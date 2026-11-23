from datetime import datetime, timedelta, time
from django.utils import timezone
from django.db import models
from apps.attendance.models import Attendance, AttendanceStatus
from apps.organization.models import EmployeeTurn, CustomHoliday
from apps.hr.models import DisciplinaryAct, FaultSeverity

REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
NO_REMUNERADOS = ['PERSONAL', 'OTROS']


def get_colombian_holidays(years):
    """Retorna un conjunto de fechas festivas de Colombia + festivos personalizados para los años dados."""
    holiday_dates = set()
    try:
        import holidays as pyholidays
        co_holidays = pyholidays.CO(years=list(years))
        holiday_dates.update(co_holidays.keys())
    except Exception:
        pass
    db_holidays = CustomHoliday.objects.values_list('date', flat=True)
    holiday_dates.update(db_holidays)
    return holiday_dates


def get_lunch_window(work_date, turn_start_dt, turn_end_dt):
    """
    De lunes a viernes (weekday 0..4), toda jornada completa (> 5 horas) cuenta con
    1 hora de almuerzo que no se contabiliza dentro de los tiempos totales de trabajo.
    Se ubica la ventana de 1 hora en el punto medio del turno (ej: 08:00-17:00 -> 12:00-13:00;
    09:00-18:00 -> 13:00-14:00).
    """
    if work_date.weekday() < 5 and turn_start_dt and turn_end_dt:
        turn_span = turn_end_dt - turn_start_dt
        if turn_span > timedelta(hours=5):
            midpoint = turn_start_dt + (turn_span / 2)
            return (midpoint - timedelta(minutes=30), midpoint + timedelta(minutes=30))
    return (None, None)


def effective_seconds(start_dt, end_dt, lunch_start=None, lunch_end=None):
    """
    Retorna los segundos efectivos entre start_dt y end_dt, descontando cualquier
    traslape con la ventana de almuerzo [lunch_start, lunch_end].
    """
    if not start_dt or not end_dt or end_dt <= start_dt:
        return 0.0
    raw_secs = (end_dt - start_dt).total_seconds()
    if lunch_start and lunch_end:
        overlap_start = max(start_dt, lunch_start)
        overlap_end = min(end_dt, lunch_end)
        if overlap_end > overlap_start:
            raw_secs -= (overlap_end - overlap_start).total_seconds()
    return max(0.0, raw_secs)


