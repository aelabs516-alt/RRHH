from django.shortcuts import render, redirect
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required

class CustomLoginView(LoginView):
    template_name = 'users/login.html'
    redirect_authenticated_user = True

from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Sum, Count, Q, F
from apps.attendance.models import Attendance, Permission, AttendanceStatus
from apps.hr.models import DisciplinaryAct

@login_required
def dashboard(request):
    user = request.user
    
    # Parámetros de filtrado
    year = request.GET.get('year')
    month = request.GET.get('month')
    day = request.GET.get('day')
    collab_id = request.GET.get('user_id')
    
    now = timezone.now()
    
    # Base queries
    att_qs = Attendance.objects.all()
    acts_qs = DisciplinaryAct.objects.all()
    
    # No admins solo ven lo suyo
    if user.role not in ['ADMIN', 'JEFE'] and not user.is_superuser:
        collab_id = user.id
        att_qs = att_qs.filter(user=user)
        acts_qs = acts_qs.filter(user=user)
        
    if year:
        att_qs = att_qs.filter(date__year=year)
        acts_qs = acts_qs.filter(date_created__year=year)
    if month:
        att_qs = att_qs.filter(date__month=month)
        acts_qs = acts_qs.filter(date_created__month=month)
    if day:
        att_qs = att_qs.filter(date__day=day)
        acts_qs = acts_qs.filter(date_created__day=day)
    if collab_id:
        att_qs = att_qs.filter(user_id=collab_id)
        acts_qs = acts_qs.filter(user_id=collab_id)
        
    # KPIs
    total_extras = att_qs.aggregate(Sum('extra_hours'))['extra_hours__sum'] or 0
    total_permisos = 0 # Necesitamos calcular horas de permiso. Podemos calcular (salida_oficial - exit_time) si salió temprano, pero Attendance no guarda 'permission_hours' explícitamente en base, aunque sí tenemos permisos aprobados.
    # En attendance, si sale temprano lo marcamos con extra_hours=0 y observations=motivo, pero no sumamos. 
    # Para hacerlo dinámico, asumimos que total_permisos viene de la diferencia de horas_trabajadas vs turno. 
    # O calculamos los permisos aprobados del modelo Permission.
    perm_qs = Permission.objects.filter(status='APROBADO')
    if user.role not in ['ADMIN', 'JEFE'] and not user.is_superuser:
        perm_qs = perm_qs.filter(user=user)
    if year: perm_qs = perm_qs.filter(start_date__year=year)
    if month: perm_qs = perm_qs.filter(start_date__month=month)
    if collab_id: perm_qs = perm_qs.filter(user_id=collab_id)
    
    # Calculo simple de horas por permisos aprobados (excluye vacaciones)
    for p in perm_qs.exclude(category='VACACIONES'):
        diff = p.end_date - p.start_date
        total_permisos += diff.total_seconds() / 3600.0

    llegadas_tarde = att_qs.filter(entry_status=AttendanceStatus.RETARDO).count()
    
    actas_firmadas = acts_qs.exclude(Q(employee_signature='') | Q(employee_signature__isnull=True)).count()
    actas_pendientes = acts_qs.filter(Q(employee_signature='') | Q(employee_signature__isnull=True)).count()
    
    # Gráficos
    # 1. Horas extras acumuladas por colaborador
    extras_por_colab = list(Attendance.objects.filter(extra_hours__gt=0).values('user__first_name', 'user__last_name').annotate(total=Sum('extra_hours')).order_by('-total')[:10])
    
    # 2. Vacaciones acumuladas por colaborador (Ley Colombiana: 15 días hábiles por cada año laborado - 360 días)
    from apps.users.models import User
    from apps.organization.models import CustomHoliday
    collabs = User.objects.filter(is_active=True)
    if user.role not in ['ADMIN', 'JEFE'] and not user.is_superuser:
        collabs = collabs.filter(id=user.id)
        
    colombian_holidays = list(CustomHoliday.objects.values_list('date', flat=True))
    vacaciones_por_colab = []
    
    for c in collabs:
        if c.hire_date:
            # Fórmula Laboral Colombiana Comercial: (Días Trabajados * 15) / 360
            days_worked = (now.date() - c.hire_date).days
            earned_vacation = (days_worked * 15) / 360.0
            
            used_working_days = 0
            # Contar SOLO días hábiles usados en vacaciones (descontando domingos y festivos)
            vacs = Permission.objects.filter(user=c, category='VACACIONES', status='APROBADO')
            for v in vacs:
                current_date = v.start_date.date()
                end_d = v.end_date.date()
                while current_date <= end_d:
                    if current_date.weekday() != 6 and current_date not in colombian_holidays:
                        used_working_days += 1
                    current_date += timedelta(days=1)
            
            balance = max(0, round(earned_vacation - used_working_days, 1))
            vacaciones_por_colab.append({'name': c.get_full_name(), 'balance': balance})
    
    # Ordenar por balance
    vacaciones_por_colab = sorted(vacaciones_por_colab, key=lambda x: x['balance'], reverse=True)[:10]

    # Panel de Auditoría: Retardos críticos (esta semana)
    start_of_week = now.date() - timedelta(days=now.date().weekday())
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    users_with_acts = DisciplinaryAct.objects.filter(date_created__gte=start_of_month).values_list('user__id', flat=True)
    
    critical_tardies = Attendance.objects.filter(
        date__gte=start_of_week, entry_status=AttendanceStatus.RETARDO
    ).exclude(user__id__in=users_with_acts).values('user__first_name', 'user__last_name', 'user__document_number').annotate(count=Count('id')).filter(count__gte=3)
    
    # Alerta de Geolocalización: Marcaciones fuera de la empresa (Hoy)
    out_of_bounds_alerts = Attendance.objects.filter(
        date=now.date(), is_out_of_bounds=True
    ).select_related('user')
    
    # Consolidado Neto (Tabla)
    net_table = []
    for c in collabs:
        c_att = att_qs.filter(user=c)
        c_extras = c_att.aggregate(Sum('extra_hours'))['extra_hours__sum'] or 0
        
        c_perms = 0
        c_pqs = perm_qs.filter(user=c).exclude(category='VACACIONES')
        for p in c_pqs:
            c_perms += (p.end_date - p.start_date).total_seconds() / 3600.0
            
        balance = c_extras - c_perms
        state = 'A favor' if balance > 0 else ('En contra' if balance < 0 else 'Al día')
        
        matrix = c.turns.last()
        turn_str = "Matriz Asignada" if matrix else "Sin Turno"
        
        net_table.append({
            'doc': c.document_number,
            'name': c.get_full_name(),
            'turn': turn_str,
            'extras': round(c_extras, 1),
            'permisos': round(c_perms, 1),
            'balance': round(balance, 1),
            'state': state
        })

    context = {
        'is_admin': user.role in ['ADMIN', 'JEFE'] or user.is_superuser,
        'users': User.objects.filter(is_active=True),
        'kpis': {
            'extras': round(total_extras, 1),
            'permisos': round(total_permisos, 1),
            'tardies': llegadas_tarde,
            'acts_signed': actas_firmadas,
            'acts_pending': actas_pendientes
        },
        'extras_chart': extras_por_colab,
        'vacs_chart': vacaciones_por_colab,
        'critical_tardies': critical_tardies,
        'out_of_bounds_alerts': out_of_bounds_alerts,
        'net_table': net_table,
        
        # Filtros seleccionados
        'f_year': year,
        'f_month': month,
        'f_day': day,
        'f_collab': collab_id,
    }
    
    return render(request, 'users/dashboard.html', context)

