import datetime

from django.db import migrations, models


def backfill_dates(apps, schema_editor):
    StudyDocument = apps.get_model('studies', 'StudyDocument')
    for doc in StudyDocument.objects.filter(date__isnull=True):
        doc.date = doc.study.register_date or doc.uploaded_at.date()
        doc.save(update_fields=['date'])


class Migration(migrations.Migration):

    dependencies = [
        ('studies', '0007_split_name_and_img'),
    ]

    operations = [
        migrations.AddField(
            model_name='studydocument',
            name='time',
            field=models.TimeField(blank=True, null=True,
                                   verbose_name='Hora del examen'),
        ),
        migrations.RunPython(backfill_dates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='studydocument',
            name='date',
            field=models.DateField(verbose_name='Fecha del examen'),
        ),
    ]
