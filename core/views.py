from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.http import JsonResponse, HttpResponseForbidden
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from apps.organization.models import Turn, CustomHoliday, Area, Position
from apps.attendance.models import Permission
from apps.hr.models import DisciplinaryAct, PayrollSlip

import holidays as pyholidays

def get_holidays_api(request):
    import datetime
    year = datetime.date.today().year
    
    # Obtener festivos de Colombia usando la librería (año actual y el próximo)
    co_holidays = pyholidays.CO(years=[year, year + 1])
    holiday_dates = [date_obj.strftime('%Y-%m-%d') for date_obj in co_holidays.keys()]
    
    # Agregar festivos personalizados de la base de datos (si existen)
    db_holidays = CustomHoliday.objects.values_list('date', flat=True)
    for h in db_holidays:
        date_str = h.strftime('%Y-%m-%d')
        if date_str not in holiday_dates:
            holiday_dates.append(date_str)
            
    return JsonResponse({'holidays': holiday_dates})

# -- ÁREAS --
class AreaListView(LoginRequiredMixin, ListView):
    model = Area
    template_name = 'crud/list.html'
    context_object_name = 'objects'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'], ctx['headers'] = 'Áreas', ['Nombre', 'Descripción']
        ctx['create_url'], ctx['update_url'] = 'areas_create', 'areas_update'
        return ctx

