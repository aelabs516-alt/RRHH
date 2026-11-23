import json
from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from apps.users.models import User
from .models import Attendance, AttendanceStatus
from .services import calculate_attendance_metrics
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

            status = AttendanceStatus.A_TIEMPO.value

            matrix = EmployeeTurn.objects.filter(user=colaborador, start_date__lte=d).filter(Q(end_date__gte=d) | Q(end_date__isnull=True)).first()
            if not matrix:
                matrix = EmployeeTurn.objects.filter(user=colaborador).last()
            turn_of_day = matrix.get_turn_for_date(d) if matrix else None

            if entry_dt and turn_of_day and turn_of_day.start_time:
                turn_start_datetime = timezone.make_aware(datetime.combine(d, turn_of_day.start_time))
                grace_period = turn_start_datetime + timedelta(minutes=5)
                if entry_dt > grace_period:
                    status = AttendanceStatus.RETARDO.value

            if entry_justification and entry_justification != 'NORMAL':
                status = AttendanceStatus.A_TIEMPO.value

            hours_worked, extra_hours, permission_hours = calculate_attendance_metrics(
                work_date=d,
                turn=turn_of_day,
                entry_dt=entry_dt,
                exit_dt=exit_dt,
                entry_justification=entry_justification,
                exit_justification=exit_justification,
                apply_exit_only_threshold=False,
            )

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
    user_turns_map = {}
    for u in users:
        matrix = EmployeeTurn.objects.filter(user=u).last()
        if matrix:
            day_attrs = {
                '0': matrix.turn_sunday,
                '1': matrix.turn_monday,
                '2': matrix.turn_tuesday,
                '3': matrix.turn_wednesday,
                '4': matrix.turn_thursday,
                '5': matrix.turn_friday,
                '6': matrix.turn_saturday,
            }
            user_turns_map[str(u.id)] = {
                k: [t.start_time.strftime('%H:%M'), t.end_time.strftime('%H:%M')] if (t and t.start_time and t.end_time) else None
                for k, t in day_attrs.items()
            }
    return render(request, 'attendance/console_individual.html', {
        'users': users,
        'today': timezone.localdate().strftime('%Y-%m-%d'),
        'user_turns_json': json.dumps(user_turns_map),
    })


@user_passes_test(is_admin)
def console_massive(request):
    selected_date_str = request.GET.get('date', timezone.localdate().strftime('%Y-%m-%d'))
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

                    status = AttendanceStatus.A_TIEMPO.value

                    matrix = EmployeeTurn.objects.filter(user=colaborador, start_date__lte=selected_date).filter(Q(end_date__gte=selected_date) | Q(end_date__isnull=True)).first()
                    if not matrix:
                        matrix = EmployeeTurn.objects.filter(user=colaborador).last()
                    turn_of_day = matrix.get_turn_for_date(selected_date) if matrix else None

                    if entry_dt and turn_of_day and turn_of_day.start_time:
                        turn_start_datetime = timezone.make_aware(datetime.combine(selected_date, turn_of_day.start_time))
                        grace_period = turn_start_datetime + timedelta(minutes=5)
                        if entry_dt > grace_period:
                            status = AttendanceStatus.RETARDO.value

                    if entry_just and entry_just != 'NORMAL':
                        status = AttendanceStatus.A_TIEMPO.value

                    hours_worked, extra_hours, permission_hours = calculate_attendance_metrics(
                        work_date=selected_date,
                        turn=turn_of_day,
                        entry_dt=entry_dt,
                        exit_dt=exit_dt,
                        entry_justification=entry_just,
                        exit_justification=exit_just,
                        apply_exit_only_threshold=False,
                    )

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
            return redirect(f"{request.path}?date={request.POST.get('date', timezone.localdate().strftime('%Y-%m-%d'))}")

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
            'turn_start': turn_of_day.start_time.strftime('%H:%M') if (turn_of_day and turn_of_day.start_time) else '',
            'turn_end': turn_of_day.end_time.strftime('%H:%M') if (turn_of_day and turn_of_day.end_time) else '',
            'attendance': att
        })

    return render(request, 'attendance/console_massive.html', {
        'user_data': user_data,
        'selected_date': selected_date_str,
        'is_weekday': selected_date.weekday() < 5,
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

