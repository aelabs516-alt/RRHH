from django.db import models

class CompanySettings(models.Model):
    latitude = models.DecimalField('Latitud Empresa', max_digits=10, decimal_places=7, default=6.1950)
    longitude = models.DecimalField('Longitud Empresa', max_digits=10, decimal_places=7, default=-75.5685)
    tolerance_radius = models.IntegerField('Radio de Tolerancia (m)', default=30)
    
    class Meta:
        verbose_name = 'Configuración de Empresa'
        verbose_name_plural = 'Configuraciones de Empresa'
        
    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj

class Area(models.Model):
    name = models.CharField('Nombre del Área', max_length=100, unique=True)
    description = models.TextField('Descripción', blank=True)

    class Meta:
        verbose_name = 'Área'
        verbose_name_plural = 'Áreas'

    def __str__(self):
        return self.name

    def get_row_values(self):
        return [self.name, self.description]

class Position(models.Model):
    name = models.CharField('Nombre del Cargo', max_length=100)
    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name='positions', verbose_name='Área')
    description = models.TextField('Descripción', blank=True)

    class Meta:
        verbose_name = 'Cargo'
        verbose_name_plural = 'Cargos'
        unique_together = ('name', 'area')

    def __str__(self):
        return f"{self.name} - {self.area.name}"

    def get_row_values(self):
        return [self.name, self.area.name, self.description]

class Turn(models.Model):
    # Gestión de Turnos (Módulo 4.2.2)
    code = models.CharField('Código del turno', max_length=20, unique=True)
    name = models.CharField('Nombre', max_length=50) # Ej: Turno Mañana
    start_time = models.TimeField('Hora de inicio')
    end_time = models.TimeField('Hora de Fin')
    
    # Podría requerir días aplicables, pero el PDF pide básicos. Añadamos tolerancia si es necesario, 
    # aunque la regla dice 5 min global, se puede parametrizar aquí si futuro cambia.
    
    class Meta:
        verbose_name = 'Turno'
        verbose_name_plural = 'Turnos'

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"

    def get_row_values(self):
        return [self.code, self.name, self.start_time.strftime('%H:%M'), self.end_time.strftime('%H:%M')]

class EmployeeTurn(models.Model):
    # Matriz semanal de turnos para los colaboradores
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='turns')
    turn_monday = models.ForeignKey(Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    turn_tuesday = models.ForeignKey(Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    turn_wednesday = models.ForeignKey(Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    turn_thursday = models.ForeignKey(Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    turn_friday = models.ForeignKey(Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    turn_saturday = models.ForeignKey(Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    turn_sunday = models.ForeignKey(Turn, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    
    start_date = models.DateField('Fecha de Inicio Asignación', auto_now_add=True)
    end_date = models.DateField('Fecha de Fin Asignación', null=True, blank=True)

    class Meta:
        verbose_name = 'Matriz de Turno'
        verbose_name_plural = 'Matrices de Turnos'

    def __str__(self):
        return f"Matriz Semanal de {self.user}"

    def get_turn_for_date(self, check_date):
        # 0 = Monday, 6 = Sunday
        weekday = check_date.weekday()
        if weekday == 0: return self.turn_monday
        elif weekday == 1: return self.turn_tuesday
        elif weekday == 2: return self.turn_wednesday
        elif weekday == 3: return self.turn_thursday
        elif weekday == 4: return self.turn_friday
        elif weekday == 5: return self.turn_saturday
        elif weekday == 6: return self.turn_sunday
        return None

class CustomHoliday(models.Model):
    date = models.DateField('Fecha del Festivo', unique=True)
    name = models.CharField('Nombre / Motivo', max_length=100)
    
    class Meta:
        verbose_name = 'Festivo Personalizado'
        verbose_name_plural = 'Festivos Personalizados'
        ordering = ['date']
        
    def __str__(self):
        return f"{self.date.strftime('%d/%m/%Y')} - {self.name}"

    def get_row_values(self):
        return [self.date.strftime('%d/%m/%Y'), self.name]
