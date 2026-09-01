from django.db import models
from django.utils import timezone

class AttendanceStatus(models.TextChoices):
    A_TIEMPO = 'A_TIEMPO', 'A Tiempo'
    RETARDO = 'RETARDO', 'Retardo'
    FALTA = 'FALTA', 'Falta'

class Attendance(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField('Fecha de Marcación', default=timezone.now)
    
    # Marcación Ingreso
    entry_time = models.DateTimeField('Hora de Ingreso', null=True, blank=True)
    entry_status = models.CharField('Estado de Ingreso', max_length=20, choices=AttendanceStatus.choices, null=True, blank=True)
    entry_photo = models.ImageField('Foto de Ingreso', upload_to='attendance/entry/', null=True, blank=True)
    
    # Marcación Salida
    exit_time = models.DateTimeField('Hora de Salida', null=True, blank=True)
    exit_photo = models.ImageField('Foto de Salida', upload_to='attendance/exit/', null=True, blank=True)
    
    # Cálculos Automáticos
    hours_worked = models.DecimalField('Horas Trabajadas', max_digits=5, decimal_places=2, default=0)
    extra_hours = models.DecimalField('Horas Extras', max_digits=5, decimal_places=2, default=0)
    permission_hours = models.DecimalField('Horas de Permiso (Salida Temprano)', max_digits=5, decimal_places=2, default=0)
    
    # Geolocalización
    latitude = models.DecimalField('Latitud', max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField('Longitud', max_digits=10, decimal_places=7, null=True, blank=True)
    is_out_of_bounds = models.BooleanField('Fuera de Rango (30m)', default=False)
    
    JUSTIFICATION_CHOICES = [
        ('NORMAL', 'Ninguna / Normal'),
        ('CITA_MEDICA', 'Permiso remunerado: Cita médica'),
        ('ELECCIONES', 'Permiso remunerado: Elecciones / Jurado'),
        ('CALAMIDAD', 'Permiso remunerado: Calamidad'),
        ('ESCOLAR', 'Permiso remunerado: Obligaciones escolares'),
        ('JUDICIAL', 'Permiso remunerado: Citas Judiciales'),
        ('LUTO', 'Permiso remunerado: Luto'),
        ('ENFERMEDAD', 'Permiso remunerado: Enfermedad General'),
        ('PERSONAL', 'Permiso NO Remunerado: Asuntos personales'),
        ('OTROS', 'Permiso NO Remunerado: Otros'),
    ]
    justification_type = models.CharField('Tipo de Justificación', max_length=20, choices=JUSTIFICATION_CHOICES, default='NORMAL')
    observations = models.TextField('Observaciones', blank=True)
    
    class Meta:
        verbose_name = 'Registro de Asistencia'
        verbose_name_plural = 'Registros de Asistencia'
        unique_together = ('user', 'date')

    def __str__(self):
        return f"{self.user} - {self.date}"

class PermissionCategory(models.TextChoices):
    # Tipificación Módulo 4.3.3
    CITA_MEDICA = 'CITA_MEDICA', 'Cita médica (Remunerado)'
    ELECCIONES = 'ELECCIONES', 'Elecciones / Jurado (Remunerado)'
    CALAMIDAD = 'CALAMIDAD', 'Calamidad (Remunerado)'
    ESCOLARES = 'ESCOLARES', 'Obligaciones escolares (Remunerado)'
    JUDICIALES = 'JUDICIALES', 'Citas Judiciales (Remunerado)'
    LUTO = 'LUTO', 'Luto (Remunerado)'
    ENFERMEDAD = 'ENFERMEDAD', 'Enfermedad General (Remunerado)'
    PERSONALES = 'PERSONALES', 'Asuntos personales (NO Remunerado)'
    OTROS = 'OTROS', 'Otros (Descuenta tiempo)'
    VACACIONES = 'VACACIONES', 'Vacaciones'

class Permission(models.Model):
    STATUS_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
    ]

    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='permissions')
    category = models.CharField('Categoría de Permiso', max_length=30, choices=PermissionCategory.choices)
    start_date = models.DateTimeField('Fecha/Hora Inicio')
    end_date = models.DateTimeField('Fecha/Hora Fin')
    days_requested = models.IntegerField('Días a disfrutar', null=True, blank=True)
    reason = models.TextField('Motivo')
    status = models.CharField('Estado', max_length=20, choices=STATUS_CHOICES, default='PENDIENTE')
    created_at = models.DateTimeField('Fecha de Solicitud', auto_now_add=True)
    
    # Aprobación
    approved_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_permissions')
    approval_date = models.DateTimeField('Fecha de Aprobación/Rechazo', null=True, blank=True)
    
    # Para Carga Masiva (Observaciones del Admin)
    admin_observations = models.TextField('Observaciones del Administrador', blank=True)

    class Meta:
        verbose_name = 'Permiso / Vacaciones'
        verbose_name_plural = 'Permisos / Vacaciones'

    def __str__(self):
        return f"{self.user} - {self.get_category_display()} ({self.status})"

    def get_row_values(self):
        return [self.user.document_number, self.user.get_full_name(), self.get_category_display(), self.start_date.strftime('%d/%m/%Y'), self.end_date.strftime('%d/%m/%Y'), self.status]
