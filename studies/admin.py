from django.contrib import admin

from .models import Patient, Study


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name', 'sex', 'age', 'created_at')
    list_filter = ('sex',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = (
        'access_number', 'patient', 'body_part',
        'exposure_date', 'exposure_time', 'performing_physician',
    )
    list_filter = ('body_part', 'exposure_date')
    search_fields = (
        'access_number', 'patient__name',
        'referring_physician', 'performing_physician', 'body_part',
    )
    autocomplete_fields = ('patient',)
    date_hierarchy = 'exposure_date'

    fieldsets = (
        ('Paciente y acceso', {
            'fields': ('patient', 'access_number'),
        }),
        ('Registro', {
            'fields': (('register_date', 'register_time'),),
        }),
        ('Exposición', {
            'fields': (
                ('exposure_date', 'exposure_time'),
                'body_part',
            ),
        }),
        ('Médicos', {
            'fields': ('referring_physician', 'performing_physician'),
        }),
        ('Imagen', {
            'fields': (
                ('image_width', 'image_height'),
                ('bits_allocated', 'bits_stored'),
            ),
        }),
        ('Archivo', {
            'fields': ('pdf',),
        }),
    )
