import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from pathlib import Path

from django import forms
from django.contrib import admin
from django.core.files import File
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from scripts_img.empaquetar_img import (
    DatosEstudio,
    DatosPaciente,
    empaquetar_img,
    generar_uid,
    pdf_a_pixeles,
)
from scripts_img.render_img import renderizar_img

from .models import BodyPart, Patient, Study, StudyDocument


# Vieworks FXRD-1717VA siempre escribe pixeles de 14 bits en uint16.
DEFAULT_BITS_ALLOCATED = 16
DEFAULT_BITS_STORED = 14


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('code', 'last_name', 'first_name', 'sex', 'age', 'created_at')
    list_filter = ('sex',)
    search_fields = ('code', 'last_name', 'first_name')
    readonly_fields = ('code',)
    ordering = ('last_name', 'first_name')


@admin.register(BodyPart)
class BodyPartAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    ordering = ('name',)


class StudyDocumentForm(forms.ModelForm):
    pdf_upload = forms.FileField(
        label='Subir PDF',
        required=False,
        help_text='Se renderiza a 3072×3072 y se empaqueta como .img Vieworks.',
    )

    class Meta:
        model = StudyDocument
        fields = ('body_part', 'date', 'time')

    def clean(self):
        cleaned = super().clean()
        pdf = cleaned.get('pdf_upload')
        is_new = not (self.instance and self.instance.pk)
        # Fila totalmente vacia: la ignoramos para que no falle el inline
        if is_new and not pdf and not any([
            cleaned.get('body_part'), cleaned.get('date'),
            cleaned.get('time'),
        ]):
            return cleaned
        if is_new and not pdf:
            raise forms.ValidationError('Debes adjuntar un PDF para crear el documento.')
        if pdf and not pdf.name.lower().endswith('.pdf'):
            raise forms.ValidationError('El archivo debe ser un PDF.')
        if is_new and not cleaned.get('date'):
            raise forms.ValidationError('Indica la fecha del examen.')
        return cleaned


class StudyDocumentInline(admin.TabularInline):
    model = StudyDocument
    form = StudyDocumentForm
    fields = ('pdf_upload', 'body_part', 'date', 'time')
    verbose_name = 'Documento'
    verbose_name_plural = 'Documentos'

    def get_extra(self, request, obj=None, **kwargs):
        # Sin documentos previos: mostramos 1 fila lista para llenar.
        # Con documentos: 0 filas extra, el usuario pulsa "Agregar" si quiere mas.
        if obj and obj.pk and obj.documents.exists():
            return 0
        return 1