def calculate_attendance_metrics(
    work_date,
    turn,
    entry_dt,
    exit_dt,
    entry_justification='NORMAL',
    exit_justification='NORMAL',
    apply_exit_only_threshold=False,
):
    """
    Calcula (hours_worked, extra_hours, permission_hours) aplicando:
    - Exclusión de 1 hora de almuerzo de lunes a viernes en jornadas completas (> 5h).
    - Permisos remunerados no descuentan tiempo y suman a las horas trabajadas.
    - Permisos no remunerados (PERSONAL, OTROS) no generan horas extras.
    - Umbrales de hora extra: >= 30 min anticipado en ingreso, >= 20 min tarde en salida.
    - La llegada tarde no remunerada no se acumula en permission_hours (es retardo).
    """
    hours_worked = 0.0
    extra_hours = 0.0
    permission_hours = 0.0

    # Soportar turno nocturno en registros manuales donde exit_dt < entry_dt
    if entry_dt and exit_dt and exit_dt < entry_dt:
        if turn and turn.start_time and turn.end_time and turn.end_time < turn.start_time:
            exit_dt = exit_dt + timedelta(days=1)

    turn_start_dt = None
    turn_end_dt = None
    lunch_start = None
    lunch_end = None

    if turn and turn.start_time and turn.end_time:
        turn_start_dt = timezone.make_aware(datetime.combine(work_date, turn.start_time))
        turn_end_dt = timezone.make_aware(datetime.combine(work_date, turn.end_time))
        if turn.end_time < turn.start_time:
            turn_end_dt += timedelta(days=1)
        lunch_start, lunch_end = get_lunch_window(work_date, turn_start_dt, turn_end_dt)

    if entry_dt and exit_dt and turn_start_dt and turn_end_dt:
        turn_effective_secs = effective_seconds(turn_start_dt, turn_end_dt, lunch_start, lunch_end)
        raw_worked_secs = effective_seconds(entry_dt, exit_dt, lunch_start, lunch_end)
        worked_secs = raw_worked_secs

        # Agregar tiempo si llegó tarde con justa causa remunerada
        paid_morning_secs = 0.0
        if entry_justification in REMUNERADOS and entry_dt > turn_start_dt:
            paid_morning_secs = effective_seconds(turn_start_dt, entry_dt, lunch_start, lunch_end)
            worked_secs += paid_morning_secs

        time_balance = worked_secs - turn_effective_secs

        # Déficit de ingreso no remunerado
        deficit_entry = 0.0
        if entry_dt > turn_start_dt and entry_justification not in REMUNERADOS:
            deficit_entry = effective_seconds(turn_start_dt, entry_dt, lunch_start, lunch_end)

        # Déficit de salida anticipada
        deficit_exit = 0.0
        if exit_dt < turn_end_dt:
            deficit_exit = effective_seconds(exit_dt, turn_end_dt, lunch_start, lunch_end)

        if time_balance < 0:
            # Regla: Si llegó tarde pero no compensó, no tomar el tiempo de llegada tarde como permiso.
            deficit_total = abs(time_balance)
            deuda_real = max(0.0, deficit_total - deficit_entry)
            permission_hours = deuda_real / 3600.0
            extra_hours = 0.0
        else:
            permission_hours = 0.0
            early_secs = 0.0
            if entry_dt < turn_start_dt:
                early_secs = effective_seconds(entry_dt, turn_start_dt, lunch_start, lunch_end)
                if early_secs < 30 * 60 or entry_justification in NO_REMUNERADOS:
                    early_secs = 0.0

            late_secs = 0.0
            if exit_dt > turn_end_dt:
                late_secs = effective_seconds(turn_end_dt, exit_dt, lunch_start, lunch_end)
                if late_secs < 20 * 60 or exit_justification in NO_REMUNERADOS:
                    late_secs = 0.0

            valid_extra = early_secs + late_secs - (deficit_entry + deficit_exit)
            extra_hours = (valid_extra / 3600.0) if valid_extra > 0 else 0.0

        # Horas trabajadas efectivas (sin almuerzo, sumando permisos remunerados)
        total_worked_secs = raw_worked_secs + paid_morning_secs
        if exit_justification in REMUNERADOS and exit_dt < turn_end_dt:
            total_worked_secs += effective_seconds(exit_dt, turn_end_dt, lunch_start, lunch_end)
        hours_worked = total_worked_secs / 3600.0

    elif exit_dt and turn_end_dt and not entry_dt:
        if exit_dt > turn_end_dt:
            extra_secs = effective_seconds(turn_end_dt, exit_dt, lunch_start, lunch_end)
            if (not apply_exit_only_threshold or extra_secs >= 20 * 60) and exit_justification not in NO_REMUNERADOS:
                extra_hours = extra_secs / 3600.0
        if exit_dt < turn_end_dt:
            early_secs = effective_seconds(exit_dt, turn_end_dt, lunch_start, lunch_end)
            permission_hours = early_secs / 3600.0

    elif entry_dt and exit_dt and not turn:
        # Día sin turno asignado (descanso/extra): todas las horas efectivas son extras
        raw_secs = max(0.0, (exit_dt - entry_dt).total_seconds())
        if work_date.weekday() < 5 and raw_secs > 5 * 3600:
            raw_secs -= 3600.0
        hours_worked = raw_secs / 3600.0
        if hours_worked > 0 and exit_justification not in NO_REMUNERADOS:
            extra_hours = hours_worked

    if exit_justification in REMUNERADOS and permission_hours > 0:
        permission_hours = 0.0

    return round(hours_worked, 2), round(extra_hours, 2), round(permission_hours, 2)