class AreaCreateView(LoginRequiredMixin, CreateView):
    model = Area
    fields = ['name', 'description']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('areas_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Crear Área'
        return ctx

class AreaUpdateView(LoginRequiredMixin, UpdateView):
    model = Area
    fields = ['name', 'description']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('areas_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar Área'
        return ctx

# -- CARGOS --
class PositionListView(LoginRequiredMixin, ListView):
    model = Position
    template_name = 'crud/list.html'
    context_object_name = 'objects'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'], ctx['headers'] = 'Cargos', ['Nombre', 'Área', 'Descripción']
        ctx['create_url'], ctx['update_url'] = 'positions_create', 'positions_update'
        return ctx

class PositionCreateView(LoginRequiredMixin, CreateView):
    model = Position
    fields = ['name', 'area', 'description']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('positions_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Crear Cargo'
        return ctx

class PositionUpdateView(LoginRequiredMixin, UpdateView):
    model = Position
    fields = ['name', 'area', 'description']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('positions_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar Cargo'
        return ctx

# -- FESTIVOS --
class HolidayListView(LoginRequiredMixin, ListView):
    model = CustomHoliday
    template_name = 'crud/list.html'
    context_object_name = 'objects'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'], ctx['headers'] = 'Festivos Personalizados', ['Fecha', 'Nombre / Motivo']
        ctx['create_url'], ctx['update_url'] = 'holidays_create', 'holidays_update'
        return ctx

class HolidayCreateView(LoginRequiredMixin, CreateView):
    model = CustomHoliday
    fields = ['date', 'name']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('holidays_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Añadir Festivo'
        return ctx

class HolidayUpdateView(LoginRequiredMixin, UpdateView):
    model = CustomHoliday
    fields = ['date', 'name']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('holidays_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar Festivo'
        return ctx

# -- TURNOS --
class TurnListView(LoginRequiredMixin, ListView):
    model = Turn
    template_name = 'crud/list.html'
    context_object_name = 'objects'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'], ctx['headers'] = 'Turnos', ['Código', 'Nombre', 'Hora Inicio', 'Hora Fin']
        ctx['create_url'], ctx['update_url'] = 'turns_create', 'turns_update'
        return ctx

class TurnCreateView(LoginRequiredMixin, CreateView):
    model = Turn
    fields = ['code', 'name', 'start_time', 'end_time']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('turns_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Crear Turno'
        return ctx

class TurnUpdateView(LoginRequiredMixin, UpdateView):
    model = Turn
    fields = ['code', 'name', 'start_time', 'end_time']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('turns_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar Turno'
        return ctx

# -- PERMISOS --
class PermissionListView(LoginRequiredMixin, ListView):
    model = Permission
    template_name = 'crud/list.html'
    context_object_name = 'objects'
    
    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role not in ['ADMIN', 'JEFE'] and not self.request.user.is_superuser:
            qs = qs.filter(user=self.request.user)
            
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(user__document_number__icontains=q)
        return qs
        
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'], ctx['headers'] = 'Permisos y Vacaciones', ['Documento', 'Colaborador', 'Categoría', 'F. Inicio', 'F. Fin', 'Estado']
        ctx['create_url'] = 'permissions_create'
        ctx['pdf_url_name'] = 'permission_pdf'
        
        if self.request.user.role in ['ADMIN', 'JEFE'] or self.request.user.is_superuser:
            ctx['update_url'] = 'permissions_update'
            ctx['search_enabled'] = True
            ctx['delete_url_name'] = 'permissions_delete'
            
        return ctx

class PermissionCreateView(LoginRequiredMixin, CreateView):
    model = Permission
    fields = ['user', 'category', 'start_date', 'end_date', 'days_requested', 'reason']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('permissions_list')
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        from django import forms
        form.fields['start_date'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})
        form.fields['end_date'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})
        if self.request.user.role not in ['ADMIN', 'JEFE'] and not self.request.user.is_superuser:
            form.fields['user'].queryset = User.objects.filter(id=self.request.user.id)
            form.fields['user'].initial = self.request.user
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Crear Solicitud de Permiso'
        return ctx

class PermissionUpdateView(LoginRequiredMixin, UpdateView):
    model = Permission
    fields = ['user', 'category', 'start_date', 'end_date', 'days_requested', 'reason', 'status', 'admin_observations']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('permissions_list')
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        from django import forms
        form.fields['start_date'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})
        form.fields['end_date'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})
        if self.request.user.role not in ['ADMIN', 'JEFE'] and not self.request.user.is_superuser:
            form.fields['user'].queryset = User.objects.filter(id=self.request.user.id)
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar/Aprobar Permiso'
        return ctx

class PermissionDeleteView(LoginRequiredMixin, DeleteView):
    model = Permission
    template_name = 'crud/confirm_delete.html'
    success_url = reverse_lazy('permissions_list')
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Eliminar Solicitud de Permiso'
        ctx['cancel_url'] = reverse_lazy('permissions_list')
        return ctx

# -- ACTAS DISCIPLINARIAS --
class ActListView(LoginRequiredMixin, ListView):
    model = DisciplinaryAct
    template_name = 'crud/list.html'
    context_object_name = 'objects'
    
    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role not in ['ADMIN', 'JEFE'] and not self.request.user.is_superuser:
            qs = qs.filter(user=self.request.user)
        
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(user__document_number__icontains=q)
        return qs
        
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'], ctx['headers'] = 'Actas Disciplinarias', ['Documento', 'Colaborador', 'Gravedad', 'Fecha', 'Decisión']
        if self.request.user.role in ['ADMIN', 'JEFE'] or self.request.user.is_superuser:
            ctx['create_url'] = 'acts_create'
            ctx['search_enabled'] = True
            ctx['delete_url_name'] = 'acts_delete'
        else:
            ctx['create_url'] = None
            ctx['search_enabled'] = False
        ctx['update_url'] = 'acts_update'
        ctx['pdf_url_name'] = 'act_pdf'
        return ctx

class ActCreateView(LoginRequiredMixin, CreateView):
    model = DisciplinaryAct
    fields = ['user', 'severity', 'description', 'employee_defense', 'decision']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('acts_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Crear Acta Disciplinaria'
        return ctx

    def form_valid(self, form):
        # Attach the manager's signature
        user_obj = form.cleaned_data.get('user')
        if user_obj and user_obj.manager and user_obj.manager.signature:
            form.instance.manager_signature = user_obj.manager.signature
        elif self.request.user.signature:
            form.instance.manager_signature = self.request.user.signature
        return super().form_valid(form)

class ActUpdateView(LoginRequiredMixin, UpdateView):
    model = DisciplinaryAct
    fields = ['employee_defense']
    template_name = 'hr/act_sign_form.html'
    success_url = reverse_lazy('acts_list')
    
    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.role not in ['ADMIN', 'JEFE'] and not self.request.user.is_superuser:
            qs = qs.filter(user=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Proceso Disciplinario (Firma)'
        return ctx
        
    def form_valid(self, form):
        signature_data = self.request.POST.get('signature_base64')
        if signature_data and ';base64,' in signature_data:
            import base64
            from django.core.files.base import ContentFile
            format, imgstr = signature_data.split(';base64,')
            ext = format.split('/')[-1]
            data = ContentFile(base64.b64decode(imgstr), name=f'firma_colaborador_{self.object.id}.{ext}')
            form.instance.employee_signature = data
        return super().form_valid(form)

class ActDeleteView(LoginRequiredMixin, DeleteView):
    model = DisciplinaryAct
    template_name = 'crud/confirm_delete.html'
    success_url = reverse_lazy('acts_list')
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.role not in ['ADMIN', 'JEFE'] and not request.user.is_superuser:
            return HttpResponseForbidden("No tienes permiso para eliminar actas.")
        return super().dispatch(request, *args, **kwargs)

from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from apps.users.models import User
from apps.hr.models import FaultSeverity
from apps.attendance.models import Attendance, AttendanceStatus

@login_required
def acts_auto_generate(request, doc_number):
    user_obj = get_object_or_404(User, document_number=doc_number)
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    tardies = Attendance.objects.filter(
        user=user_obj, date__gte=start_of_month, date__lte=now.date(), entry_status=AttendanceStatus.RETARDO
    ).order_by('date')
    
    count = tardies.count()
    if count <= 4:
        severity = FaultSeverity.LEVE
    elif count == 5:
        severity = FaultSeverity.GRAVE
    else:
        severity = FaultSeverity.MUY_GRAVE
        
    dates_str = ", ".join([f"{t.date.strftime('%d/%m/%Y')} - {t.entry_time.astimezone(timezone.get_current_timezone()).strftime('%H:%M')}" for t in tardies if t.entry_time])
    
    description = (
        f"El colaborador durante el mes, registró llegadas tardías en las siguientes fechas, con hora de ingreso: "
        f"[{dates_str}].\n\n"
        "Lo anterior evidencia una conducta reiterada de incumplimiento del horario laboral "
        "establecido por la empresa, situación que ha sido previamente informada al colaborador."
    )
    
    act = DisciplinaryAct.objects.create(
        user=user_obj,
        severity=severity,
        description=description,
        decision="Llamado de atención escrito"
    )
    
    if user_obj.manager and user_obj.manager.signature:
        act.manager_signature = user_obj.manager.signature
        act.save()
        
    messages.success(request, f"Acta generada y enviada a {user_obj.get_full_name()} para su firma.")
    return redirect('dashboard')

# -- NÓMINA --
class PayrollListView(LoginRequiredMixin, ListView):
    model = PayrollSlip
    template_name = 'crud/list.html'
    context_object_name = 'objects'
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'], ctx['headers'] = 'Colillas de Nómina', ['Documento', 'Colaborador', 'Mes', 'Archivo']
        ctx['create_url'], ctx['update_url'] = 'payroll_create', 'payroll_update'
        return ctx

class PayrollCreateView(LoginRequiredMixin, CreateView):
    model = PayrollSlip
    fields = ['user', 'month', 'document']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('payroll_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Subir Colilla de Nómina'
        return ctx

class PayrollUpdateView(LoginRequiredMixin, UpdateView):
    model = PayrollSlip
    fields = ['user', 'month', 'document']
    template_name = 'crud/form.html'
    success_url = reverse_lazy('payroll_list')
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Editar Colilla de Nómina'
        return ctx
