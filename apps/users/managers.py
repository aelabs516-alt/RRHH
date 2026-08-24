from django.contrib.auth.models import BaseUserManager

class UserManager(BaseUserManager):
    def create_user(self, document_number, password=None, **extra_fields):
        if not document_number:
            raise ValueError('El número de documento es obligatorio')
        user = self.model(document_number=document_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, document_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')

        return self.create_user(document_number, password, **extra_fields)
