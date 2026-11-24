from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError


class CustomPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label='Contraseña Actual',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ingresa tu contraseña actual',
            'autocomplete': 'current-password',
            'autofocus': True,
        }),
    )
    new_password1 = forms.CharField(
        label='Nueva Contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Crea una contraseña segura',
            'autocomplete': 'new-password',
        }),
    )
    new_password2 = forms.CharField(
        label='Confirmar Nueva Contraseña',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Vuelve a escribir la nueva contraseña',
            'autocomplete': 'new-password',
        }),
    )

    error_messages = {
        'password_incorrect': 'La contraseña actual ingresada es incorrecta.',
        'password_mismatch': 'Las dos contraseñas nuevas no coinciden.',
    }

    def clean_new_password1(self):
        new_password = self.cleaned_data.get('new_password1')
        old_password = self.cleaned_data.get('old_password')
        if new_password and old_password and new_password == old_password:
            raise ValidationError('La nueva contraseña debe ser diferente a tu contraseña actual.')
        return new_password

    def _post_clean(self):
        forms.Form._post_clean(self)
        password = self.cleaned_data.get('new_password1')
        if password and not self.errors.get('new_password1'):
            try:
                password_validation.validate_password(password, self.user)
            except ValidationError as error:
                self.add_error('new_password1', error)
