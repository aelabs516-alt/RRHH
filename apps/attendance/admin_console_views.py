from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from apps.users.models import User
from .models import Attendance, AttendanceStatus
from apps.organization.models import EmployeeTurn
from django.utils import timezone
from django.db.models import Q

def is_admin(user):
    return user.is_authenticated and (user.role in ['ADMIN', 'JEFE'] or user.is_superuser)

@user_passes_test(is_admin)
def console_individual(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        reg_date = request.POST.get('date')
        entry_time = request.POST.get('entry_time')
        exit_time = request.POST.get('exit_time')
        entry_justification = request.POST.get('entry_justification', 'NORMAL')
        exit_justification = request.POST.get('exit_justification', 'NORMAL')
        entry_observations = request.POST.get('entry_observations', '')
        exit_observations = request.POST.get('exit_observations', '')

        try:
            colaborador = User.objects.get(id=user_id)
            d = datetime.strptime(reg_date, '%Y-%m-%d').date()
            
            def parse_time(time_str):
                if not time_str: return None
                time_str = time_str.strip()
                try:
                    return datetime.strptime(time_str, '%H:%M:%S').time()
                except ValueError:
                    return datetime.strptime(time_str, '%H:%M').time()

            e_time = parse_time(entry_time)
            x_time = parse_time(exit_time)
            
            entry_dt = timezone.make_aware(datetime.combine(d, e_time)) if e_time else None
            exit_dt = timezone.make_aware(datetime.combine(d, x_time)) if x_time else None
            
            hours_worked = 0.0
            if entry_dt and exit_dt:
                hours_worked = round((exit_dt - entry_dt).total_seconds() / 3600.0, 2)
            
            status = AttendanceStatus.A_TIEMPO.value
            extra_hours = 0.0
            permission_hours = 0.0
            
            matrix = EmployeeTurn.objects.filter(user=colaborador, start_date__lte=d).filter(Q(end_date__gte=d) | Q(end_date__isnull=True)).first()
            if not matrix:
                matrix = EmployeeTurn.objects.filter(user=colaborador).last()
            turn_of_day = matrix.get_turn_for_date(d) if matrix else None
            
            if entry_dt and turn_of_day and turn_of_day.start_time:
                turn_start_datetime = timezone.make_aware(datetime.combine(d, turn_of_day.start_time))
                grace_period = turn_start_datetime + timedelta(minutes=5)
                if entry_dt > grace_period:
                    status = AttendanceStatus.RETARDO.value

            if exit_dt and entry_dt and turn_of_day and turn_of_day.start_time and turn_of_day.end_time:
                turn_start_datetime = timezone.make_aware(datetime.combine(d, turn_of_day.start_time))
                turn_end_datetime = timezone.make_aware(datetime.combine(d, turn_of_day.end_time))
                if turn_of_day.end_time < turn_of_day.start_time:
                    turn_end_datetime += timedelta(days=1)
                
                turn_duration = turn_end_datetime - turn_start_datetime
                worked_duration = exit_dt - entry_dt
                
                REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
                if entry_justification in REMUNERADOS and entry_dt > turn_start_datetime:
                    worked_duration += (entry_dt - turn_start_datetime)
                    
                time_balance = worked_duration.total_seconds() - turn_duration.total_seconds()
                
                deficit_entry = 0
                if entry_dt > turn_start_datetime:
                    if entry_justification not in REMUNERADOS:
                        deficit_entry = (entry_dt - turn_start_datetime).total_seconds()
                        
                deficit_exit = 0
                if exit_dt < turn_end_datetime:
                    deficit_exit = (turn_end_datetime - exit_dt).total_seconds()

                if time_balance < 0:
                    deficit_total = abs(time_balance)
                    deuda_real = max(0.0, deficit_total - deficit_entry)
                    permission_hours = round(deuda_real / 3600.0, 2)
                    extra_hours = 0.0
                else:
                    permission_hours = 0.0
                    early_secs = 0
                    if entry_dt < turn_start_datetime:
                        early_secs = (turn_start_datetime - entry_dt).total_seconds()
                        if early_secs < 30 * 60:
                            early_secs = 0
                    late_secs = 0
                    if exit_dt > turn_end_datetime:
                        late_secs = (exit_dt - turn_end_datetime).total_seconds()
                        if late_secs < 20 * 60:
                            late_secs = 0
                    deficit_entry = 0
                    if entry_dt > turn_start_datetime:
                        if entry_justification not in REMUNERADOS:
                            deficit_entry = (entry_dt - turn_start_datetime).total_seconds()
                    deficit_exit = 0
                    if exit_dt < turn_end_datetime:
                        deficit_exit = (turn_end_datetime - exit_dt).total_seconds()
                        
                    valid_extra = early_secs + late_secs - (deficit_entry + deficit_exit)
                    if valid_extra > 0:
                        extra_hours = round(valid_extra / 3600.0, 2)
                    else:
                        extra_hours = 0.0
            elif exit_dt and turn_of_day and turn_of_day.end_time and not entry_dt:
                # Fallback in case entry_dt is missing somehow
                turn_end_datetime = timezone.make_aware(datetime.combine(d, turn_of_day.end_time))
                if turn_of_day.end_time < turn_of_day.start_time:
                    turn_end_datetime += timedelta(days=1)
                
                extra_time = exit_dt - turn_end_datetime
                if extra_time.total_seconds() > 0:
                    extra_hours = round(extra_time.total_seconds() / 3600.0, 2)
                if exit_dt < turn_end_datetime:
                    early_time = turn_end_datetime - exit_dt
                    permission_hours = round(early_time.total_seconds() / 3600.0, 2)
            elif exit_dt and not turn_of_day:
                # Si trabajó en un día de descanso (sin turno asignado), todas las horas son extras
                extra_hours = hours_worked

            if entry_justification and entry_justification != 'NORMAL':
                status = AttendanceStatus.A_TIEMPO.value
                
            REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
            if exit_justification in REMUNERADOS:
                if permission_hours > 0:
                    permission_hours = 0.0
            
            if entry_justification in REMUNERADOS and turn_of_day and turn_of_day.start_time:
                turn_start_datetime = timezone.make_aware(datetime.combine(d, turn_of_day.start_time))
                if entry_dt and entry_dt > turn_start_datetime:
                    # Sumar las horas del permiso de la mañana a las horas trabajadas netas para no afectar el balance visual
                    hours_worked = round(hours_worked + (entry_dt - turn_start_datetime).total_seconds() / 3600.0, 2)
            
            if exit_justification in REMUNERADOS and turn_of_day and turn_of_day.end_time:
                turn_end_datetime = timezone.make_aware(datetime.combine(d, turn_of_day.end_time))
                if turn_of_day.end_time < turn_of_day.start_time:
                    turn_end_datetime += timedelta(days=1)
                if exit_dt and exit_dt < turn_end_datetime:
                    # Sumar las horas del permiso de la tarde a las horas trabajadas
                    hours_worked = round(hours_worked + (turn_end_datetime - exit_dt).total_seconds() / 3600.0, 2)

            Attendance.objects.update_or_create(
                user=colaborador, date=d,
                defaults={
                    'entry_time': entry_dt,
                    'exit_time': exit_dt,
                    'hours_worked': hours_worked,
                    'extra_hours': extra_hours,
                    'permission_hours': permission_hours,
                    'entry_justification': entry_justification,
                    'exit_justification': exit_justification,
                    'entry_observations': entry_observations,
                    'exit_observations': exit_observations,
                    'entry_status': status
                }
            )
            messages.success(request, 'Registro individual guardado correctamente.')
            return redirect('attendance:console_individual')
        except Exception as e:
            import traceback
            messages.error(request, f'Error: {repr(e)}. {traceback.format_exc()}')
            return redirect('attendance:console_individual')

    users = User.objects.filter(is_active=True, role='COLABORADOR')
    return render(request, 'attendance/console_individual.html', {'users': users, 'today': date.today().strftime('%Y-%m-%d')})


@user_passes_test(is_admin)
def console_massive(request):
    selected_date_str = request.GET.get('date', date.today().strftime('%Y-%m-%d'))
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    if request.method == 'POST':
        try:
            selected_date_str = request.POST.get('date')
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
            user_ids = request.POST.getlist('user_ids')
            
            def parse_time(time_str):
                if not time_str: return None
                time_str = time_str.strip()
                try:
                    return datetime.strptime(time_str, '%H:%M:%S').time()
                except ValueError:
                    return datetime.strptime(time_str, '%H:%M').time()

            count = 0
            for uid in user_ids:
                entry_time = request.POST.get(f'entry_{uid}')
                exit_time = request.POST.get(f'exit_{uid}')
                entry_just = request.POST.get(f'entry_just_{uid}', 'NORMAL')
                exit_just = request.POST.get(f'exit_just_{uid}', 'NORMAL')
                entry_obs = request.POST.get(f'entry_obs_{uid}', '')
                exit_obs = request.POST.get(f'exit_obs_{uid}', '')

                if entry_time or exit_time:
                    colaborador = User.objects.get(id=uid)
                    
                    e_time = parse_time(entry_time)
                    x_time = parse_time(exit_time)
                    
                    entry_dt = timezone.make_aware(datetime.combine(selected_date, e_time)) if e_time else None
                    exit_dt = timezone.make_aware(datetime.combine(selected_date, x_time)) if x_time else None
                    
                    hours_worked = 0.0
                    if entry_dt and exit_dt:
                        hours_worked = round((exit_dt - entry_dt).total_seconds() / 3600.0, 2)
                        
                    status = AttendanceStatus.A_TIEMPO.value
                    extra_hours = 0.0
                    permission_hours = 0.0
                    
                    matrix = EmployeeTurn.objects.filter(user=colaborador, start_date__lte=selected_date).filter(Q(end_date__gte=selected_date) | Q(end_date__isnull=True)).first()
                    if not matrix:
                        matrix = EmployeeTurn.objects.filter(user=colaborador).last()
                    turn_of_day = matrix.get_turn_for_date(selected_date) if matrix else None
                    
                    if entry_dt and turn_of_day and turn_of_day.start_time:
                        turn_start_datetime = timezone.make_aware(datetime.combine(selected_date, turn_of_day.start_time))
                        grace_period = turn_start_datetime + timedelta(minutes=5)
                        if entry_dt > grace_period:
                            status = AttendanceStatus.RETARDO.value
                            
                    if exit_dt and entry_dt and turn_of_day and turn_of_day.start_time and turn_of_day.end_time:
                        turn_start_datetime = timezone.make_aware(datetime.combine(selected_date, turn_of_day.start_time))
                        turn_end_datetime = timezone.make_aware(datetime.combine(selected_date, turn_of_day.end_time))
                        if turn_of_day.end_time < turn_of_day.start_time:
                            turn_end_datetime += timedelta(days=1)
                        
                        turn_duration = turn_end_datetime - turn_start_datetime
                        worked_duration = exit_dt - entry_dt
                        
                        REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
                        if entry_just in REMUNERADOS and entry_dt > turn_start_datetime:
                            worked_duration += (entry_dt - turn_start_datetime)
                            
                        time_balance = worked_duration.total_seconds() - turn_duration.total_seconds()
                        
                        deficit_entry = 0
                        if entry_dt > turn_start_datetime:
                            if entry_just not in REMUNERADOS:
                                deficit_entry = (entry_dt - turn_start_datetime).total_seconds()
                                
                        deficit_exit = 0
                        if exit_dt < turn_end_datetime:
                            deficit_exit = (turn_end_datetime - exit_dt).total_seconds()

                        if time_balance < 0:
                            deficit_total = abs(time_balance)
                            deuda_real = max(0.0, deficit_total - deficit_entry)
                            permission_hours = round(deuda_real / 3600.0, 2)
                            extra_hours = 0.0
                        else:
                            permission_hours = 0.0
                            early_secs = 0
                            if entry_dt < turn_start_datetime:
                                early_secs = (turn_start_datetime - entry_dt).total_seconds()
                                if early_secs < 30 * 60:
                                    early_secs = 0
                            late_secs = 0
                            if exit_dt > turn_end_datetime:
                                late_secs = (exit_dt - turn_end_datetime).total_seconds()
                                if late_secs < 20 * 60:
                                    late_secs = 0
                            deficit_entry = 0
                            if entry_dt > turn_start_datetime:
                                if entry_just not in REMUNERADOS:
                                    deficit_entry = (entry_dt - turn_start_datetime).total_seconds()
                            deficit_exit = 0
                            if exit_dt < turn_end_datetime:
                                deficit_exit = (turn_end_datetime - exit_dt).total_seconds()
                                
                            valid_extra = early_secs + late_secs - (deficit_entry + deficit_exit)
                            if valid_extra > 0:
                                extra_hours = round(valid_extra / 3600.0, 2)
                            else:
                                extra_hours = 0.0
                    elif exit_dt and turn_of_day and turn_of_day.end_time and not entry_dt:
                        turn_end_datetime = timezone.make_aware(datetime.combine(selected_date, turn_of_day.end_time))
                        if turn_of_day.end_time < turn_of_day.start_time:
                            turn_end_datetime += timedelta(days=1)
                        
                        extra_time = exit_dt - turn_end_datetime
                        if extra_time.total_seconds() > 0:
                            extra_hours = round(extra_time.total_seconds() / 3600.0, 2)
                            
                        if exit_dt < turn_end_datetime:
                            early_time = turn_end_datetime - exit_dt
                            permission_hours = round(early_time.total_seconds() / 3600.0, 2)
                    elif exit_dt and not turn_of_day:
                        # Si trabajó en un día de descanso (sin turno asignado), todas las horas son extras
                        extra_hours = hours_worked

                    if entry_just and entry_just != 'NORMAL':
                        status = AttendanceStatus.A_TIEMPO.value
                        
                    REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
                    if exit_just in REMUNERADOS:
                        if permission_hours > 0:
                            permission_hours = 0.0
                            
                    if entry_just in REMUNERADOS and turn_of_day and turn_of_day.start_time:
                        turn_start_datetime = timezone.make_aware(datetime.combine(selected_date, turn_of_day.start_time))
                        if entry_dt and entry_dt > turn_start_datetime:
                            hours_worked = round(hours_worked + (entry_dt - turn_start_datetime).total_seconds() / 3600.0, 2)
                            
                    if exit_just in REMUNERADOS and turn_of_day and turn_of_day.end_time:
                        turn_end_datetime = timezone.make_aware(datetime.combine(selected_date, turn_of_day.end_time))
                        if turn_of_day.end_time < turn_of_day.start_time:
                            turn_end_datetime += timedelta(days=1)
                        if exit_dt and exit_dt < turn_end_datetime:
                            hours_worked = round(hours_worked + (turn_end_datetime - exit_dt).total_seconds() / 3600.0, 2)

                    Attendance.objects.update_or_create(
                        user=colaborador, date=selected_date,
                        defaults={
                            'entry_time': entry_dt,
                            'exit_time': exit_dt,
                            'hours_worked': hours_worked,
                            'extra_hours': extra_hours,
                            'permission_hours': permission_hours,
                            'entry_justification': entry_just,
                            'exit_justification': exit_just,
                            'entry_observations': entry_obs,
                            'exit_observations': exit_obs,
                            'entry_status': status
                        }
                    )
                    count += 1
                    
            messages.success(request, f'Se registraron/actualizaron {count} asistencias.')
            return redirect(f"{request.path}?date={selected_date_str}")
        except Exception as e:
            import traceback
            error_msg = f"Error en sistema: {repr(e)}. Detalles: {traceback.format_exc()}"
            messages.error(request, error_msg)
            return redirect(f"{request.path}?date={request.POST.get('date', date.today().strftime('%Y-%m-%d'))}")

    users = User.objects.filter(is_active=True, role='COLABORADOR')
    
    # Enrich with today's turn
    user_data = []
    for u in users:
        # Find active turn matrix
        matrix = EmployeeTurn.objects.filter(user=u, start_date__lte=selected_date).filter(Q(end_date__gte=selected_date) | Q(end_date__isnull=True)).first()
        if not matrix:
            matrix = EmployeeTurn.objects.filter(user=u).last()
        turn_of_day = matrix.get_turn_for_date(selected_date) if matrix else None
        turn_str = turn_of_day.name if turn_of_day else "Sin Turno"
        
        # Find existing attendance
        att = Attendance.objects.filter(user=u, date=selected_date).first()
        
        user_data.append({
            'user': u,
            'turn': turn_str,
            'attendance': att
        })

    return render(request, 'attendance/console_massive.html', {
        'user_data': user_data, 
        'selected_date': selected_date_str
    })

@user_passes_test(is_admin)
def delete_attendance(request, pk):
    try:
        att = Attendance.objects.get(pk=pk)
        att.delete()
        messages.success(request, 'Registro de marcacin eliminado correctamente.')
    except Attendance.DoesNotExist:
        messages.error(request, 'El registro no existe.')
    return redirect(request.META.get('HTTP_REFERER', 'attendance:console_massive'))

