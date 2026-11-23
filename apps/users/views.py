from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required

class CustomLoginView(LoginView):
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        url = self.get_redirect_url()
        user = self.request.user
        
        from apps.hr.models import DisciplinaryAct
        from django.db.models import Q
        from django.contrib import messages
        from django.urls import reverse_lazy
        
        # Si es colaborador, revisar actas y notificaciones pendientes
        if user.role not in ['ADMIN', 'JEFE'] and not user.is_superuser:
            has_pending_acts = DisciplinaryAct.objects.filter(
                Q(employee_signature='') | Q(employee_signature__isnull=True),
                user=user
            ).exists()
            
            if has_pending_acts:
                messages.warning(self.request, "Tienes actas disciplinarias pendientes por revisar y firmar.")
                return reverse_lazy('acts_list')
                
            from apps.hr.models import VacationNotification
            has_pending_vacations = VacationNotification.objects.filter(
                Q(employee_signature='') | Q(employee_signature__isnull=True),
                user=user
            ).exists()
            
            if has_pending_vacations:
                messages.warning(self.request, "Tienes notificaciones de vacaciones pendientes por firmar.")
                return reverse_lazy('vacations_notify_list')
                
        return url or reverse_lazy('dashboard')

from django.utils import timezone
from datetime import datetime, date, timedelta
import calendar
from django.db.models import Sum, Count, Q, F
from django.shortcuts import redirect
from apps.attendance.models import Attendance, Permission, AttendanceStatus
from apps.attendance.services import (
    calculate_permission_working_hours,
    get_colombian_holidays,
    get_current_turn,
)
from apps.hr.models import DisciplinaryAct

