from django.db import models
from django.contrib.auth.models import AbstractUser
from simple_history.models import HistoricalRecords
from .managers import UserManager

class Role(models.TextChoices):
    ADMIN = 'ADMIN', 'Administrador Global'
    JEFE = 'JEFE', 'Jefe Inmediato'
    COLABORADOR = 'COLABORADOR', 'Colaborador'

class User(AbstractUser):
    username = None
    document_number = models.CharField('Número de Documento', max_length=20, unique=True)
    
    role = models.CharField('Rol/Perfil', max_length=20, choices=Role.choices, default=Role.COLABORADOR)
    signature = models.ImageField('Firma Digital', upload_to='secure/signatures/', blank=True, null=True)
    
    # Ficha Técnica del Empleado (Módulo 4.2.1)
    contact_number = models.CharField('Número de Contacto', max_length=20, blank=True)
    birth_date = models.DateField('Fecha de Nacimiento', null=True, blank=True)
    hire_date = models.DateField('Fecha de Ingreso', null=True, blank=True)
    salary = models.DecimalField('Salario', max_digits=12, decimal_places=2, null=True, blank=True)
    emergency_contact = models.CharField('Contacto de Emergencia', max_length=100, blank=True)
    emergency_contact_number = models.CharField('Número Contacto Emergencia', max_length=20, blank=True)

    # Organización
    position = models.ForeignKey('organization.Position', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cargo')
    area = models.ForeignKey('organization.Area', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Área')
    # Un Jefe Inmediato puede no tener un jefe o tener al Admin. Un colaborador tendrá a un Jefe.
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates', verbose_name='Jefe Inmediato')

    history = HistoricalRecords()

    USERNAME_FIELD = 'document_number'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    objects = UserManager()

    class Meta:
        verbose_name = 'Usuario / Colaborador'
        verbose_name_plural = 'Usuarios / Colaboradores'
        
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.document_number})"

    def get_row_values(self):
        return [self.document_number, f"{self.first_name} {self.last_name}", self.get_role_display(), self.position.name if self.position else 'N/A', 'Activo' if self.is_active else 'Inactivo']
