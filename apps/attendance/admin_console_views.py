from datetime import datetime, date
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from apps.users.models import User
from .models import Attendance
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
        justification_type = request.POST.get('justification_type')
        observations = request.POST.get('observations')

        try:
            colaborador = User.objects.get(id=user_id)
            d = datetime.strptime(reg_date, '%Y-%m-%d').date()
            
            # Simple hours calculation since it's manual admin intervention
            entry_dt = timezone.make_aware(datetime.combine(d, datetime.strptime(entry_time, '%H:%M').time())) if entry_time else None
            exit_dt = timezone.make_aware(datetime.combine(d, datetime.strptime(exit_time, '%H:%M').time())) if exit_time else None
            
            hours_worked = 0.0
            if entry_dt and exit_dt:
                hours_worked = round((exit_dt - entry_dt).total_seconds() / 3600.0, 2)
            
            # The admin provides the extra/permission logic or it calculates? User said "visualizaran horas...". 
            # I'll calculate standard and allow override, but doing simple save is fine here.
            # To keep it simple, save basic:
            Attendance.objects.update_or_create(
                user=colaborador, date=d,
                defaults={
                    'entry_time': entry_dt,
                    'exit_time': exit_dt,
                    'hours_worked': hours_worked,
                    'justification_type': justification_type,
                    'observations': observations
                }
            )
            messages.success(request, 'Registro individual guardado correctamente.')
            return redirect('console_individual')
        except Exception as e:
            messages.error(request, f'Error: {e}')

    users = User.objects.filter(is_active=True, role='COLABORADOR')
    return render(request, 'attendance/console_individual.html', {'users': users, 'today': date.today().strftime('%Y-%m-%d')})


@user_passes_test(is_admin)
def console_massive(request):
    selected_date_str = request.GET.get('date', date.today().strftime('%Y-%m-%d'))
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    if request.method == 'POST':
        selected_date_str = request.POST.get('date')
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        user_ids = request.POST.getlist('user_ids')
        
        count = 0
        for uid in user_ids:
            entry_time = request.POST.get(f'entry_{uid}')
            exit_time = request.POST.get(f'exit_{uid}')
            just_type = request.POST.get(f'just_{uid}')
            obs = request.POST.get(f'obs_{uid}')

            if entry_time or exit_time:
                colaborador = User.objects.get(id=uid)
                entry_dt = timezone.make_aware(datetime.combine(selected_date, datetime.strptime(entry_time, '%H:%M').time())) if entry_time else None
                exit_dt = timezone.make_aware(datetime.combine(selected_date, datetime.strptime(exit_time, '%H:%M').time())) if exit_time else None
                
                hours_worked = 0.0
                if entry_dt and exit_dt:
                    hours_worked = round((exit_dt - entry_dt).total_seconds() / 3600.0, 2)
                    
                Attendance.objects.update_or_create(
                    user=colaborador, date=selected_date,
                    defaults={
                        'entry_time': entry_dt,
                        'exit_time': exit_dt,
                        'hours_worked': hours_worked,
                        'justification_type': just_type,
                        'observations': obs
                    }
                )
                count += 1
                
        messages.success(request, f'Se registraron/actualizaron {count} asistencias.')
        return redirect(f"{request.path}?date={selected_date_str}")

    users = User.objects.filter(is_active=True, role='COLABORADOR')
    
    # Enrich with today's turn
    user_data = []
    for u in users:
        # Find active turn matrix
        matrix = EmployeeTurn.objects.filter(user=u, start_date__lte=selected_date).filter(Q(end_date__gte=selected_date) | Q(end_date__isnull=True)).first()
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

