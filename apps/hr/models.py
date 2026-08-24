from django.db import models

class FaultSeverity(models.TextChoices):
    LEVE = 'LEVE', 'Leve'
    GRAVE = 'GRAVE', 'Grave'
    MUY_GRAVE = 'MUY_GRAVE', 'Muy grave'

class DisciplinaryAct(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='disciplinary_acts')
    date_created = models.DateTimeField('Fecha de Creación', auto_now_add=True)
    
    severity = models.CharField('Tipo de Falta', max_length=20, choices=FaultSeverity.choices)
    
    # Texto fijo automatizado generado por el sistema
    description = models.TextField('Descripción Detallada del Hecho')
    
    # Descargos de escritura obligatoria
    employee_defense = models.TextField('Descargos del Colaborador', blank=True)
    
    decision = models.CharField('Decisión', max_length=100, default='Llamado de atención escrito')
    
    # Firmas interactivas
    employee_signature = models.ImageField('Firma del Colaborador', upload_to='secure/acts/employee_signatures/', null=True, blank=True)
    manager_signature = models.ImageField('Firma del Jefe Inmediato', upload_to='secure/acts/manager_signatures/', null=True, blank=True)
    
    # PDF generado final
    document_pdf = models.FileField('Acta en PDF', upload_to='secure/acts/documents/', null=True, blank=True)

    class Meta:
        verbose_name = 'Acta Disciplinaria'
        verbose_name_plural = 'Actas Disciplinarias'

    def __str__(self):
        return f"Acta {self.get_severity_display()} - {self.user} ({self.date_created.strftime('%Y-%m-%d')})"

    def get_row_values(self):
        return [self.user.document_number, self.user.get_full_name(), self.get_severity_display(), self.date_created.strftime('%d/%m/%Y'), self.decision]

class PayrollSlip(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='payroll_slips')
    month = models.DateField('Mes de Pago') # Representará el periodo
    
    # Archivo PDF (Colilla)
    document = models.FileField('Colilla de Nómina', upload_to='secure/payroll/')
    
    uploaded_at = models.DateTimeField('Fecha de Carga', auto_now_add=True)

    class Meta:
        verbose_name = 'Colilla de Nómina'
        verbose_name_plural = 'Colillas de Nómina'
        unique_together = ('user', 'month')

    def __str__(self):
        return f"Colilla {self.month.strftime('%Y-%m')} - {self.user}"

    def get_row_values(self):
        return [self.user.document_number, self.user.get_full_name(), self.month.strftime('%Y-%m'), 'Descargar PDF']
