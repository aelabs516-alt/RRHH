from datetime import datetime, timedelta
from django.utils import timezone
from django.db import models
from apps.attendance.models import Attendance, AttendanceStatus
from apps.organization.models import EmployeeTurn
from apps.hr.models import DisciplinaryAct, FaultSeverity

def get_current_turn(user, date):
    """Obtiene el turno activo de un colaborador para una fecha dada desde la matriz."""
    matrix = EmployeeTurn.objects.filter(
        user=user, 
        start_date__lte=date
    ).filter(
        models.Q(end_date__gte=date) | models.Q(end_date__isnull=True)
    ).first()
    
    if not matrix:
        matrix = EmployeeTurn.objects.filter(user=user).last()
        
    if matrix:
        return matrix.get_turn_for_date(date)
    return None

def check_and_generate_disciplinary_act(user, current_date):
    """
    Evalúa la matriz de reincidencia semanal y genera actas si corresponde.
    Retorna None, un string ("ALERTA_CRITICA") o la instancia del Acta.
    """
    # Lógica de semana (Lunes=0, Domingo=6)
    start_of_week = current_date - timedelta(days=current_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    # Contar retardos en la semana actual
    tardies_this_week = Attendance.objects.filter(
        user=user,
        date__range=[start_of_week, end_of_week],
        entry_status=AttendanceStatus.RETARDO
    ).count()

    if tardies_this_week < 3:
        return None
    elif tardies_this_week == 3:
        return "ALERTA_CRITICA" # Se dispara flag para el Admin
    
    # Regla de Reinicio e Historial Intersemanal
    start_of_month = current_date.replace(day=1)
    
    previous_acts_this_month = DisciplinaryAct.objects.filter(
        user=user,
        date_created__date__gte=start_of_month,
        date_created__date__lt=start_of_week
    ).exists()
    
    severity = FaultSeverity.LEVE
    
    if tardies_this_week == 4:
        severity = FaultSeverity.GRAVE if previous_acts_this_month else FaultSeverity.LEVE
    elif tardies_this_week == 5:
        severity = FaultSeverity.GRAVE
    elif tardies_this_week >= 6:
        severity = FaultSeverity.MUY_GRAVE
        
    # Construir descripción automatizada extraída de la asistencia
    tardy_records = Attendance.objects.filter(
        user=user,
        date__range=[start_of_week, current_date],
        entry_status=AttendanceStatus.RETARDO
    ).order_by('date')
    
    dates_str = ", ".join([
        f"{t.date.strftime('%d/%m/%Y')} - {t.entry_time.astimezone(timezone.get_current_timezone()).strftime('%H:%M')}"
        for t in tardy_records if t.entry_time
    ])
    
    description = (
        f"El colaborador durante el mes, registró llegadas tardías en las siguientes fechas, con hora de ingreso: "
        f"[{dates_str}].\n\n"
        "Lo anterior evidencia una conducta reiterada de incumplimiento del horario laboral "
        "establecido por la empresa, situación que ha sido previamente informada al colaborador."
    )
    
    # Generar Acta Disciplinaria
    act = DisciplinaryAct.objects.create(
        user=user,
        severity=severity,
        description=description,
        decision="Llamado de atención escrito"
    )
    
    return act

import math

def calculate_distance(lat1, lon1, lat2, lon2):
    # Radio de la Tierra en metros
    R = 6371000 
    
    # Asegurar que todos sean float (para evitar error entre decimal.Decimal y float)
    lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0)**2
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def process_entry(user, entry_datetime, entry_justification='NORMAL', entry_observations='', photo=None, lat=None, lng=None):
    """
    Procesa el ingreso, aplica la regla de 5 minutos, evalúa actas disciplinarias y geolocalización.
    """
    from apps.organization.models import CompanySettings
    settings = CompanySettings.get_settings()
    COMPANY_LAT = settings.latitude
    COMPANY_LNG = settings.longitude
    
    local_dt = timezone.localtime(entry_datetime)
    date = local_dt.date()
    turn = get_current_turn(user, date)
    if not turn:
        raise ValueError("El usuario no tiene un turno asignado para esta fecha.")

    # Convertir start_time a datetime local
    turn_start_datetime = timezone.make_aware(datetime.combine(date, turn.start_time))
    
    # Umbral de Tolerancia: 5 minutos
    grace_period = turn_start_datetime + timedelta(minutes=5)
    
    status = AttendanceStatus.A_TIEMPO
    if entry_datetime > grace_period:
        if entry_justification == 'NORMAL':
            raise ValueError("require_entry_justification")
            
        REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
        if entry_justification in REMUNERADOS:
            status = AttendanceStatus.A_TIEMPO
        else:
            status = AttendanceStatus.RETARDO
            
    is_out_of_bounds = False
    if lat is not None and lng is not None:
        distance = calculate_distance(float(lat), float(lng), COMPANY_LAT, COMPANY_LNG)
        if distance > settings.tolerance_radius:
            is_out_of_bounds = True
        
    attendance, created = Attendance.objects.get_or_create(
        user=user, date=date,
        defaults={
            'entry_time': entry_datetime, 
            'entry_status': status, 
            'entry_justification': entry_justification,
            'entry_observations': entry_observations,
            'entry_photo': photo,
            'latitude': lat,
            'longitude': lng,
            'is_out_of_bounds': is_out_of_bounds
        }
    )
    
    if not created:
        if attendance.entry_time is not None:
            raise ValueError("Ya tienes un ingreso registrado para el turno de hoy. Si hay un error, contacta a tu jefe o RRHH.")
            
        # Actualiza si el registro existía pero sin hora de ingreso (ej. salida anticipada sin marcación de entrada)
        attendance.entry_time = entry_datetime
        attendance.entry_status = status
        attendance.entry_justification = entry_justification
        attendance.entry_observations = entry_observations
        if photo: attendance.entry_photo = photo
        attendance.latitude = lat
        attendance.longitude = lng
        attendance.is_out_of_bounds = is_out_of_bounds
        attendance.save()

    act_generated = None
    if status == AttendanceStatus.RETARDO:
        act_generated = check_and_generate_disciplinary_act(user, date)
        
    return attendance, status, act_generated

