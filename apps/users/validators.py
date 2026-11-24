import re
from django.core.exceptions import ValidationError


class StrongPasswordValidator:
    """
    Valida que la contraseña cumpla las reglas de seguridad de la empresa:
    - Mínimo 8 caracteres
    - Al menos una letra mayúscula (A-Z)
    - Al menos una letra minúscula (a-z)
    - Al menos un número (0-9)
    - Al menos un símbolo especial (ej. !@#$%^&*)
    """

    def validate(self, password, user=None):
        errors = []
        if len(password) < 8:
            errors.append("La contraseña debe tener al menos 8 caracteres.")
        if not re.search(r'[A-Z]', password):
            errors.append("La contraseña debe incluir al menos una letra mayúscula (A-Z).")
        if not re.search(r'[a-z]', password):
            errors.append("La contraseña debe incluir al menos una letra minúscula (a-z).")
        if not re.search(r'[0-9]', password):
            errors.append("La contraseña debe incluir al menos un número (0-9).")
        if not re.search(r'[^A-Za-z0-9]', password):
            errors.append("La contraseña debe incluir al menos un símbolo especial (ej. !@#$%&*).")

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return (
            "Tu contraseña debe tener mínimo 8 caracteres y combinar letras mayúsculas, "
            "letras minúsculas, números y símbolos especiales."
        )
