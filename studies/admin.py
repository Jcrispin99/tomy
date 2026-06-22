from django import forms
from django.contrib import admin
from django.core.files.base import ContentFile

import fitz

from .models import Patient, Study, StudyDocument


def pdf_first_page_to_jpeg(pdf_file, dpi=200):
    pdf_file.seek(0)
    pdf_bytes = pdf_file.read()
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    try:
        page = doc[0]
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes('jpeg')
    finally:
        doc.close()


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name', 'sex', 'age', 'created_at')
    list_filter = ('sex',)
    search_fields = ('name',)
    ordering = ('name',)


class StudyDocumentForm(forms.ModelForm):
    pdf_upload = forms.FileField(
        label='Subir PDF',
        required=False,
        help_text='Se convertirá a JPG automáticamente.',
    )

    class Meta:
        model = StudyDocument
        fields = ('description',)

    def clean(self):
        cleaned = super().clean()
        pdf = cleaned.get('pdf_upload')
        is_new = not (self.instance and self.instance.pk)
        if is_new and not pdf:
            if cleaned.get('description'):
                raise forms.ValidationError('Debes adjuntar un PDF para crear el documento.')
            return cleaned
        if pdf and not pdf.name.lower().endswith('.pdf'):
            raise forms.ValidationError('El archivo debe ser un PDF.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        pdf = self.cleaned_data.get('pdf_upload')
        if pdf:
            jpg_bytes = pdf_first_page_to_jpeg(pdf)
            base = pdf.name.rsplit('.', 1)[0]
            instance.image.save(f'{base}.jpg', ContentFile(jpg_bytes), save=False)
        if commit:
            instance.save()
        return instance


class StudyDocumentInline(admin.TabularInline):
    model = StudyDocument
    form = StudyDocumentForm
    extra = 2
    fields = ('pdf_upload', 'image', 'width', 'height', 'description')
    readonly_fields = ('image', 'width', 'height')


@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = (
        'access_number', 'patient', 'body_part',
        'exposure_date', 'exposure_time', 'performing_physician',
        'document_count',
    )
    list_filter = ('body_part', 'exposure_date')
    search_fields = (
        'access_number', 'patient__name',
        'referring_physician', 'performing_physician', 'body_part',
    )
    autocomplete_fields = ('patient',)
    date_hierarchy = 'exposure_date'
    inlines = [StudyDocumentInline]

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
            'fields': (('bits_allocated', 'bits_stored'),),
        }),
    )

    @admin.display(description='Imágenes')
    def document_count(self, obj):
        return obj.documents.count()