@login_required
def dashboard(request):
    user = request.user
    is_admin = user.role in ['ADMIN', 'JEFE'] or user.is_superuser
    
    # Check for pending acts and vacations on dashboard entry for collaborators
    if not is_admin:
        has_pending_acts = DisciplinaryAct.objects.filter(
            Q(employee_signature='') | Q(employee_signature__isnull=True),
            user=user
        ).exists()
        if has_pending_acts:
            from django.contrib import messages
            messages.warning(request, "Tienes actas disciplinarias pendientes por revisar y firmar.")
            return redirect('acts_list')
            
        from apps.hr.models import VacationNotification
        has_pending_vacations = VacationNotification.objects.filter(
            Q(employee_signature='') | Q(employee_signature__isnull=True),
            user=user
        ).exists()
        if has_pending_vacations:
            from django.contrib import messages
            messages.warning(request, "Tienes notificaciones de vacaciones pendientes por firmar.")
            return redirect('vacations_notify_list')
    
    # Parámetros de filtrado
    year = request.GET.get('year')
    month = request.GET.get('month')
    day = request.GET.get('day')
    collab_id = request.GET.get('user_id') if is_admin else str(user.id)
    
    today_local = timezone.localdate()
    
    from apps.users.models import User
    
    # Base queries
    att_qs = Attendance.objects.all()
    acts_qs = DisciplinaryAct.objects.all()
    perm_qs = Permission.objects.filter(status='APROBADO', category__in=['PERSONALES', 'OTROS'])
    
    # Colaboradores visibles según perfil: no admins ven ÚNICAMENTE su propia sesión
    if not is_admin:
        collabs = User.objects.filter(id=user.id)
        att_qs = att_qs.filter(user=user)
        acts_qs = acts_qs.filter(user=user)
        perm_qs = perm_qs.filter(user=user)
    else:
        collabs = User.objects.filter(is_active=True)
        if collab_id:
            collabs = collabs.filter(id=collab_id)
            att_qs = att_qs.filter(user_id=collab_id)
            acts_qs = acts_qs.filter(user_id=collab_id)
            perm_qs = perm_qs.filter(user_id=collab_id)
    
    # Filtros de fecha (soportando input type="date" YYYY-MM-DD y año/mes)
    filter_start_date = None
    filter_end_date = None
    target_date = today_local
    
    if day:
        if '-' in day:
            try:
                specific_date = datetime.strptime(day, '%Y-%m-%d').date()
                att_qs = att_qs.filter(date=specific_date)
                acts_qs = acts_qs.filter(date_created__date=specific_date)
                filter_start_date = specific_date
                filter_end_date = specific_date
                target_date = specific_date
            except ValueError:
                pass
        else:
            try:
                day_int = int(day)
                att_qs = att_qs.filter(date__day=day_int)
                acts_qs = acts_qs.filter(date_created__day=day_int)
                if year and month:
                    specific_date = date(int(year), int(month), day_int)
                    filter_start_date = specific_date
                    filter_end_date = specific_date
                    target_date = specific_date
            except ValueError:
                pass
    else:
        year_int = None
        month_int = None
        if year:
            try:
                year_int = int(year)
                att_qs = att_qs.filter(date__year=year_int)
                acts_qs = acts_qs.filter(date_created__year=year_int)
            except ValueError:
                year_int = None
        if month:
            try:
                month_int = int(month)
                att_qs = att_qs.filter(date__month=month_int)
                acts_qs = acts_qs.filter(date_created__month=month_int)
            except ValueError:
                month_int = None

        if year_int and month_int:
            last_day_num = calendar.monthrange(year_int, month_int)[1]
            filter_start_date = date(year_int, month_int, 1)
            filter_end_date = date(year_int, month_int, last_day_num)
        elif year_int:
            filter_start_date = date(year_int, 1, 1)
            filter_end_date = date(year_int, 12, 31)
        elif month_int:
            perm_qs = perm_qs.filter(Q(start_date__month=month_int) | Q(end_date__month=month_int))

    if filter_start_date and filter_end_date:
        f_start_dt = timezone.make_aware(datetime.combine(filter_start_date, datetime.min.time()))
        f_end_dt = timezone.make_aware(datetime.combine(filter_end_date + timedelta(days=1), datetime.min.time()))
        perm_qs = perm_qs.filter(start_date__lt=f_end_dt, end_date__gt=f_start_dt)

    # Pre-cargar festivos colombianos + personalizados para evitar recálculo en bucle
    holiday_years = set(range(today_local.year - 2, today_local.year + 2))
    for p_dates in perm_qs.values_list('start_date', 'end_date'):
        if p_dates[0]:
            holiday_years.add(p_dates[0].year)
        if p_dates[1]:
            holiday_years.add(p_dates[1].year)
    colombian_holidays_set = get_colombian_holidays(holiday_years)

    # Actas KPIs
    actas_firmadas = acts_qs.exclude(Q(employee_signature='') | Q(employee_signature__isnull=True)).count()
    actas_pendientes = acts_qs.filter(Q(employee_signature='') | Q(employee_signature__isnull=True)).count()

    # Consolidado Neto, KPIs Netos (Extras y Permisos) y Gráfica de Balance Neto
    # Fuente única de verdad: calcula por colaborador (Extras - Permisos en horario laboral sin almuerzo)
    net_table = []
    extras_por_colab = []
    net_total_extras = 0.0
    net_total_permisos = 0.0

    for c in collabs:
        c_att = att_qs.filter(user=c)
        c_extras = float(c_att.aggregate(Sum('extra_hours'))['extra_hours__sum'] or 0)

        c_perms = 0.0
        perm_details = []
        c_pqs = perm_qs.filter(user=c).order_by('-start_date')
        for p in c_pqs:
            p_hours = calculate_permission_working_hours(
                c,
                p.start_date,
                p.end_date,
                filter_start_date=filter_start_date,
                filter_end_date=filter_end_date,
                holidays_set=colombian_holidays_set,
            )
            c_perms += p_hours
            if p_hours > 0:
                p_start_loc = timezone.localtime(p.start_date)
                p_end_loc = timezone.localtime(p.end_date)
                date_label = (
                    p_start_loc.strftime('%Y-%m-%d')
                    if p_start_loc.date() == p_end_loc.date()
                    else f"{p_start_loc.strftime('%Y-%m-%d')} a {p_end_loc.strftime('%Y-%m-%d')}"
                )
                perm_details.append({
                    'date': date_label,
                    'status': p.get_category_display(),
                    'extra': 0,
                    'permission': round(p_hours, 2),
                    'entry': p_start_loc.strftime('%H:%M'),
                    'exit': p_end_loc.strftime('%H:%M'),
                })

        c_early = float(c_att.aggregate(Sum('permission_hours'))['permission_hours__sum'] or 0)
        c_perms += c_early

        balance = round(c_extras - c_perms, 2)
        state = 'A favor' if balance > 0 else ('En contra' if balance < 0 else 'Al día')

        # Acumular balance neto para tarjetas KPI
        if balance > 0:
            net_total_extras += balance
        elif balance < 0:
            net_total_permisos += abs(balance)

        # Gráfica de Balance Neto:
        # - Colaborador (o admin filtrando 1 colaborador): siempre muestra únicamente esa sesión/persona
        # - Admin viendo todos: muestra el acumulado neto de los colaboradores con saldo neto != 0
        if (not is_admin) or collab_id:
            extras_por_colab.append({
                'user__first_name': c.first_name,
                'user__last_name': c.last_name,
                'total': round(balance, 1),
            })
        elif round(balance, 1) != 0:
            extras_por_colab.append({
                'user__first_name': c.first_name,
                'user__last_name': c.last_name,
                'total': round(balance, 1),
            })

        matrix = c.turns.last()
        turn_str = "Matriz Asignada" if matrix else "Sin Turno"

        details = []
        for att in c_att.filter(Q(extra_hours__gt=0) | Q(permission_hours__gt=0) | Q(entry_status='RETARDO')).order_by('-date'):
            details.append({
                'date': att.date.strftime('%Y-%m-%d'),
                'status': att.get_entry_status_display() if att.entry_status else 'A Tiempo',
                'extra': att.extra_hours,
                'permission': att.permission_hours,
                'entry': timezone.localtime(att.entry_time).strftime('%H:%M') if att.entry_time else '-',
                'exit': timezone.localtime(att.exit_time).strftime('%H:%M') if att.exit_time else '-'
            })
        details.extend(perm_details)

        net_table.append({
            'doc': c.document_number,
            'name': c.get_full_name(),
            'turn': turn_str,
            'extras': round(c_extras, 1),
            'permisos': round(c_perms, 1),
            'balance': round(balance, 1),
            'state': state,
            'details': details
        })

    extras_por_colab = sorted(extras_por_colab, key=lambda x: x['total'], reverse=True)[:15]

    # 2. Vacaciones acumuladas por colaborador (Ley Colombiana: 15 días hábiles por cada año laborado - 360 días)
    vacaciones_por_colab = []
    for c in collabs:
        if c.hire_date:
            # Fórmula Laboral Colombiana Comercial: (Días Trabajados * 15) / 360
            days_worked = (today_local - c.hire_date).days
            earned_vacation = (days_worked * 15) / 360.0

            used_working_days = 0
            # Contar SOLO días hábiles usados en vacaciones (descontando domingos y festivos)
            vacs = Permission.objects.filter(user=c, category='VACACIONES', status='APROBADO')
            for v in vacs:
                current_date = timezone.localtime(v.start_date).date()
                end_d = timezone.localtime(v.end_date).date()
                while current_date <= end_d:
                    if current_date.weekday() != 6 and current_date not in colombian_holidays_set:
                        used_working_days += 1
                    current_date += timedelta(days=1)

            # También descontar los días de Notificaciones de Vacaciones firmadas
            from apps.hr.models import VacationNotification
            vac_notifs = VacationNotification.objects.filter(user=c).exclude(Q(employee_signature='') | Q(employee_signature__isnull=True))
            for vn in vac_notifs:
                used_working_days += vn.days_enjoyed

            balance_vac = max(0, round(earned_vacation - used_working_days, 1))
            vacaciones_por_colab.append({'name': c.get_full_name(), 'balance': balance_vac})

    vacaciones_por_colab = sorted(vacaciones_por_colab, key=lambda x: x['balance'], reverse=True)[:10]

    # Panel de Auditoría: Retardos pendientes por generar acta (ventana móvil de 30 días calendario)
    critical_tardies = []
    thirty_days_ago = today_local - timedelta(days=30)

    users_with_tardies = collabs.filter(
        attendances__entry_status=AttendanceStatus.RETARDO,
        attendances__date__gte=thirty_days_ago
    ).distinct()

    for u in users_with_tardies:
        latest_act = DisciplinaryAct.objects.filter(user=u).order_by('-date_created').first()

        tardies_qs = Attendance.objects.filter(
            user=u,
            entry_status=AttendanceStatus.RETARDO,
            date__gte=thirty_days_ago
        )

        if latest_act:
            tardies_count = tardies_qs.filter(
                Q(entry_time__gt=latest_act.date_created) |
                Q(entry_time__isnull=True, date__gt=latest_act.date_created.date())
            ).count()
        else:
            tardies_count = tardies_qs.count()

        if tardies_count > 0:
            critical_tardies.append({
                'user__first_name': u.first_name,
                'user__last_name': u.last_name,
                'user__document_number': u.document_number,
                'count': tardies_count
            })

    critical_tardies.sort(key=lambda x: x['count'], reverse=True)

    # KPI LLEGADAS TARDE: relacionar ÚNICAMENTE las llegadas tarde vigentes en el Panel de Auditoría
    llegadas_tarde = sum(ct['count'] for ct in critical_tardies)

    # Alerta de Geolocalización: Marcaciones fuera de la empresa (Hoy) - solo para administradores
    if is_admin:
        out_of_bounds_alerts = Attendance.objects.filter(
            date=today_local, is_out_of_bounds=True
        ).select_related('user')
        if collab_id:
            out_of_bounds_alerts = out_of_bounds_alerts.filter(user_id=collab_id)
    else:
        out_of_bounds_alerts = Attendance.objects.none()

    # Calcular ausencias (Faltas o no llegadas) para la fecha seleccionada o hoy - solo para administradores
    absencias_hoy = []
    if is_admin:
        for c in collabs:
            turn = get_current_turn(c, target_date)
            if turn:
                if not Attendance.objects.filter(user=c, date=target_date, entry_time__isnull=False).exists():
                    has_perm = False
                    for p in Permission.objects.filter(user=c, status='APROBADO'):
                        p_s = timezone.localtime(p.start_date).date()
                        p_e = timezone.localtime(p.end_date).date()
                        if p_s <= target_date <= p_e:
                            has_perm = True
                            break
                    if not has_perm:
                        absencias_hoy.append({'name': c.get_full_name(), 'turn': f"{turn.start_time.strftime('%H:%M')} - {turn.end_time.strftime('%H:%M')}"})

    context = {
        'is_admin': is_admin,
        'users': User.objects.filter(is_active=True) if is_admin else User.objects.filter(id=user.id),
        'kpis': {
            'extras': round(net_total_extras, 1),
            'permisos': round(net_total_permisos, 1),
            'tardies': llegadas_tarde,
            'acts_signed': actas_firmadas,
            'acts_pending': actas_pendientes
        },
        'extras_chart': extras_por_colab,
        'vacs_chart': vacaciones_por_colab,
        'critical_tardies': critical_tardies,
        'out_of_bounds_alerts': out_of_bounds_alerts,
        'absencias_hoy': absencias_hoy,
        'net_table': net_table,
        
        # Filtros seleccionados
        'f_year': year,
        'f_month': month,
        'f_day': day,
        'f_collab': collab_id if is_admin else None,
        'target_date_str': target_date.strftime('%Y-%m-%d'),
    }
    
    return render(request, 'users/dashboard.html', context)