def process_exit(user, exit_datetime, exit_justification='NORMAL', exit_observations='', photo=None, lat=None, lng=None):
    """
    Procesa la salida, aplica la regla de 30 minutos de horas extras y validación de observaciones.
    """
    from apps.organization.models import CompanySettings
    settings = CompanySettings.get_settings()
    COMPANY_LAT = settings.latitude
    COMPANY_LNG = settings.longitude
    
    local_dt = timezone.localtime(exit_datetime)
    
    # Find the most recent open attendance (handles night shifts crossing midnight)
    attendance = Attendance.objects.filter(user=user, exit_time__isnull=True).order_by('-date').first()
    if not attendance:
        raise ValueError("Secuencia ilógica: No tienes un ingreso pendiente por cerrar.")
        
    date = attendance.date
    turn = get_current_turn(user, date)
    
    extra_hours = 0.0
    permission_hours = 0.0
    
    if turn and turn.start_time and turn.end_time and attendance.entry_time:
        turn_start_datetime = timezone.make_aware(datetime.combine(date, turn.start_time))
        turn_end_datetime = timezone.make_aware(datetime.combine(date, turn.end_time))
        
        # Night shift logic
        if turn.end_time < turn.start_time:
            turn_end_datetime += timedelta(days=1)
            
        turn_duration = turn_end_datetime - turn_start_datetime
        
        effective_entry = attendance.entry_time
        if effective_entry < turn_start_datetime:
            if (turn_start_datetime - effective_entry).total_seconds() < 30 * 60:
                effective_entry = turn_start_datetime
                
        effective_exit = exit_datetime
        if effective_exit > turn_end_datetime:
            if (effective_exit - turn_end_datetime).total_seconds() < 20 * 60:
                effective_exit = turn_end_datetime
                
        worked_duration = effective_exit - effective_entry
        
        # Reconocer el tiempo del ingreso tarde como tiempo trabajado si fue un permiso remunerado
        REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
        if getattr(attendance, 'entry_justification', 'NORMAL') in REMUNERADOS and attendance.entry_time > turn_start_datetime:
            paid_morning_delay = attendance.entry_time - turn_start_datetime
            worked_duration += paid_morning_delay
            
        time_balance = worked_duration.total_seconds() - turn_duration.total_seconds()
        
        if time_balance > 0:
            extra_hours = time_balance / 3600.0
        elif time_balance < 0:
            permission_hours = abs(time_balance) / 3600.0
            
    elif turn and turn.end_time and not attendance.entry_time:
        turn_end_datetime = timezone.make_aware(datetime.combine(date, turn.end_time))
        if turn.end_time < turn.start_time:
            turn_end_datetime += timedelta(days=1)
            
        extra_time = exit_datetime - turn_end_datetime
        if extra_time.total_seconds() >= 20 * 60:
            extra_hours = extra_time.total_seconds() / 3600.0
            
        if exit_datetime < turn_end_datetime:
            early_time = turn_end_datetime - exit_datetime
            permission_hours = early_time.total_seconds() / 3600.0

    # Condicional de Observaciones Obligatorias
    if (extra_hours > 0 or permission_hours > 0) and exit_justification == 'NORMAL':
        raise ValueError("require_exit_justification")
        
    REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
    if exit_justification in REMUNERADOS:
        # Si es remunerado, el tiempo faltante se considera trabajado, no se descuenta
        if permission_hours > 0:
            permission_hours = 0.0
        # Las horas extras se mantienen si las generó después de su permiso (el permiso cuenta como trabajado)

    attendance.exit_time = exit_datetime
    if photo: attendance.exit_photo = photo
    attendance.extra_hours = round(extra_hours, 2)
    attendance.permission_hours = round(permission_hours, 2)
    attendance.exit_justification = exit_justification
    attendance.exit_observations = exit_observations
    
    if lat is not None and lng is not None:
        distance = calculate_distance(float(lat), float(lng), COMPANY_LAT, COMPANY_LNG)
        attendance.latitude = lat
        attendance.longitude = lng
        if distance > settings.tolerance_radius:
            attendance.is_out_of_bounds = True
    
    # Horas trabajadas en el día
    if attendance.entry_time:
        worked_time = exit_datetime - attendance.entry_time
        attendance.hours_worked = round(worked_time.total_seconds() / 3600.0, 2)
        
        # Aumentar las horas trabajadas si hubo un permiso remunerado
        REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
        if getattr(attendance, 'entry_justification', 'NORMAL') in REMUNERADOS and turn and turn.start_time:
            turn_start = timezone.make_aware(datetime.combine(date, turn.start_time))
            if attendance.entry_time > turn_start:
                attendance.hours_worked += round((attendance.entry_time - turn_start).total_seconds() / 3600.0, 2)
                
        if exit_justification in REMUNERADOS and turn and turn.end_time:
            turn_end = timezone.make_aware(datetime.combine(date, turn.end_time))
            if turn.end_time < turn.start_time:
                turn_end += timedelta(days=1)
            if exit_datetime < turn_end:
                attendance.hours_worked += round((turn_end - exit_datetime).total_seconds() / 3600.0, 2)
        
    if not turn and attendance.hours_worked > 0:
        # Si trabajó en un día de descanso (sin turno), todo es hora extra
        attendance.extra_hours = attendance.hours_worked
        
    attendance.save()
    return attendance
