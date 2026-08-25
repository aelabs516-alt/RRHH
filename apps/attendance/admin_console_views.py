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
        justification_type = request.POST.get('justification_type', 'NORMAL')
        observations = request.POST.get('observations', '')

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
                
                time_balance = worked_duration.total_seconds() - turn_duration.total_seconds()
                
                if time_balance >= 30 * 60:
                    extra_hours = round(time_balance / 3600.0, 2)
                elif time_balance < 0:
                    permission_hours = round(abs(time_balance) / 3600.0, 2)
            elif exit_dt and turn_of_day and turn_of_day.end_time and not entry_dt:
                # Fallback in case entry_dt is missing somehow
                turn_end_datetime = timezone.make_aware(datetime.combine(d, turn_of_day.end_time))
                if turn_of_day.end_time < turn_of_day.start_time:
                    turn_end_datetime += timedelta(days=1)
                
                extra_time = exit_dt - turn_end_datetime
                if extra_time.total_seconds() >= 30 * 60:
                    extra_hours = round(extra_time.total_seconds() / 3600.0, 2)
                if exit_dt < turn_end_datetime:
                    early_time = turn_end_datetime - exit_dt
                    permission_hours = round(early_time.total_seconds() / 3600.0, 2)
            elif exit_dt and not turn_of_day:
                # Si trabajó en un día de descanso (sin turno asignado), todas las horas son extras
                extra_hours = hours_worked

            if justification_type and justification_type != 'NORMAL':
                status = AttendanceStatus.A_TIEMPO.value
                
            REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
            if justification_type in REMUNERADOS:
                permission_hours = 0.0
                if turn_of_day and turn_of_day.start_time and turn_of_day.end_time:
                    # Calcular horas esperadas del turno
                    t_start = datetime.combine(d, turn_of_day.start_time)
                    t_end = datetime.combine(d, turn_of_day.end_time)
                    if turn_of_day.end_time < turn_of_day.start_time:
                        t_end += timedelta(days=1)
                    expected_hours = round((t_end - t_start).total_seconds() / 3600.0, 2)
                    if hours_worked < expected_hours:
                        hours_worked = expected_hours

            Attendance.objects.update_or_create(
                user=colaborador, date=d,
                defaults={
                    'entry_time': entry_dt,
                    'exit_time': exit_dt,
                    'hours_worked': hours_worked,
                    'extra_hours': extra_hours,
                    'permission_hours': permission_hours,
                    'justification_type': justification_type,
                    'observations': observations,
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
                just_type = request.POST.get(f'just_{uid}', 'NORMAL')
                obs = request.POST.get(f'obs_{uid}', '')

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
                        
                        time_balance = worked_duration.total_seconds() - turn_duration.total_seconds()
                        
                        if time_balance >= 30 * 60:
                            extra_hours = round(time_balance / 3600.0, 2)
                        elif time_balance < 0:
                            permission_hours = round(abs(time_balance) / 3600.0, 2)
                    elif exit_dt and turn_of_day and turn_of_day.end_time and not entry_dt:
                        turn_end_datetime = timezone.make_aware(datetime.combine(selected_date, turn_of_day.end_time))
                        if turn_of_day.end_time < turn_of_day.start_time:
                            turn_end_datetime += timedelta(days=1)
                        
                        extra_time = exit_dt - turn_end_datetime
                        if extra_time.total_seconds() >= 30 * 60:
                            extra_hours = round(extra_time.total_seconds() / 3600.0, 2)
                            
                        if exit_dt < turn_end_datetime:
                            early_time = turn_end_datetime - exit_dt
                            permission_hours = round(early_time.total_seconds() / 3600.0, 2)
                    elif exit_dt and not turn_of_day:
                        # Si trabajó en un día de descanso (sin turno asignado), todas las horas son extras
                        extra_hours = hours_worked

                    if just_type and just_type != 'NORMAL':
                        status = AttendanceStatus.A_TIEMPO.value
                        
                    REMUNERADOS = ['CITA_MEDICA', 'ELECCIONES', 'CALAMIDAD', 'ESCOLAR', 'JUDICIAL', 'LUTO', 'ENFERMEDAD']
                    if just_type in REMUNERADOS:
                        permission_hours = 0.0
                        if turn_of_day and turn_of_day.start_time and turn_of_day.end_time:
                            t_start = datetime.combine(selected_date, turn_of_day.start_time)
                            t_end = datetime.combine(selected_date, turn_of_day.end_time)
                            if turn_of_day.end_time < turn_of_day.start_time:
                                t_end += timedelta(days=1)
                            expected_hours = round((t_end - t_start).total_seconds() / 3600.0, 2)
                            if hours_worked < expected_hours:
                                hours_worked = expected_hours

                    Attendance.objects.update_or_create(
                        user=colaborador, date=selected_date,
                        defaults={
                            'entry_time': entry_dt,
                            'exit_time': exit_dt,
                            'hours_worked': hours_worked,
                            'extra_hours': extra_hours,
                            'permission_hours': permission_hours,
                            'justification_type': just_type,
                            'observations': obs,
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

