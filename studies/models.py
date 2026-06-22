from django.db import models
from django.db.models import CheckConstraint, Q


class Patient(models.Model):
    SEX_CHOICES = [('V', 'Varón'), ('M', 'Mujer')]

    name = models.CharField('Nombre', max_length=200)
    sex = models.CharField('Sexo', max_length=1, choices=SEX_CHOICES, blank=True)
    age = models.PositiveSmallIntegerField('Edad', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Paciente'
        verbose_name_plural = 'Pacientes'
        ordering = ['name']
        constraints = [
            CheckConstraint(
                check=Q(sex__in=['V', 'M', '']),
                name='patient_sex_valid',
            ),
        ]

    def __str__(self):
        if self.age is not None and self.sex:
            return f'{self.name} ({self.get_sex_display()}, {self.age})'
        return self.name


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
        return f'{ref} — {self.patient.name}'


class StudyDocument(models.Model):
    study = models.ForeignKey(
        Study, on_delete=models.CASCADE, related_name='documents',
        verbose_name='Estudio',
    )
    image = models.ImageField(
        'Imagen JPG', upload_to='studies/%Y/%m/',
        width_field='width', height_field='height',
    )
    width = models.PositiveIntegerField('Ancho (px)', null=True, blank=True)
    height = models.PositiveIntegerField('Alto (px)', null=True, blank=True)
    body_part = models.ForeignKey(
        BodyPart, on_delete=models.PROTECT, null=True, blank=True,
        related_name='documents', verbose_name='Parte del cuerpo',
    )
    date = models.DateField('Fecha', null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'
        ordering = ['uploaded_at']

    def __str__(self):
        return self.image.name.rsplit('/', 1)[-1]
