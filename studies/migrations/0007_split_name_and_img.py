from django.db import migrations, models


def partir_nombre(texto: str) -> tuple[str, str]:
    """Heuristica simple: primera mitad apellidos, segunda mitad nombres.
    Si solo hay una palabra, va a last_name.
    """
    texto = (texto or '').strip().strip(';,').strip()
    if not texto:
        return '', ''
    partes = texto.split()
    if len(partes) == 1:
        return partes[0], ''
    mitad = len(partes) // 2 or 1
    return ' '.join(partes[:mitad]), ' '.join(partes[mitad:])


def migrar_pacientes_y_estudios(apps, schema_editor):
    Patient = apps.get_model('studies', 'Patient')
    for idx, p in enumerate(Patient.objects.order_by('created_at', 'pk'), start=1):
        last, first = partir_nombre(p.name)
        p.last_name = last
        p.first_name = first
        p.code = f'{idx:07d}'
        p.save(update_fields=['last_name', 'first_name', 'code'])


def revertir(apps, schema_editor):
    Patient = apps.get_model('studies', 'Patient')
    for p in Patient.objects.all():
        nombre = f'{p.last_name} {p.first_name}'.strip()
        p.name = nombre or 'sin nombre'
        p.save(update_fields=['name'])


class Migration(migrations.Migration):

    dependencies = [
        ('studies', '0006_remove_studydocument_description'),
    ]

    operations = [
        # 1) Campos nuevos nullable/blank para poder rellenarlos
        migrations.AddField(
            model_name='patient',
            name='last_name',
            field=models.CharField(default='', max_length=120, verbose_name='Apellidos'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='patient',
            name='first_name',
            field=models.CharField(default='', max_length=120, verbose_name='Nombres'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='patient',
            name='code',
            field=models.CharField(
                editable=False, max_length=8, null=True,
                help_text='Correlativo autogenerado (0000001, 0000002, ...).',
                verbose_name='Código',
            ),
        ),
        migrations.AddField(
            model_name='study',
            name='study_uid',
            field=models.CharField(blank=True, default='', max_length=64,
                                   verbose_name='Study Instance UID'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='study',
            name='series_uid',
            field=models.CharField(blank=True, default='', max_length=64,
                                   verbose_name='Series Instance UID'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='studydocument',
            name='instance_uid',
            field=models.CharField(blank=True, default='', max_length=64,
                                   verbose_name='SOP Instance UID'),
            preserve_default=False,
        ),

        # 2) Migrar datos existentes
        migrations.RunPython(migrar_pacientes_y_estudios, revertir),

        # 3) Promover code a unique (los datos ya estan llenos)
        migrations.AlterField(
            model_name='patient',
            name='code',
            field=models.CharField(
                editable=False, max_length=8, unique=True,
                help_text='Correlativo autogenerado (0000001, 0000002, ...).',
                verbose_name='Código',
            ),
        ),

        # 4) Cambiar StudyDocument.image -> img_file
        migrations.RemoveField(model_name='studydocument', name='image'),
        migrations.AddField(
            model_name='studydocument',
            name='img_file',
            field=models.FileField(
                default='', upload_to='studies/%Y/%m/',
                verbose_name='Archivo .img',
            ),
            preserve_default=False,
        ),

        # 5) Quitar Patient.name
        migrations.RemoveField(model_name='patient', name='name'),

        # 6) Actualizar Meta de Patient
        migrations.AlterModelOptions(
            name='patient',
            options={
                'ordering': ['last_name', 'first_name'],
                'verbose_name': 'Paciente',
                'verbose_name_plural': 'Pacientes',
            },
        ),
    ]
