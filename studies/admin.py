from django import forms
from django.contrib import admin
from django.core.files.base import ContentFile
from django.utils import timezone

import fitz
from PIL import Image

from .models import BodyPart, Patient, Study, StudyDocument


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


_MODE_BITS = {
    '1': (8, 1),
    'L': (8, 8),
    'P': (8, 8),
    'RGB': (8, 8),
    'RGBA': (8, 8),
    'I;16': (16, 16),
    'I': (32, 32),
    'F': (32, 32),
}


def image_bits(image_field):
    image_field.open('rb')
    try:
        with Image.open(image_field) as img:
            return _MODE_BITS.get(img.mode, (8, 8))
    finally:
        image_field.close()


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('name', 'sex', 'age', 'created_at')
    list_filter = ('sex',)
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(BodyPart)
class BodyPartAdmin(admin.ModelAdmin):
    list_display = ('name',)
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
        fields = ('body_part', 'date')

    def clean(self):
        cleaned = super().clean()
        pdf = cleaned.get('pdf_upload')
        is_new = not (self.instance and self.instance.pk)
        if is_new and not pdf:
            if cleaned.get('body_part') or cleaned.get('date'):
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
    fields = ('pdf_upload', 'body_part', 'date')


@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = ('patient', 'body_parts', 'register_date', 'document_count')
    list_filter = ('documents__body_part', 'register_date')
    search_fields = (
        'patient__name', 'documents__body_part__name',
    )
    autocomplete_fields = ('patient',)
    date_hierarchy = 'register_date'
    inlines = [StudyDocumentInline]

    fieldsets = (
        ('Paciente y acceso', {
            'fields': ('patient', 'access_number'),
        }),
        ('Registro', {
            'fields': (('register_date', 'register_time'),),
        }),
    )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        now = timezone.localtime()
        initial.setdefault('register_date', now.date())
        initial.setdefault('register_time', now.time().replace(microsecond=0))
        return initial

    def save_model(self, request, obj, form, change):
        obj.exposure_date = obj.register_date
        obj.exposure_time = obj.register_time
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        study = form.instance
        first_doc = study.documents.first()
        if first_doc and first_doc.image:
            bits_allocated, bits_stored = image_bits(first_doc.image)
            if (study.bits_allocated != bits_allocated
                    or study.bits_stored != bits_stored):
                study.bits_allocated = bits_allocated
                study.bits_stored = bits_stored
                study.save(update_fields=['bits_allocated', 'bits_stored'])

    @admin.display(description='Imágenes')
    def document_count(self, obj):
        return obj.documents.count()

    @admin.display(description='Partes del cuerpo')
    def body_parts(self, obj):
        names = (
            obj.documents
            .exclude(body_part__isnull=True)
            .values_list('body_part__name', flat=True)
            .distinct()
        )
        return ', '.join(names) or '—'