@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = ('paciente_link', 'body_parts', 'register_date',
                    'document_count', 'visor_link')
    list_display_links = ('paciente_link',)
    list_filter = ('documents__body_part', 'register_date')
    search_fields = (
        'patient__code', 'patient__last_name', 'patient__first_name',
        'documents__body_part__name',
    )
    autocomplete_fields = ('patient',)
    date_hierarchy = 'register_date'
    inlines = [StudyDocumentInline]

    fieldsets = (
        ('Paciente', {
            'fields': ('patient',),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.register_date:
            now = timezone.localtime()
            obj.register_date = now.date()
            obj.register_time = now.time().replace(microsecond=0)
        if not obj.study_uid:
            obj.study_uid = generar_uid()
        if not obj.series_uid:
            obj.series_uid = generar_uid()
        obj.bits_allocated = DEFAULT_BITS_ALLOCATED
        obj.bits_stored = DEFAULT_BITS_STORED
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        study = form.instance
        for formset in formsets:
            if formset.model is not StudyDocument:
                continue
            for sub_form in formset.forms:
                if not sub_form.cleaned_data:
                    continue
                doc = sub_form.instance
                if not doc.pk or doc.img_file:
                    continue
                pdf = sub_form.cleaned_data.get('pdf_upload')
                if not pdf:
                    continue
                self._generar_img_para_documento(study, doc, pdf)

    @staticmethod
    def _generar_img_para_documento(study: Study, doc: StudyDocument, pdf_file) -> None:
        if not study.study_uid:
            study.study_uid = generar_uid()
        if not study.series_uid:
            study.series_uid = generar_uid()
        if not study.bits_allocated or not study.bits_stored:
            study.bits_allocated = DEFAULT_BITS_ALLOCATED
            study.bits_stored = DEFAULT_BITS_STORED
        study.save(update_fields=['study_uid', 'series_uid',
                                  'bits_allocated', 'bits_stored'])

        if not doc.instance_uid:
            doc.instance_uid = generar_uid()

        patient = study.patient
        paciente = DatosPaciente(
            code=patient.code,
            last_name=patient.last_name,
            first_name=patient.first_name,
            sex=patient.dicom_sex(),
            age=patient.age,
            birth_date='',
        )
        body_part_nombre = (doc.body_part.name if doc.body_part else '').upper()
        fecha = doc.date
        hora = doc.time or study.register_time or timezone.localtime().time()
        estudio = DatosEstudio(
            study_uid=study.study_uid,
            series_uid=study.series_uid,
            instance_uid=doc.instance_uid,
            body_part=body_part_nombre,
            study_date=fecha.strftime('%Y%m%d') if fecha else '',
            study_time=hora.strftime('%H%M%S'),
            accession_number=str(study.access_number or ''),
            performing_physician=study.performing_physician or 'rayosx^^^^',
            institution='CENTRO MEDICO TINTAYA',
        )

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
            for chunk in pdf_file.chunks():
                tmp_pdf.write(chunk)
            tmp_pdf_path = Path(tmp_pdf.name)
        with tempfile.NamedTemporaryFile(suffix='.img', delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            pixeles = pdf_a_pixeles(tmp_pdf_path)
            empaquetar_img(tmp_path, paciente, estudio, pixeles)
            nombre = f'{patient.code}_{doc.instance_uid.split(".")[-1][:8]}.img'
            with tmp_path.open('rb') as fh:
                doc.img_file.save(nombre, File(fh), save=False)
            doc.width = 3072
            doc.height = 3072
            doc.save(update_fields=['img_file', 'instance_uid', 'width', 'height'])
        finally:
            tmp_path.unlink(missing_ok=True)
            tmp_pdf_path.unlink(missing_ok=True)

    @admin.display(description='Paciente', ordering='patient__last_name')
    def paciente_link(self, obj):
        return (f'{obj.patient.code} — {obj.patient.last_name}, '
                f'{obj.patient.first_name}')

    @admin.display(description='Visor')
    def visor_link(self, obj):
        if not obj.documents.exclude(img_file='').exists():
            return '—'
        url = reverse('admin:studies_study_visor', args=[obj.pk])
        return format_html(
            '<a href="{}" class="button" style="padding:3px 10px;">Ver</a>',
            url,
        )

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

    # --- Exportación de .img por rango de fechas ---
    PRESETS = {
        'hoy': 'Hoy',
        'ayer': 'Ayer',
        'semana': 'Esta semana',
        'mes': 'Este mes',
    }

    def get_urls(self):
        custom = [
            path(
                'exportar/',
                self.admin_site.admin_view(self.exportar_view),
                name='studies_study_exportar',
            ),
            path(
                '<int:pk>/visor/',
                self.admin_site.admin_view(self.visor_view),
                name='studies_study_visor',
            ),
            path(
                'documento/<int:doc_pk>/preview.png',
                self.admin_site.admin_view(self.preview_view),
                name='studies_study_preview',
            ),
        ]
        return custom + super().get_urls()

    def preview_view(self, request, doc_pk):
        doc = get_object_or_404(StudyDocument, pk=doc_pk)
        if not doc.img_file:
            raise Http404('Sin archivo .img')
        try:
            png = renderizar_img(Path(doc.img_file.path), max_size=1024)
        except Exception as e:
            raise Http404(f'Error al renderizar: {e}')
        from django.http import HttpResponse
        return HttpResponse(png, content_type='image/png')

    # --- Visor de imagenes ---
    FIRMA_XML = "<?xml".encode("utf-16-le")

    def visor_view(self, request, pk):
        study = get_object_or_404(Study.objects.select_related('patient'), pk=pk)
        documentos = (
            study.documents
            .exclude(img_file='')
            .select_related('body_part')
            .order_by('date', 'time', 'id')
        )

        items = []
        for doc in documentos:
            meta = self._leer_metadatos_img(Path(doc.img_file.path))
            descarga_url = doc.img_file.url if doc.img_file else None
            items.append({
                'doc': doc,
                'meta': meta,
                'descarga_url': descarga_url,
                'tamano': doc.img_file.size if doc.img_file else 0,
            })

        embed = request.GET.get('embed') == '1'
        contexto = {
            'study': study,
            'items': items,
        }
        if embed:
            return render(request, 'admin/studies/study/visor_embed.html', contexto)

        contexto.update({
            **self.admin_site.each_context(request),
            'title': f'Visor — {study}',
            'opts': self.model._meta,
            'cambiar_url': reverse('admin:studies_study_change', args=[study.pk]),
            'changelist_url': reverse('admin:studies_study_changelist'),
        })
        return render(request, 'admin/studies/study/visor.html', contexto)

    @classmethod
    def _leer_metadatos_img(cls, ruta: Path) -> dict | None:
        try:
            data = ruta.read_bytes()
        except OSError:
            return None
        pos = data.find(cls.FIRMA_XML)
        if pos < 0:
            return None
        try:
            xml_texto = data[pos:].decode('utf-16-le', errors='replace')
            root = ET.fromstring(xml_texto)
        except ET.ParseError:
            return None

        def attrs(path):
            node = root.find(path)
            return dict(node.attrib) if node is not None else {}

        pac = attrs('PATIENT_INFO/Patient')
        est_p = attrs('STUDY_INFO/Patient')
        est = attrs('STUDY_INFO/Study')
        inst = attrs('INSTANCE_INFO/Instance')
        det = attrs('INSTANCE_INFO/Detector')
        dose = attrs('INSTANCE_INFO/Dose')
        series = attrs('SERIES_INFO/Series')

        return {
            'paciente_id': pac.get('ID', ''),
            'paciente_nombre': pac.get('Name', '').replace('^', ' ').strip(),
            'paciente_sexo': pac.get('Sex', ''),
            'paciente_edad': est_p.get('Age', ''),
            'estudio_fecha': est.get('Date', ''),
            'estudio_hora': est.get('Time', ''),
            'modalidad': series.get('Modality', ''),
            'parte': series.get('BodypartExamined', ''),
            'tamano_px': f'{inst.get("Width", "?")} × {inst.get("Height", "?")}',
            'bits': inst.get('UsingBits', ''),
            'detector': f'{det.get("ManufacturerName", "")} '
                        f'{det.get("ManufacturerModelName", "")}'.strip(),
            'kvp': dose.get('KVP', ''),
            'mas': dose.get('MAS', ''),
            'uid_instancia': inst.get('InstanceUID', ''),
        }

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['exportar_url'] = reverse('admin:studies_study_exportar')
        return super().changelist_view(request, extra_context=extra_context)

    @staticmethod
    def _resolver_rango(preset: str, desde: str, hasta: str) -> tuple[date, date]:
        hoy = timezone.localdate()
        if preset == 'hoy':
            return hoy, hoy
        if preset == 'ayer':
            ayer = hoy - timedelta(days=1)
            return ayer, ayer
        if preset == 'semana':
            inicio = hoy - timedelta(days=hoy.weekday())
            return inicio, hoy
        if preset == 'mes':
            return hoy.replace(day=1), hoy
        d_desde = date.fromisoformat(desde) if desde else hoy
        d_hasta = date.fromisoformat(hasta) if hasta else hoy
        if d_hasta < d_desde:
            d_desde, d_hasta = d_hasta, d_desde
        return d_desde, d_hasta

    @staticmethod
    def _slug(texto: str) -> str:
        texto = re.sub(r'[^A-Za-z0-9]+', '_', (texto or '').upper()).strip('_')
        return texto or 'SIN_DATO'

    def _documentos_en_rango(self, desde: date, hasta: date):
        return (
            StudyDocument.objects
            .filter(
                study__register_date__gte=desde,
                study__register_date__lte=hasta,
            )
            .exclude(img_file='')
            .select_related('study__patient', 'body_part')
            .order_by('study__register_date', 'study__id', 'id')
        )

    def exportar_view(self, request):
        preset = request.GET.get('preset', 'hoy')
        desde_raw = request.GET.get('desde', '')
        hasta_raw = request.GET.get('hasta', '')

        try:
            desde, hasta = self._resolver_rango(preset, desde_raw, hasta_raw)
        except ValueError:
            return HttpResponseBadRequest('Fechas inválidas (usa YYYY-MM-DD).')

        documentos = list(self._documentos_en_rango(desde, hasta))

        if request.GET.get('descargar'):
            return self._descargar_zip(documentos, desde, hasta)

        contexto = {
            **self.admin_site.each_context(request),
            'title': 'Exportar .img',
            'opts': self.model._meta,
            'presets': self.PRESETS,
            'preset': preset,
            'desde': desde.isoformat(),
            'hasta': hasta.isoformat(),
            'total_documentos': len(documentos),
            'tamano_total': sum(
                (d.img_file.size if d.img_file else 0) for d in documentos
            ),
            'documentos_preview': documentos[:20],
            'documentos_extra': max(len(documentos) - 20, 0),
            'changelist_url': reverse('admin:studies_study_changelist'),
        }
        return render(request, 'admin/studies/study/exportar.html', contexto)

    def _descargar_zip(self, documentos, desde: date, hasta: date) -> FileResponse:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        usados: dict[str, int] = {}
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as zf:
            for doc in documentos:
                if not doc.img_file:
                    continue
                paciente = doc.study.patient
                body = doc.body_part.name if doc.body_part else 'SIN_PARTE'
                fecha = doc.study.register_date or doc.uploaded_at.date()
                base = (
                    f'{paciente.code}_'
                    f'{self._slug(paciente.last_name)}_'
                    f'{self._slug(paciente.first_name)}_'
                    f'{self._slug(body)}_'
                    f'{fecha.strftime("%Y%m%d")}'
                )
                n = usados.get(base, 0) + 1
                usados[base] = n
                nombre = f'{base}.img' if n == 1 else f'{base}_{n}.img'
                zf.write(doc.img_file.path, arcname=nombre)
        tmp.flush()
        tmp.seek(0)

        rango = (
            desde.strftime('%Y%m%d')
            if desde == hasta
            else f'{desde:%Y%m%d}_{hasta:%Y%m%d}'
        )
        return FileResponse(
            open(tmp.name, 'rb'),
            as_attachment=True,
            filename=f'export_img_{rango}.zip',
            content_type='application/zip',
        )
