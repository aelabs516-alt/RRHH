from datetime import date
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.files.base import ContentFile
from apps.users.models import User
from .models import PayrollSlip

def is_admin(user):
    return user.is_authenticated and (user.role in ['ADMIN', 'JEFE'] or user.is_superuser)

@user_passes_test(is_admin)
def payroll_mass_upload(request):
    if request.method == 'POST':
        files = request.FILES.getlist('payroll_files')
        success_count = 0
        error_messages = []
        
        for f in files:
            # Expected format: cedula_mes_año.pdf
            filename = f.name
            name_without_ext = filename.rsplit('.', 1)[0]
            parts = name_without_ext.split('_')
            
            if len(parts) >= 3:
                document_number = parts[0]
                month_str = parts[1]
                year_str = parts[2]
                
                try:
                    user = User.objects.get(document_number=document_number)
                    # Convert to date (1st of the month)
                    slip_date = date(int(year_str), int(month_str), 1)
                    
                    # Update or Create
                    slip, created = PayrollSlip.objects.update_or_create(
                        user=user,
                        month=slip_date,
                        defaults={'document': f}
                    )
                    success_count += 1
                except User.DoesNotExist:
                    error_messages.append(f"Usuario no encontrado para documento: {document_number} ({filename})")
                except ValueError:
                    error_messages.append(f"Mes o año inválido en el archivo: {filename}")
            else:
                error_messages.append(f"Formato incorrecto (debe ser cedula_mes_año.pdf): {filename}")
        
        if success_count > 0:
            messages.success(request, f"Se cargaron {success_count} colillas exitosamente.")
        if error_messages:
            for err in error_messages:
                messages.error(request, err)
                
        return redirect('payroll_mass_upload')

    return render(request, 'hr/payroll_mass_upload.html')
