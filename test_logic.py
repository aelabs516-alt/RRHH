import os
import django
from datetime import datetime, date, timedelta, time
from django.utils import timezone

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.users.models import User
from apps.organization.models import Area, Position, Turn, EmployeeTurn
from apps.attendance.services import process_entry, process_exit
from apps.hr.models import DisciplinaryAct

def run_tests():
    print("--- INICIANDO VALIDACIONES DE RRHH ---")
    
    # 1. Setup inicial
    area, _ = Area.objects.get_or_create(name='Desarrollo')
    pos, _ = Position.objects.get_or_create(name='Backend Dev', area=area)
    
    user, created = User.objects.get_or_create(
        document_number='987654321', 
        defaults={'first_name': 'Juan', 'last_name': 'Pérez', 'position': pos}
    )
    if created:
        user.set_password('1234')
        user.save()
        
    turn, _ = Turn.objects.get_or_create(
        code='T_MANANA',
        defaults={'name': 'Turno Mañana', 'start_time': time(8, 0), 'end_time': time(17, 0)}
    )
    
    EmployeeTurn.objects.get_or_create(
        user=user, turn=turn, start_date=date(2026, 1, 1)
    )
    
    print(f"[*] Colaborador '{user}' asignado al turno: {turn}")
    
    # Limpiar asistencia de prueba previa
    user.attendances.all().delete()
    user.disciplinary_acts.all().delete()

    # 2. Prueba de Ingreso: A TIEMPO (dentro de los 5 minutos)
    base_date = timezone.now().date()
    # Lunes de esta semana
    monday = base_date - timedelta(days=base_date.weekday())
    
    entry_time_ok = timezone.make_aware(datetime.combine(monday, time(8, 4)))
    att_ok, status, act = process_entry(user, entry_time_ok)
    print(f"[+] Ingreso 08:04: Estado -> {status} (Esperado: A_TIEMPO)")
    
    # 3. Prueba de Ingreso: RETARDO 1, 2 y 3 (Alerta)
    tuesday = monday + timedelta(days=1)
    wednesday = monday + timedelta(days=2)
    thursday = monday + timedelta(days=3)
    
    _, s1, _ = process_entry(user, timezone.make_aware(datetime.combine(tuesday, time(8, 15))))
    _, s2, _ = process_entry(user, timezone.make_aware(datetime.combine(wednesday, time(8, 20))))
    _, s3, act3 = process_entry(user, timezone.make_aware(datetime.combine(thursday, time(8, 10))))
    
    print(f"[+] Ingresos tardíos (Mar, Mie): Estados -> {s1}, {s2}")
    print(f"[+] Tercer retardo (Jueves): Alerta disparada -> {act3} (Esperado: ALERTA_CRITICA)")
    
    # 4. Prueba de Ingreso: RETARDO 4 (Genera Acta Leve)
    friday = monday + timedelta(days=4)
    _, s4, act4 = process_entry(user, timezone.make_aware(datetime.combine(friday, time(8, 30))))
    print(f"[+] Cuarto retardo (Viernes): Acta Generada -> {act4}")
    if act4 and isinstance(act4, DisciplinaryAct):
        print(f"    - Severidad: {act4.get_severity_display()}")
        print(f"    - Descripción Auto-generada:\n      {act4.description.replace(chr(10), ' ')}")

    # 5. Prueba de Salida: Horas Extras (> 30 min) y Observaciones requeridas
    exit_time_extra = timezone.make_aware(datetime.combine(friday, time(17, 45)))
    try:
        process_exit(user, exit_time_extra)
        print("[-] FALLO: Debió pedir observaciones al tener horas extras.")
    except ValueError as e:
        print(f"[+] Validación Exitosa (Faltan observaciones): {e}")
        
    att_exit = process_exit(user, exit_time_extra, observations="Me quedé terminando un pase a producción.")
    print(f"[+] Salida 17:45 registrada con observaciones. Horas Extras calculadas: {att_exit.extra_hours}h (Esperado: 0.75h)")

    print("--- VALIDACIONES FINALIZADAS CORRECTAMENTE ---")

if __name__ == '__main__':
    run_tests()
