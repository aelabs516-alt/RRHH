from django.template.loader import render_to_string
from django.core.files.base import ContentFile
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except (OSError, ImportError):
    WEASYPRINT_AVAILABLE = False
from .models import DisciplinaryAct

def generate_disciplinary_act_pdf(act: DisciplinaryAct, request=None):
    if not WEASYPRINT_AVAILABLE:
        print("WeasyPrint missing, skipping PDF generation.")
        return None
    """
    Genera un PDF usando Weasyprint a partir de una plantilla HTML y lo adjunta al modelo.
    """
    # Si pasamos request, base_url permite resolver rutas estáticas, pero para weasyprint suele ser mejor
    # pasar rutas absolutas o usar base_url adecuado. Usaremos base_url básico.
    
    context = {
        'act': act,
        'user': act.user,
        'date': act.date_created,
    }
    
    html_string = render_to_string('hr/pdf/disciplinary_act.html', context)
    
    # Dependiendo de si es llamado en tarea background o web
    base_url = request.build_absolute_uri('/') if request else ''
    
    html = HTML(string=html_string, base_url=base_url)
    
    css = CSS(string='''
        @page { size: A4; margin: 2.5cm; }
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; font-size: 14px; }
        .header { text-align: center; border-bottom: 2px solid #2c3e50; padding-bottom: 15px; margin-bottom: 30px; }
        h1 { font-size: 20px; text-transform: uppercase; }
        .content { margin-bottom: 30px; }
        .signatures { margin-top: 50px; width: 100%; display: table; }
        .signature-box { display: table-cell; width: 50%; text-align: center; }
        .signature-box img { max-width: 150px; max-height: 80px; border-bottom: 1px solid #000; margin-bottom: 5px; }
    ''')
    
    pdf_bytes = html.write_pdf(stylesheets=[css])
    
    filename = f"Acta_{act.user.document_number}_{act.id}.pdf"
    act.document_pdf.save(filename, ContentFile(pdf_bytes), save=True)
    return act
