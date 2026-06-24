from django.db import models
from django.db.models import CheckConstraint, Q


class Patient(models.Model):
    SEX_CHOICES = [('V', 'Varón'), ('M', 'Mujer')]

    code = models.CharField(
        'Código', max_length=8, unique=True, editable=False,
        help_text='Correlativo autogenerado (0000001, 0000002, ...).',
    )
    last_name = models.CharField('Apellidos', max_length=120)
    first_name = models.CharField('Nombres', max_length=120)
    sex = models.CharField('Sexo', max_length=1, choices=SEX_CHOICES, blank=True)
    age = models.PositiveSmallIntegerField('Edad', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Paciente'
        verbose_name_plural = 'Pacientes'
        ordering = ['last_name', 'first_name']
        constraints = [
            CheckConstraint(
                check=Q(sex__in=['V', 'M', '']),
                name='patient_sex_valid',
            ),
        ]

    def __str__(self):
        return f'{self.code} — {self.last_name}, {self.first_name}'

    @property
    def full_name(self) -> str:
        return f'{self.last_name}, {self.first_name}'.strip(', ')

    def dicom_name(self) -> str:
        return f'{self.last_name.strip()}^{self.first_name.strip()}^^^'

    def dicom_sex(self) -> str:
        return {'V': 'M', 'M': 'F'}.get(self.sex, '')

    @classmethod
    def siguiente_code(cls) -> str:
        ultimo = cls.objects.order_by('-code').values_list('code', flat=True).first()
        n = int(ultimo) + 1 if ultimo and ultimo.isdigit() else 1
        return f'{n:07d}'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.siguiente_code()
        super().save(*args, **kwargs)


class BodyPart(models.Model):
    name = models.CharField('Nombre', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Parte del cuerpo'
        verbose_name_plural = 'Partes del cuerpo'
        ordering = ['name']

    def __str__(self):
        return self.name


class Study(models.Model):
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name='studies',
        verbose_name='Paciente',
    )
    access_number = models.PositiveIntegerField(
        'N° de acceso', unique=True, null=True, blank=True,
    )

    register_date = models.DateField('Fecha de registro', null=True, blank=True)
    register_time = models.TimeField('Hora de registro', null=True, blank=True)
    exposure_date = models.DateField('Fecha de exposición', null=True, blank=True)
    exposure_time = models.TimeField('Hora de exposición', null=True, blank=True)

    referring_physician = models.CharField(
        'Médico referente', max_length=200, blank=True,
    )
    performing_physician = models.CharField(
        'Médico ejecutor', max_length=200, blank=True,
    )

    bits_allocated = models.PositiveSmallIntegerField(
        'Bits asignados', null=True, blank=True,
    )
    bits_stored = models.PositiveSmallIntegerField(
        'Bits usados', null=True, blank=True,
    )

    study_uid = models.CharField('Study Instance UID', max_length=64, blank=True)
    series_uid = models.CharField('Series Instance UID', max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Estudio'
        verbose_name_plural = 'Estudios'
        ordering = ['-exposure_date', '-exposure_time']
        constraints = [
            CheckConstraint(
                check=Q(bits_stored__lte=models.F('bits_allocated')),
                name='study_bits_stored_le_allocated',
            ),
            CheckConstraint(
                check=Q(exposure_date__lte=models.F('register_date')),
                name='study_exposure_before_register',
            ),
        ]

    def __str__(self):
        ref = self.access_number or f'#{self.pk}'
        return f'{ref} — {self.patient.full_name}'


class StudyDocument(models.Model):
    study = models.ForeignKey(
        Study, on_delete=models.CASCADE, related_name='documents',
        verbose_name='Estudio',
    )
    img_file = models.FileField(
        'Archivo .img', upload_to='studies/%Y/%m/',
    )
    width = models.PositiveIntegerField('Ancho (px)', null=True, blank=True)
    height = models.PositiveIntegerField('Alto (px)', null=True, blank=True)
    instance_uid = models.CharField(
        'SOP Instance UID', max_length=64, blank=True,
    )
    body_part = models.ForeignKey(
        BodyPart, on_delete=models.PROTECT, null=True, blank=True,
        related_name='documents', verbose_name='Parte del cuerpo',
    )
    date = models.DateField('Fecha del examen')
    time = models.TimeField('Hora del examen', null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'
        ordering = ['uploaded_at']

    def __str__(self):
        return self.img_file.name.rsplit('/', 1)[-1]