def custom_logout(request):
    logout(request)
    return redirect('login')

from django.views.generic import ListView, CreateView, UpdateView
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
        return ctx

from apps.organization.models import Turn, EmployeeTurn

class UserCreateView(LoginRequiredMixin, CreateView):
    model = User
    fields = ['document_number', 'first_name', 'last_name', 'role', 'position', 'area', 'manager', 'salary', 'birth_date', 'hire_date', 'emergency_contact', 'emergency_contact_number']
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users_list')
    
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
    fields = ['document_number', 'first_name', 'last_name', 'role', 'position', 'area', 'manager', 'salary', 'birth_date', 'hire_date', 'emergency_contact', 'emergency_contact_number', 'is_active']
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users_list')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar Colaborador'
        ctx['turns'] = Turn.objects.all()
        
        matrix = self.object.turns.last()
        ctx['t_monday'] = matrix.turn_monday_id if matrix else None
        ctx['t_tuesday'] = matrix.turn_tuesday_id if matrix else None
        ctx['t_wednesday'] = matrix.turn_wednesday_id if matrix else None
        ctx['t_thursday'] = matrix.turn_thursday_id if matrix else None
        ctx['t_friday'] = matrix.turn_friday_id if matrix else None
        ctx['t_saturday'] = matrix.turn_saturday_id if matrix else None
        ctx['t_sunday'] = matrix.turn_sunday_id if matrix else None
        
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
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
