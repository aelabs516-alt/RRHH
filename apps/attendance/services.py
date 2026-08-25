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

def process_entry(user, entry_datetime, photo=None, lat=None, lng=None):
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
            'entry_photo': photo,
            'latitude': lat,
            'longitude': lng,
            'is_out_of_bounds': is_out_of_bounds
        }
    )
    
    if not created:
        # Actualiza si hubo un error o es sobreescritura válida (ej. reintento)
        attendance.entry_time = entry_datetime
        attendance.entry_status = status
        if photo: attendance.entry_photo = photo
        attendance.latitude = lat
        attendance.longitude = lng
        attendance.is_out_of_bounds = is_out_of_bounds
        attendance.save()

    act_generated = None
    if status == AttendanceStatus.RETARDO:
        act_generated = check_and_generate_disciplinary_act(user, date)
        
    return attendance, status, act_generated

def process_exit(user, exit_datetime, observations="", photo=None, lat=None, lng=None):
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
    
    if turn:
        turn_end_datetime = timezone.make_aware(datetime.combine(date, turn.end_time))
        
        # Night shift logic: if turn ends before it starts, add 1 day to end_datetime
        if turn.end_time < turn.start_time:
            turn_end_datetime += timedelta(days=1)
            
        # Evaluación de la Salida: Regla de 30 Minutos (Horas Extras)
        extra_time = exit_datetime - turn_end_datetime
        if extra_time.total_seconds() > 30 * 60:
            extra_hours = extra_time.total_seconds() / 3600.0
            
        # Cálculo de horas de permiso o salida anticipada
        if exit_datetime < turn_end_datetime:
            early_time = turn_end_datetime - exit_datetime
            permission_hours = early_time.total_seconds() / 3600.0

    # Condicional de Observaciones Obligatorias
    if (extra_hours > 0 or permission_hours > 0) and not observations.strip():
        raise ValueError("Es obligatorio ingresar el Motivo (observaciones) por generar horas extras o salida anticipada.")
        
    attendance.exit_time = exit_datetime
    if photo: attendance.exit_photo = photo
    attendance.extra_hours = round(extra_hours, 2)
    attendance.permission_hours = round(permission_hours, 2)
    attendance.observations = observations
    
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
        
    attendance.save()
    return attendance
