from django.db import models

class NotificationStatus(models.TextChoices):
    UNREAD = 'UNREAD', 'No Leído'
    READ = 'READ', 'Leído'

class Notification(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField('Título', max_length=200)
    message = models.TextField('Mensaje')
    status = models.CharField('Estado', max_length=20, choices=NotificationStatus.choices, default=NotificationStatus.UNREAD)
    created_at = models.DateTimeField('Fecha de Creación', auto_now_add=True)
    
    # URL opcional para redirigir (ej. al permiso pendiente)
    action_url = models.URLField('URL de Acción', blank=True)

    class Meta:
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.status}] {self.user} - {self.title}"
