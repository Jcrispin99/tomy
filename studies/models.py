from django.db import models
from django.db.models import CheckConstraint, Q


class Patient(models.Model):
    SEX_CHOICES = [('V', 'Varón'), ('M', 'Mujer')]

    name = models.CharField('Nombre', max_length=200)
    sex = models.CharField('Sexo', max_length=1, choices=SEX_CHOICES)
    age = models.PositiveSmallIntegerField('Edad')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Paciente'
        verbose_name_plural = 'Pacientes'
        ordering = ['name']
        constraints = [
            CheckConstraint(
                check=Q(sex__in=['V', 'M']),
                name='patient_sex_valid',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_sex_display()}, {self.age})'


class Study(models.Model):
    patient = models.ForeignKey(
        Patient, on_delete=models.PROTECT, related_name='studies',
        verbose_name='Paciente',
    )
    access_number = models.PositiveIntegerField(
        'N° de acceso', unique=True, null=True, blank=True,
    )

    register_date = models.DateField('Fecha de registro')
    register_time = models.TimeField('Hora de registro')
    exposure_date = models.DateField('Fecha de exposición')
    exposure_time = models.TimeField('Hora de exposición')

    body_part = models.CharField(
        'Parte del cuerpo', max_length=100, blank=True,
    )
    referring_physician = models.CharField(
        'Médico referente', max_length=200,
    )
    performing_physician = models.CharField(
        'Médico ejecutor', max_length=200,
    )

    image_width = models.PositiveIntegerField('Ancho (px)')
    image_height = models.PositiveIntegerField('Alto (px)')
    bits_allocated = models.PositiveSmallIntegerField('Bits asignados')
    bits_stored = models.PositiveSmallIntegerField('Bits usados')

    pdf = models.FileField('PDF', upload_to='studies/%Y/%m/')

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
