from datetime import date, datetime, time, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.users.models import User, Role
from apps.organization.models import Turn, EmployeeTurn, CustomHoliday
from apps.attendance.models import Attendance, AttendanceStatus, Permission, PermissionCategory
from apps.attendance.services import (
    calculate_attendance_metrics,
    calculate_permission_working_hours,
)
from apps.hr.models import DisciplinaryAct, FaultSeverity


class ScheduleLunchAndDashboardTests(TestCase):
    def setUp(self):
        self.turn_weekday = Turn.objects.create(
            code='T_LV', name='Lunes a Viernes 9-18', start_time=time(9, 0), end_time=time(18, 0)
        )
        self.turn_sat = Turn.objects.create(
            code='T_SAB', name='Sábado 8-12', start_time=time(8, 0), end_time=time(12, 0)
        )

        self.admin = User.objects.create_user(
            document_number='1000',
            first_name='Admin',
            last_name='Global',
            password='pass',
            role=Role.ADMIN,
        )
        self.collab_a = User.objects.create_user(
            document_number='2001',
            first_name='Juan',
            last_name='Perez',
            password='pass',
            role=Role.COLABORADOR,
        )
        self.collab_b = User.objects.create_user(
            document_number='2002',
            first_name='Maria',
            last_name='Gomez',
            password='pass',
            role=Role.COLABORADOR,
        )

        for u in (self.collab_a, self.collab_b):
            EmployeeTurn.objects.create(
                user=u,
                turn_monday=self.turn_weekday,
                turn_tuesday=self.turn_weekday,
                turn_wednesday=self.turn_weekday,
                turn_thursday=self.turn_weekday,
                turn_friday=self.turn_weekday,
                turn_saturday=self.turn_sat,
                turn_sunday=None,
            )

    def _aware(self, d, hh, mm=0):
        return timezone.make_aware(datetime.combine(d, time(hh, mm)))

    # --- Requirement #2: Lunch hour exclusion on Monday-Friday ---
    def test_weekday_lunch_excluded_personal_full_day_9am_to_9am(self):
        # Lunes 2026-11-23 (no festivo): turno 09:00 - 18:00 (9h reloj = 8h trabajo + 1h almuerzo)
        mon = date(2026, 11, 23)
        hours_worked, extra, perm = calculate_attendance_metrics(
            work_date=mon,
            turn=self.turn_weekday,
            entry_dt=self._aware(mon, 9, 0),
            exit_dt=self._aware(mon, 9, 0),
            entry_justification='NORMAL',
            exit_justification='PERSONAL',
        )
        self.assertEqual(hours_worked, 0.0)
        self.assertEqual(extra, 0.0)
        self.assertEqual(perm, 8.0)

    def test_weekday_lunch_excluded_full_shift_and_partial_exits(self):
        mon = date(2026, 11, 23)
        # Jornada completa 09:00 - 18:00 -> 8h trabajadas, 0 extra, 0 permiso
        hw, ex, pm = calculate_attendance_metrics(
            mon, self.turn_weekday, self._aware(mon, 9, 0), self._aware(mon, 18, 0)
        )
        self.assertEqual((hw, ex, pm), (8.0, 0.0, 0.0))

        # Sale 2h temprano (16:00) -> 6h trabajadas, 2h permiso
        hw, ex, pm = calculate_attendance_metrics(
            mon, self.turn_weekday, self._aware(mon, 9, 0), self._aware(mon, 16, 0),
            exit_justification='PERSONAL',
        )
        self.assertEqual((hw, ex, pm), (6.0, 0.0, 2.0))

        # Trabaja solo la mañana (09:00 - 13:00) -> 4h trabajadas, 4h permiso
        hw, ex, pm = calculate_attendance_metrics(
            mon, self.turn_weekday, self._aware(mon, 9, 0), self._aware(mon, 13, 0),
            exit_justification='PERSONAL',
        )
        self.assertEqual((hw, ex, pm), (4.0, 0.0, 4.0))

        # Llega después de almuerzo con permiso remunerado (14:00 - 18:00) -> 8h trabajadas, 0 extra, 0 permiso
        hw, ex, pm = calculate_attendance_metrics(
            mon, self.turn_weekday, self._aware(mon, 14, 0), self._aware(mon, 18, 0),
            entry_justification='CITA_MEDICA',
        )
        self.assertEqual((hw, ex, pm), (8.0, 0.0, 0.0))

        # Hora extra 1h (09:00 - 19:00 con TIEMPO_EXTRA) -> 9h trabajadas, 1h extra, 0 permiso
        hw, ex, pm = calculate_attendance_metrics(
            mon, self.turn_weekday, self._aware(mon, 9, 0), self._aware(mon, 19, 0),
            exit_justification='TIEMPO_EXTRA',
        )
        self.assertEqual((hw, ex, pm), (9.0, 1.0, 0.0))

    def test_saturday_no_lunch_deduction(self):
        sat = date(2026, 11, 28)
        hw, ex, pm = calculate_attendance_metrics(
            sat, self.turn_sat, self._aware(sat, 8, 0), self._aware(sat, 12, 0)
        )
        self.assertEqual((hw, ex, pm), (4.0, 0.0, 0.0))

        hw, ex, pm = calculate_attendance_metrics(
            sat, self.turn_sat, self._aware(sat, 8, 0), self._aware(sat, 8, 0),
            exit_justification='PERSONAL',
        )
        self.assertEqual((hw, ex, pm), (0.0, 0.0, 4.0))

    # --- Requirement #1: Multi-day permission uses only working schedule ---
    def test_multiday_permission_working_schedule_only(self):
        # Lunes 2026-11-23 09:00 a Miércoles 2026-11-25 18:00 (3 días hábiles * 8h = 24h, NO 57h)
        start_dt = self._aware(date(2026, 11, 23), 9, 0)
        end_dt = self._aware(date(2026, 11, 25), 18, 0)
        hours = calculate_permission_working_hours(self.collab_a, start_dt, end_dt)
        self.assertEqual(hours, 24.0)

        # Parcial multi-día: Lunes 14:00 (4h) + Martes completo (8h) + Miércoles 09:00-12:00 (3h) = 15h
        start_dt = self._aware(date(2026, 11, 23), 14, 0)
        end_dt = self._aware(date(2026, 11, 25), 12, 0)
        hours = calculate_permission_working_hours(self.collab_a, start_dt, end_dt)
        self.assertEqual(hours, 15.0)

        # Cruzando fin de semana: Viernes 2026-11-27 09:00 (8h) + Sábado 28 (4h) + Domingo 29 (0h) + Lunes 30 18:00 (8h) = 20h
        start_dt = self._aware(date(2026, 11, 27), 9, 0)
        end_dt = self._aware(date(2026, 11, 30), 18, 0)
        hours = calculate_permission_working_hours(self.collab_a, start_dt, end_dt)
        self.assertEqual(hours, 20.0)

        # Con festivo personalizado en Martes 2026-11-24: Lun (8h) + Mar festivo (0h) + Mié (8h) = 16h
        CustomHoliday.objects.create(date=date(2026, 11, 24), name='Festivo Prueba')
        start_dt = self._aware(date(2026, 11, 23), 9, 0)
        end_dt = self._aware(date(2026, 11, 25), 18, 0)
        hours = calculate_permission_working_hours(self.collab_a, start_dt, end_dt)
        self.assertEqual(hours, 16.0)

    # --- Requirement #3 & #4: Dashboard Net Balance, Session Isolation & Audit Tardies ---
    def test_dashboard_net_balance_isolation_and_audit_tardies(self):
        today = timezone.localdate()
        # Collab A: +10h extras, -8h permiso (multi-día 1 día 9-18 = 8h) -> Balance Neto = +2.0h
        Attendance.objects.create(
            user=self.collab_a,
            date=today - timedelta(days=2),
            entry_time=self._aware(today - timedelta(days=2), 9, 10),
            entry_status=AttendanceStatus.RETARDO,
            extra_hours=Decimal('10.00'),
            permission_hours=Decimal('0.00'),
        )
        # Un retardo antiguo (> 30 días) que NO debe aparecer en LLEGADAS TARDE ni en Panel de Auditoría
        Attendance.objects.create(
            user=self.collab_a,
            date=today - timedelta(days=45),
            entry_time=self._aware(today - timedelta(days=45), 9, 15),
            entry_status=AttendanceStatus.RETARDO,
        )
        # Permiso personal de 1 día completo Lunes 2026-11-23 09:00-18:00 (8h efectivas)
        Permission.objects.create(
            user=self.collab_a,
            category=PermissionCategory.PERSONALES,
            start_date=self._aware(date(2026, 11, 23), 9, 0),
            end_date=self._aware(date(2026, 11, 23), 18, 0),
            reason='Personal',
            status='APROBADO',
        )

        # Collab B: +2h extras, -6h permiso_hours -> Balance Neto = -4.0h
        # Además 1 retardo YA castigado con acta firmada (no debe contar en LLEGADAS TARDE)
        # y 2 retardos nuevos posteriores al acta (sí deben contar)
        Attendance.objects.create(
            user=self.collab_b,
            date=today - timedelta(days=10),
            entry_time=self._aware(today - timedelta(days=10), 9, 15),
            entry_status=AttendanceStatus.RETARDO,
            extra_hours=Decimal('2.00'),
            permission_hours=Decimal('6.00'),
        )
        act_b = DisciplinaryAct.objects.create(
            user=self.collab_b,
            severity=FaultSeverity.LEVE,
            description='Acta previa',
            decision='Llamado',
            employee_signature='signed.png',
        )
        # Ajustar fecha del acta a hace 5 días
        DisciplinaryAct.objects.filter(pk=act_b.pk).update(
            date_created=self._aware(today - timedelta(days=5), 12, 0)
        )
        # 2 retardos posteriores al acta
        Attendance.objects.create(
            user=self.collab_b,
            date=today - timedelta(days=2),
            entry_time=self._aware(today - timedelta(days=2), 9, 15),
            entry_status=AttendanceStatus.RETARDO,
        )
        Attendance.objects.create(
            user=self.collab_b,
            date=today - timedelta(days=1),
            entry_time=self._aware(today - timedelta(days=1), 9, 20),
            entry_status=AttendanceStatus.RETARDO,
        )

        client = Client()

        # 1) Sesión de Colaborador A: SOLO sus horas netas (+2.0h extras, 0.0h permisos), 1 retardo vigente
        client.force_login(self.collab_a)
        resp_a = client.get(reverse('dashboard') + f'?user_id={self.collab_b.id}')
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a.context['kpis']['extras'], 2.0)
        self.assertEqual(resp_a.context['kpis']['permisos'], 0.0)
        self.assertEqual(resp_a.context['kpis']['tardies'], 1)
        self.assertEqual(len(resp_a.context['extras_chart']), 1)
        self.assertEqual(resp_a.context['extras_chart'][0]['user__first_name'], 'Juan')
        self.assertEqual(resp_a.context['extras_chart'][0]['total'], 2.0)
        self.assertEqual(len(resp_a.context['net_table']), 1)
        # Los colaboradores NO deben ver controles de ordenamiento en Consolidado Neto
        self.assertNotContains(resp_a, 'data-sort-key="extras"')

        # 2) Sesión de Colaborador B: SOLO sus horas netas (0.0h extras, 4.0h permisos), 2 retardos vigentes (ignora el ya castigado)
        client.force_login(self.collab_b)
        resp_b = client.get(reverse('dashboard'))
        self.assertEqual(resp_b.status_code, 200)
        self.assertEqual(resp_b.context['kpis']['extras'], 0.0)
        self.assertEqual(resp_b.context['kpis']['permisos'], 4.0)
        self.assertEqual(resp_b.context['kpis']['tardies'], 2)
        self.assertEqual(len(resp_b.context['extras_chart']), 1)
        self.assertEqual(resp_b.context['extras_chart'][0]['total'], -4.0)

        # 3) Sesión de Admin: acumulado neto de colaboradores (+2.0h extras, 4.0h permisos), 3 retardos totales del panel de auditoría
        client.force_login(self.admin)
        resp_admin = client.get(reverse('dashboard'))
        self.assertEqual(resp_admin.status_code, 200)
        self.assertEqual(resp_admin.context['kpis']['extras'], 2.0)
        self.assertEqual(resp_admin.context['kpis']['permisos'], 4.0)
        self.assertEqual(resp_admin.context['kpis']['tardies'], 3)
        self.assertEqual(
            resp_admin.context['kpis']['tardies'],
            sum(ct['count'] for ct in resp_admin.context['critical_tardies']),
        )
        chart_totals = {e['user__first_name']: e['total'] for e in resp_admin.context['extras_chart']}
        self.assertEqual(chart_totals, {'Juan': 2.0, 'Maria': -4.0})
        # Los administradores SÍ tienen ordenamiento en Total Extras, Total Permisos y Balance Neto
        self.assertContains(resp_admin, 'data-sort-key="extras"')
        self.assertContains(resp_admin, 'data-sort-key="permisos"')
        self.assertContains(resp_admin, 'data-sort-key="balance"')

        # 4) API de preview de horas laborales de permiso
        resp_api = client.get(
            reverse('api_permission_hours'),
            {
                'user_id': self.collab_a.id,
                'start_date': '2026-11-23T09:00',
                'end_date': '2026-11-25T18:00',
            },
        )
        self.assertEqual(resp_api.status_code, 200)
        self.assertEqual(resp_api.json()['hours'], 24.0)

        # 5) Filtro por día específico (formato YYYY-MM-DD del input date) no falla
        resp_day = client.get(reverse('dashboard'), {'day': today.strftime('%Y-%m-%d')})
        self.assertEqual(resp_day.status_code, 200)

    def test_consoles_and_permission_list_integration(self):
        client = Client()
        client.force_login(self.admin)

        # Consola individual: Lunes 09:00 a 09:00 permiso personal -> 8h permiso, 0h trabajadas
        resp = client.post(reverse('attendance:console_individual'), {
            'user_id': self.collab_a.id,
            'date': '2026-11-23',
            'entry_time': '09:00',
            'exit_time': '09:00',
            'entry_justification': 'NORMAL',
            'exit_justification': 'PERSONAL',
        })
        self.assertEqual(resp.status_code, 302)
        att_a = Attendance.objects.get(user=self.collab_a, date=date(2026, 11, 23))
        self.assertEqual(att_a.hours_worked, Decimal('0.00'))
        self.assertEqual(att_a.permission_hours, Decimal('8.00'))
        self.assertEqual(att_a.extra_hours, Decimal('0.00'))

        # Consola masiva: Lunes 09:00 a 18:00 normal -> 8h trabajadas (descuenta 1h almuerzo)
        resp_m = client.post(reverse('attendance:console_massive'), {
            'date': '2026-11-23',
            'user_ids': [str(self.collab_b.id)],
            f'entry_{self.collab_b.id}': '09:00',
            f'exit_{self.collab_b.id}': '18:00',
            f'entry_just_{self.collab_b.id}': 'NORMAL',
            f'exit_just_{self.collab_b.id}': 'NORMAL',
        })
        self.assertEqual(resp_m.status_code, 302)
        att_b = Attendance.objects.get(user=self.collab_b, date=date(2026, 11, 23))
        self.assertEqual(att_b.hours_worked, Decimal('8.00'))
        self.assertEqual(att_b.permission_hours, Decimal('0.00'))
        self.assertEqual(att_b.extra_hours, Decimal('0.00'))

        # Listado de permisos muestra duración laboral (24.0 h para 3 días L-M-Mi)
        Permission.objects.create(
            user=self.collab_a,
            category=PermissionCategory.PERSONALES,
            start_date=self._aware(date(2026, 11, 23), 9, 0),
            end_date=self._aware(date(2026, 11, 25), 18, 0),
            reason='Viaje personal',
            status='APROBADO',
        )
        resp_list = client.get(reverse('permissions_list'))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, '24.0 h')

    def test_all_redesigned_pages_render_cleanly(self):
        client = Client()

        # Login (unauthenticated)
        resp_login = client.get(reverse('login'))
        self.assertEqual(resp_login.status_code, 200)
        self.assertContains(resp_login, 'css/app.css')
        self.assertContains(resp_login, 'themeToggle')

        # Authenticated admin pages
        client.force_login(self.admin)
        admin_urls = [
            'dashboard',
            'attendance:mark',
            'attendance:console_individual',
            'attendance:console_massive',
            'attendance:map',
            'users_list',
            'users_create',
            'areas_list',
            'positions_list',
            'turns_list',
            'holidays_list',
            'permissions_list',
            'permissions_create',
            'acts_list',
            'vacations_notify_list',
            'vacations_notify_create',
            'certificate_labor',
            'download_payroll',
            'payroll_list',
            'payroll_mass_upload',
            'change_password',
        ]
        for url_name in admin_urls:
            resp = client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200, f"Failed to render {url_name}")
            self.assertContains(resp, 'css/app.css')
            self.assertContains(resp, 'themeToggle')

    def test_collaborator_password_change_validation_and_success(self):
        client = Client()
        client.force_login(self.collab_a)
        url = reverse('change_password')

        # Renderizado correcto con medidor de seguridad
        resp_get = client.get(url)
        self.assertEqual(resp_get.status_code, 200)
        self.assertContains(resp_get, 'strengthLabel')

        # Rechaza contraseñas que incumplen reglas de seguridad
        weak_passwords = [
            'Ab1!abc',      # menos de 8 caracteres
            'abcdef1!',     # sin mayúscula
            'ABCDEF1!',     # sin minúscula
            'Abcdefg!',     # sin número
            'Abcdefg1',     # sin símbolo especial
        ]
        for bad_pwd in weak_passwords:
            resp = client.post(url, {
                'old_password': 'pass',
                'new_password1': bad_pwd,
                'new_password2': bad_pwd,
            })
            self.assertEqual(resp.status_code, 200, f"Should reject weak password: {bad_pwd}")
            self.assertTrue(resp.context['form'].errors, f"Expected errors for {bad_pwd}")

        # Contraseña segura válida (8+ chars, mayúscula, minúscula, número, símbolo)
        strong_pwd = 'Segura2026!*'
        resp_ok = client.post(url, {
            'old_password': 'pass',
            'new_password1': strong_pwd,
            'new_password2': strong_pwd,
        })
        self.assertEqual(resp_ok.status_code, 302)

        # La sesión se mantiene activa y el inicio de sesión funciona con la nueva contraseña
        self.collab_a.refresh_from_db()
        self.assertTrue(self.collab_a.check_password(strong_pwd))
        client.logout()
        self.assertTrue(client.login(username='2001', password=strong_pwd))
