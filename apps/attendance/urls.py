from django.urls import path
from . import views
from . import admin_console_views

app_name = 'attendance'

urlpatterns = [
    path('mark/', views.mark_attendance, name='mark'),
    path('map/', views.attendance_map, name='map'),
    path('map/update/', views.update_company_location, name='update_company_location'),
    path('api/process/', views.process_attendance_api, name='process_api'),
    path('console/individual/', admin_console_views.console_individual, name='console_individual'),
    path('console/massive/', admin_console_views.console_massive, name='console_massive'),
]