def custom_logout(request):
    logout(request)
    return redirect('login')

from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import User

class UserListView(LoginRequiredMixin, ListView):
    model = User
    template_name = 'crud/list.html'
    context_object_name = 'objects'
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Colaboradores'
        ctx['headers'] = ['Documento', 'Nombre', 'Rol', 'Cargo', 'Estado']
        ctx['create_url'] = 'users_create'
        ctx['update_url'] = 'users_update'
        ctx['delete_url_name'] = 'users_delete'
        return ctx

class UserDeleteView(LoginRequiredMixin, DeleteView):
    model = User
    template_name = 'crud/confirm_delete.html'
    success_url = reverse_lazy('users_list')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Eliminar Colaborador'
        ctx['cancel_url'] = reverse_lazy('users_list')
        return ctx

    def get_queryset(self):
        # Evitar que puedan eliminar a un superusuario desde la interfaz
        return super().get_queryset().exclude(is_superuser=True)

from apps.organization.models import Turn, EmployeeTurn

class UserCreateView(LoginRequiredMixin, CreateView):
    model = User
    fields = ['document_number', 'first_name', 'last_name', 'role', 'position', 'area', 'manager', 'salary', 'birth_date', 'hire_date', 'emergency_contact', 'emergency_contact_number', 'signature']
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users_list')
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        from django import forms
        form.fields['birth_date'].widget = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
        form.fields['hire_date'].widget = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Crear Colaborador'
        ctx['turns'] = Turn.objects.all()
        ctx['days_of_week'] = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        ctx['current_turns'] = {}
        return ctx

    def form_valid(self, form):
        # We intercept the save to set the password
        user = form.save(commit=False)
        # If no password is set, use document_number as default password
        if not user.password:
            user.set_password(user.document_number)
            
        import base64
        from django.core.files.base import ContentFile
        from django.utils import timezone
        
        signature_b64 = self.request.POST.get('signature_base64')
        if signature_b64:
            format, imgstr = signature_b64.split(';base64,')
            ext = format.split('/')[-1]
            user.signature.save(f"sign_{user.document_number}_{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}", ContentFile(base64.b64decode(imgstr)), save=False)
            
        user.save()
        self.object = user
        
        # Save M2M if needed (not in this form, but standard practice)
        form.save_m2m()
        
        matrix = EmployeeTurn(user=user)
        matrix.turn_monday_id = self.request.POST.get('turn_monday') or None
        matrix.turn_tuesday_id = self.request.POST.get('turn_tuesday') or None
        matrix.turn_wednesday_id = self.request.POST.get('turn_wednesday') or None
        matrix.turn_thursday_id = self.request.POST.get('turn_thursday') or None
        matrix.turn_friday_id = self.request.POST.get('turn_friday') or None
        matrix.turn_saturday_id = self.request.POST.get('turn_saturday') or None
        matrix.turn_sunday_id = self.request.POST.get('turn_sunday') or None
        matrix.save()
        return redirect(self.success_url)

class UserUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    fields = ['document_number', 'first_name', 'last_name', 'role', 'position', 'area', 'manager', 'salary', 'birth_date', 'hire_date', 'emergency_contact', 'emergency_contact_number', 'signature', 'is_active']
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users_list')
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        from django import forms
        form.fields['birth_date'].widget = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
        form.fields['hire_date'].widget = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar Colaborador'
        ctx['turns'] = Turn.objects.all()
        
        matrix = self.object.turns.last()
        ctx['current_turns'] = {
            'monday': matrix.turn_monday_id if matrix else None,
            'tuesday': matrix.turn_tuesday_id if matrix else None,
            'wednesday': matrix.turn_wednesday_id if matrix else None,
            'thursday': matrix.turn_thursday_id if matrix else None,
            'friday': matrix.turn_friday_id if matrix else None,
            'saturday': matrix.turn_saturday_id if matrix else None,
            'sunday': matrix.turn_sunday_id if matrix else None,
        }
        
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        
        import base64
        from django.core.files.base import ContentFile
        from django.utils import timezone
        
        signature_b64 = self.request.POST.get('signature_base64')
        if signature_b64:
            format, imgstr = signature_b64.split(';base64,')
            ext = format.split('/')[-1]
            user.signature.save(f"sign_{user.document_number}_{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}", ContentFile(base64.b64decode(imgstr)), save=True)
            
        matrix = user.turns.last()
        if not matrix:
            matrix = EmployeeTurn(user=user)
        matrix.turn_monday_id = self.request.POST.get('turn_monday') or None
        matrix.turn_tuesday_id = self.request.POST.get('turn_tuesday') or None
        matrix.turn_wednesday_id = self.request.POST.get('turn_wednesday') or None
        matrix.turn_thursday_id = self.request.POST.get('turn_thursday') or None
        matrix.turn_friday_id = self.request.POST.get('turn_friday') or None
        matrix.turn_saturday_id = self.request.POST.get('turn_saturday') or None
        matrix.turn_sunday_id = self.request.POST.get('turn_sunday') or None
        matrix.save()
        return response
