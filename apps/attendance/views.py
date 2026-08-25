import json
import base64
from django.core.files.base import ContentFile
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from .services import process_entry, process_exit

@login_required
def mark_attendance(request):
    """Renderiza la interfaz de marcación web con la cámara."""
    user = request.user
    if user.role not in ['ADMIN', 'JEFE'] and not user.is_superuser:
        from apps.hr.models import DisciplinaryAct
        from django.db.models import Q
        from django.shortcuts import redirect
        has_pending = DisciplinaryAct.objects.filter(
            Q(employee_signature='') | Q(employee_signature__isnull=True),
            user=user
        ).exists()
        if has_pending:
            from django.contrib import messages
            messages.warning(request, "Debes firmar tus actas disciplinarias pendientes antes de marcar asistencia.")
            return redirect('acts_list')
            
    return render(request, 'attendance/mark.html')

@login_required
def process_attendance_api(request):
    """Recibe el POST de la cámara (foto en base64 y tipo de marcación)."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action') # 'ingreso' o 'salida'
            photo_data = data.get('photo')
            observations = data.get('observations', '')
            
            photo_file = None
            if photo_data:
                format, imgstr = photo_data.split(';base64,')
                ext = format.split('/')[-1]
                photo_file = ContentFile(base64.b64decode(imgstr), name=f"{request.user.document_number}_{timezone.now().strftime('%Y%m%d%H%M%S')}.{ext}")
            
            lat = data.get('lat')
            lng = data.get('lng')
            
            current_time = timezone.now()
            
            if action == 'ingreso':
                att, status, act = process_entry(request.user, current_time, photo=photo_file, lat=lat, lng=lng)
                msg = f"Ingreso registrado: {status}"
                if act:
                    if act == "ALERTA_CRITICA":
                        msg += ". ALERTA: 3er retardo en la semana."
                    else:
                        msg += f". Se generó Acta: {act.get_severity_display()}."
                        
                return JsonResponse({'status': 'success', 'message': msg})
                
            elif action == 'salida':
                try:
                    att = process_exit(request.user, current_time, observations=observations, photo=photo_file, lat=lat, lng=lng)
                    msg = f"Salida registrada. Horas trabajadas: {att.hours_worked}."
                    if att.extra_hours > 0:
                        msg += f" Horas extras: {att.extra_hours}."
                    return JsonResponse({'status': 'success', 'message': msg})
                except ValueError as e:
                    # Este catch maneja las observaciones obligatorias si hay horas extras
                    return JsonResponse({'status': 'error', 'message': str(e), 'require_observations': True})
            else:
                return JsonResponse({'status': 'error', 'message': 'Acción inválida.'})
                
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'})

from apps.users.models import User
from .models import Attendance
from django.db.models import Q
from django.core.serializers.json import DjangoJSONEncoder

@login_required
def attendance_map(request):
    """Renderiza el mapa de marcaciones."""
    if request.user.role not in ['ADMIN', 'JEFE'] and not request.user.is_superuser:
        return render(request, '403.html') # Or handle unauthorized properly
        
    date_filter = request.GET.get('date', timezone.now().date().strftime('%Y-%m-%d'))
    user_id = request.GET.get('user_id', '')
    
    attendances = Attendance.objects.filter(
        date=date_filter,
        latitude__isnull=False,
        longitude__isnull=False
    ).select_related('user')
    
    if user_id:
        attendances = attendances.filter(user_id=user_id)
        
    # Serialize for JS
    markers = []
    for att in attendances:
        entry_time_str = att.entry_time.astimezone(timezone.get_current_timezone()).strftime('%H:%M') if att.entry_time else 'N/A'
        exit_time_str = att.exit_time.astimezone(timezone.get_current_timezone()).strftime('%H:%M') if att.exit_time else 'N/A'
        
        markers.append({
            'lat': float(att.latitude),
            'lng': float(att.longitude),
            'name': att.user.get_full_name(),
            'doc': att.user.document_number,
            'entry': entry_time_str,
            'exit': exit_time_str,
            'out_of_bounds': att.is_out_of_bounds
        })
        
    from apps.organization.models import CompanySettings
    settings = CompanySettings.get_settings()
    
    context = {
        'date_filter': date_filter,
        'user_id': user_id,
        'users': User.objects.filter(is_active=True),
        'markers_json': json.dumps(markers, cls=DjangoJSONEncoder),
        'company_lat': float(settings.latitude),
        'company_lng': float(settings.longitude),
        'company_radius': settings.tolerance_radius
    }
    return render(request, 'attendance/map.html', context)

@login_required
def update_company_location(request):
    """Actualiza la latitud y longitud de la sede principal."""
    if request.user.role not in ['ADMIN', 'JEFE'] and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'No autorizado.'}, status=403)
        
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            lat = data.get('lat')
            lng = data.get('lng')
            radius = data.get('radius')
            
            from apps.organization.models import CompanySettings
            settings = CompanySettings.get_settings()
            updated = False
            
            if lat is not None and lng is not None:
                settings.latitude = lat
                settings.longitude = lng
                updated = True
                
            if radius is not None:
                settings.tolerance_radius = int(radius)
                updated = True
                
            if updated:
                settings.save()
                return JsonResponse({'status': 'success', 'message': 'Configuración de la empresa actualizada correctamente.'})
                
            return JsonResponse({'status': 'error', 'message': 'No se enviaron datos para actualizar.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'})
