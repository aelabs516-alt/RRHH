from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.users import views as user_views
from core import views as core_views
from apps.hr import views as hr_views
from apps.hr import certificates_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', user_views.dashboard, name='dashboard'),
    path('login/', user_views.CustomLoginView.as_view(), name='login'),
    path('logout/', user_views.custom_logout, name='logout'),
    
    # Módulo de Colaboradores (Custom Frontend)
    path('users/', user_views.UserListView.as_view(), name='users_list'),
    path('users/create/', user_views.UserCreateView.as_view(), name='users_create'),
    path('users/<int:pk>/update/', user_views.UserUpdateView.as_view(), name='users_update'),
    path('users/<int:pk>/delete/', user_views.UserDeleteView.as_view(), name='users_delete'),
    
    # Módulos Adicionales (Custom Frontend)
    path('areas/', core_views.AreaListView.as_view(), name='areas_list'),
    path('areas/create/', core_views.AreaCreateView.as_view(), name='areas_create'),
    path('areas/<int:pk>/update/', core_views.AreaUpdateView.as_view(), name='areas_update'),

    path('positions/', core_views.PositionListView.as_view(), name='positions_list'),
    path('positions/create/', core_views.PositionCreateView.as_view(), name='positions_create'),
    path('positions/<int:pk>/update/', core_views.PositionUpdateView.as_view(), name='positions_update'),

    path('holidays/', core_views.HolidayListView.as_view(), name='holidays_list'),
    path('holidays/create/', core_views.HolidayCreateView.as_view(), name='holidays_create'),
    path('holidays/<int:pk>/update/', core_views.HolidayUpdateView.as_view(), name='holidays_update'),

    path('turns/', core_views.TurnListView.as_view(), name='turns_list'),
    path('turns/create/', core_views.TurnCreateView.as_view(), name='turns_create'),
    path('turns/<int:pk>/update/', core_views.TurnUpdateView.as_view(), name='turns_update'),

    path('permissions/', core_views.PermissionListView.as_view(), name='permissions_list'),
    path('permissions/create/', core_views.PermissionCreateView.as_view(), name='permissions_create'),
    path('permissions/<int:pk>/update/', core_views.PermissionUpdateView.as_view(), name='permissions_update'),

    path('acts/', core_views.ActListView.as_view(), name='acts_list'),
    path('acts/create/', core_views.ActCreateView.as_view(), name='acts_create'),
    path('acts/<int:pk>/update/', core_views.ActUpdateView.as_view(), name='acts_update'),
    path('acts/<int:pk>/delete/', core_views.ActDeleteView.as_view(), name='acts_delete'),
    path('acts/<int:pk>/pdf/', certificates_views.download_act_pdf, name='act_pdf'),
    path('acts/auto-generate/<str:doc_number>/', core_views.acts_auto_generate, name='acts_auto_generate'),

    path('payroll/mass-upload/', hr_views.payroll_mass_upload, name='payroll_mass_upload'),
    
    path('certificates/labor/', certificates_views.certificate_labor, name='certificate_labor'),
    path('certificates/payroll/', certificates_views.download_payroll, name='download_payroll'),
    
    path('payroll/', core_views.PayrollListView.as_view(), name='payroll_list'),
    path('payroll/create/', core_views.PayrollCreateView.as_view(), name='payroll_create'),
    path('payroll/<int:pk>/update/', core_views.PayrollUpdateView.as_view(), name='payroll_update'),
    
    path('api/holidays/', core_views.get_holidays_api, name='api_holidays'),
    
    # Marcación de Asistencia
    path('attendance/', include('apps.attendance.urls')),
]

from django.urls import re_path
from django.views.static import serve

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