def calculate_permission_working_hours(
    user,
    start_dt,
    end_dt,
    filter_start_date=None,
    filter_end_date=None,
    holidays_set=None,
):
    """
    Calcula las horas laborales efectivas de un permiso (de uno o varios días),
    considerando ÚNICAMENTE el horario laboral asignado al colaborador (EmployeeTurn),
    NO las 24 horas del día:
    - Intersecta cada día del rango con el turno laboral del colaborador.
    - Excluye días de descanso (sin turno asignado) y festivos colombianos/personalizados.
    - Excluye la 1 hora de almuerzo de lunes a viernes en jornadas completas (> 5 horas).
    - Si el colaborador no tiene matriz de turnos asignada, usa L-V 08:00-17:00 (8h efectivas/día).
    """
    if not start_dt or not end_dt or end_dt <= start_dt:
        return 0.0

    start_local = timezone.make_aware(start_dt) if timezone.is_naive(start_dt) else timezone.localtime(start_dt)
    end_local = timezone.make_aware(end_dt) if timezone.is_naive(end_dt) else timezone.localtime(end_dt)

    if filter_start_date:
        f_start_dt = timezone.make_aware(datetime.combine(filter_start_date, time.min))
        start_local = max(start_local, f_start_dt)
    if filter_end_date:
        f_end_dt = timezone.make_aware(datetime.combine(filter_end_date + timedelta(days=1), time.min))
        end_local = min(end_local, f_end_dt)

    if end_local <= start_local:
        return 0.0

    if holidays_set is None:
        years = range(start_local.year - 1, end_local.year + 2)
        holidays_set = get_colombian_holidays(years)

    has_matrix = EmployeeTurn.objects.filter(user=user).exists()

    total_secs = 0.0
    curr_date = start_local.date() - timedelta(days=1)
    last_date = end_local.date()

    while curr_date <= last_date:
        if curr_date in holidays_set:
            curr_date += timedelta(days=1)
            continue

        turn_start_dt = None
        turn_end_dt = None

        if has_matrix:
            turn = get_current_turn(user, curr_date)
            if turn and turn.start_time and turn.end_time:
                turn_start_dt = timezone.make_aware(datetime.combine(curr_date, turn.start_time))
                turn_end_dt = timezone.make_aware(datetime.combine(curr_date, turn.end_time))
                if turn.end_time < turn.start_time:
                    turn_end_dt += timedelta(days=1)
        else:
            if curr_date.weekday() < 5:
                turn_start_dt = timezone.make_aware(datetime.combine(curr_date, time(8, 0)))
                turn_end_dt = timezone.make_aware(datetime.combine(curr_date, time(17, 0)))

        if turn_start_dt and turn_end_dt:
            overlap_start = max(start_local, turn_start_dt)
            overlap_end = min(end_local, turn_end_dt)
            if overlap_end > overlap_start:
                lunch_start, lunch_end = get_lunch_window(curr_date, turn_start_dt, turn_end_dt)
                total_secs += effective_seconds(overlap_start, overlap_end, lunch_start, lunch_end)

        curr_date += timedelta(days=1)

    return round(total_secs / 3600.0, 2)

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
    
    needs_entry_just = False
    if entry_datetime > grace_period:
        needs_entry_just = True
    if entry_datetime <= turn_start_datetime - timedelta(minutes=30):
        needs_entry_just = True
        
    if needs_entry_just and entry_justification == 'NORMAL':
        raise ValueError("require_entry_justification")

    if entry_datetime > grace_period:
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

    turn_end_datetime = None
    if turn and turn.end_time:
        turn_end_datetime = timezone.make_aware(datetime.combine(date, turn.end_time))
        if turn.start_time and turn.end_time < turn.start_time:
            turn_end_datetime += timedelta(days=1)

    hours_worked, extra_hours, permission_hours = calculate_attendance_metrics(
        work_date=date,
        turn=turn,
        entry_dt=attendance.entry_time,
        exit_dt=exit_datetime,
        entry_justification=getattr(attendance, 'entry_justification', 'NORMAL'),
        exit_justification=exit_justification,
        apply_exit_only_threshold=True,
    )

    # Condicional de Observaciones Obligatorias
    needs_exit_just = False
    if turn_end_datetime:
        if exit_datetime < turn_end_datetime:
            needs_exit_just = True
        if exit_datetime >= turn_end_datetime + timedelta(minutes=20):
            needs_exit_just = True
    if not turn and hours_worked > 0:
        needs_exit_just = True

    if needs_exit_just and exit_justification == 'NORMAL':
        raise ValueError("require_exit_justification")

    attendance.exit_time = exit_datetime
    if photo:
        attendance.exit_photo = photo
    attendance.hours_worked = hours_worked
    attendance.extra_hours = extra_hours
    attendance.permission_hours = permission_hours
    attendance.exit_justification = exit_justification
    attendance.exit_observations = exit_observations

    if lat is not None and lng is not None:
        distance = calculate_distance(float(lat), float(lng), COMPANY_LAT, COMPANY_LNG)
        attendance.latitude = lat
        attendance.longitude = lng
        if distance > settings.tolerance_radius:
            attendance.is_out_of_bounds = True

    attendance.save()
    return attendance
