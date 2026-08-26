from datetime import date
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.users.models import User
from .models import PayrollSlip
from django.template.loader import render_to_string

import io
import os
from django.conf import settings
try:
    from xhtml2pdf import pisa
    XHTML2PDF_AVAILABLE = True
except ImportError:
    XHTML2PDF_AVAILABLE = False
    print("Warning: xhtml2pdf is missing.")

def link_callback(uri, rel):
    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    elif uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.BASE_DIR, 'static', uri.replace(settings.STATIC_URL, ""))
    else:
        return uri
    
    if not os.path.isfile(path):
        # Fallback
        return uri
    return path

@login_required
def certificate_labor(request):
    if request.method == 'POST':
        # Admin can submit any doc, user can only submit their own
        doc = request.POST.get('document_number')
        if request.user.role in ['ADMIN', 'JEFE'] or request.user.is_superuser:
            pass # Use the submitted doc
        else:
            doc = request.user.document_number

        include_salary = request.POST.get('include_salary') == 'on'

        def num_to_words(n):
            unidades = ['', 'un', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
            decenas = ['', 'diez', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
            dieces = ['diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciseis', 'diecisiete', 'dieciocho', 'diecinueve']
            veintes = ['veinte', 'veintiuno', 'veintidos', 'veintitres', 'veinticuatro', 'veinticinco', 'veintiseis', 'veintisiete', 'veintiocho', 'veintinueve']
            centenas = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos', 'novecientos']
            
            def convert_999(num):
                if num == 100: return 'cien'
                c = num // 100
                r = num % 100
                res = centenas[c]
                if r > 0:
                    if res: res += ' '
                    if r < 10: res += unidades[r]
                    elif r < 20: res += dieces[r-10]
                    elif r < 30: res += veintes[r-20]
                    else:
                        d = r // 10
                        u = r % 10
                        res += decenas[d]
                        if u > 0: res += ' y ' + unidades[u]
                return res
            if n == 0: return 'cero'
            millones = n // 1000000
            miles = (n % 1000000) // 1000
            resto = n % 1000
            words = []
            if millones > 0:
                if millones == 1: words.append('un millón')
                else: words.append(convert_999(millones) + ' millones')
            if miles > 0:
                if miles == 1: words.append('mil')
                else: words.append(convert_999(miles) + ' mil')
            if resto > 0:
                words.append(convert_999(resto))
            return ' '.join(words)

        MONTHS = ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

        try:
            colaborador = User.objects.get(document_number=doc)
            today = date.today()
            
            directed_to = request.POST.get('directed_to', 'A QUIEN INTERESE')
            if not directed_to.strip():
                directed_to = 'A QUIEN INTERESE'
            
            hire_day_words = num_to_words(colaborador.hire_date.day) if colaborador.hire_date else ''
            hire_month = MONTHS[colaborador.hire_date.month] if colaborador.hire_date else ''
            hire_year = str(colaborador.hire_date.year) if colaborador.hire_date else ''
            
            today_day_words = num_to_words(today.day)
            today_month = MONTHS[today.month]
            
            salary = int(colaborador.salary) if colaborador.salary else 0
            salary_words = num_to_words(salary)
            salary_formatted = f"{salary:,}".replace(',', '.')
            
            context = {
                'user': colaborador,
                'directed_to': directed_to,
                'include_salary': include_salary,
                'today': today,
                'today_day_words': today_day_words,
                'today_month': today_month,
                'hire_day_words': hire_day_words,
                'hire_month': hire_month,
                'hire_year': hire_year,
                'salary': salary,
                'salary_words': salary_words,
                'salary_formatted': salary_formatted,
                'logo_url': request.build_absolute_uri('/static/img/logo.png'),
            }
            
            if XHTML2PDF_AVAILABLE:
                html_string = render_to_string('hr/pdf/labor_certificate.html', context)
                
                # Create a file-like buffer to receive PDF data.
                buffer = io.BytesIO()
                
                # Create PDF
                pisa_status = pisa.CreatePDF(
                    html_string, dest=buffer, link_callback=link_callback
                )
                
                if pisa_status.err:
                    messages.error(request, 'Hubo un error generando el PDF.')
                    return render(request, 'hr/certificate_labor.html')
                    
                response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="Constancia_{doc}.pdf"'
                return response
            else:
                messages.error(request, 'El generador de PDF (xhtml2pdf) no está instalado en este servidor.')
                return render(request, 'hr/certificate_labor.html')
            
        except User.DoesNotExist:
            messages.error(request, 'Usuario no encontrado.')

    return render(request, 'hr/certificate_labor.html')


@login_required
def download_payroll(request):
    if request.method == 'POST':
        doc = request.POST.get('document_number')
        if request.user.role in ['ADMIN', 'JEFE'] or request.user.is_superuser:
            pass 
        else:
            doc = request.user.document_number
            
        month_str = request.POST.get('month') # expected YYYY-MM
        if month_str:
            y, m = month_str.split('-')
            try:
                slip_date = date(int(y), int(m), 1)
                colaborador = User.objects.get(document_number=doc)
                slip = PayrollSlip.objects.get(user=colaborador, month=slip_date)
                
                # We could redirect to slip.document.url or return it as attachment
                response = HttpResponse(slip.document.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="Nomina_{doc}_{month_str}.pdf"'
                return response
                
            except User.DoesNotExist:
                messages.error(request, 'Usuario no encontrado.')
            except PayrollSlip.DoesNotExist:
                messages.error(request, f'No hay colilla de pago para el periodo {month_str}.')
        else:
            messages.error(request, 'Debe seleccionar un mes válido.')

    return render(request, 'hr/download_payroll.html')

from django.shortcuts import get_object_or_404
from apps.hr.models import DisciplinaryAct

@login_required
def download_act_pdf(request, pk):
    act = get_object_or_404(DisciplinaryAct, pk=pk)
    
    # Security: only admins/jefes or the owner can download
    if request.user.role not in ['ADMIN', 'JEFE'] and not request.user.is_superuser:
        if act.user != request.user:
            return HttpResponse("No tienes permiso para descargar esta acta.", status=403)
            
    context = {'act': act}
    
    html = render_to_string('hr/pdf/disciplinary_act.html', context, request=request)
    
    response = HttpResponse(content_type='application/pdf')
    filename = f'Acta_Disciplinaria_{act.user.document_number}_{act.date_created.strftime("%Y%m%d")}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=link_callback)
    
    if pisa_status.err:
        return HttpResponse('Error generando PDF', status=500)
    return response

from apps.attendance.models import Permission

@login_required
def download_permission_pdf(request, pk):
    try:
        perm = get_object_or_404(Permission, pk=pk)
        
        # Security: only admins/jefes or the owner can download
        if request.user.role not in ['ADMIN', 'JEFE'] and not request.user.is_superuser:
            if perm.user != request.user:
                return HttpResponse("No tienes permiso para descargar este documento.", status=403)
                
        context = {'perm': perm}
        
        html = render_to_string('hr/pdf/permission_document.html', context, request=request)
        
        response = HttpResponse(content_type='application/pdf')
        filename = f'Solicitud_{perm.category}_{perm.user.document_number}_{perm.start_date.strftime("%Y%m%d")}.pdf'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        pisa_status = pisa.CreatePDF(html, dest=response, link_callback=link_callback)
        
        if pisa_status.err:
            return HttpResponse('Error generando PDF', status=500)
        return response
    except Exception as e:
        import traceback
        error_msg = f"Crash en PDF:\n{str(e)}\n\n{traceback.format_exc()}"
        return HttpResponse(error_msg, content_type="text/plain", status=500)
