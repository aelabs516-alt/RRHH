import csv
from django.http import HttpResponse
from django.contrib import admin
from apps.attendance.models import Attendance, Permission

@admin.action(description="Exportar a CSV / Excel")
def export_to_csv(modeladmin, request, queryset):
    meta = modeladmin.model._meta
    field_names = [field.name for field in meta.fields]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={meta}.csv'
    
    # Escribir con BOM para que Excel lea UTF-8 correctamente
    response.write(u'\ufeff'.encode('utf8'))
    writer = csv.writer(response)

    writer.writerow(field_names)
    for obj in queryset:
        row = writer.writerow([getattr(obj, field) for field in field_names])
    return response

class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'entry_status', 'hours_worked', 'extra_hours')
    list_filter = ('date', 'entry_status', 'user')
    actions = [export_to_csv]

class PermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'category')
    actions = [export_to_csv]

admin.site.register(Attendance, AttendanceAdmin)
admin.site.register(Permission, PermissionAdmin)
