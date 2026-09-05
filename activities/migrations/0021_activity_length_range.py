from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def migrate_limit_to_range(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    Activity.objects.filter(limit_type='MAX').update(
        min_length=0,
        max_length=models.F('limit_count'),
        limit_type='RANGE',
    )
    Activity.objects.filter(limit_type='MIN').update(
        min_length=models.F('limit_count'),
        max_length=99999,
        limit_type='RANGE',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0020_activity_character_limit_engine'),
    ]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='max_length',
            field=models.PositiveIntegerField(
                default=99999,
                validators=[MinValueValidator(0), MaxValueValidator(99999)],
                verbose_name='최대 글자 수',
            ),
        ),
        migrations.AddField(
            model_name='activity',
            name='min_length',
            field=models.PositiveIntegerField(
                default=0,
                validators=[MinValueValidator(0), MaxValueValidator(99999)],
                verbose_name='최소 글자 수',
            ),
        ),
        migrations.AlterField(
            model_name='activity',
            name='limit_type',
            field=models.CharField(
                choices=[
                    ('NONE', '제한 없음'), ('RANGE', '글자 수 범위 제한'),
                    ('MAX', '글자 수 이내'), ('MIN', '글자 수 이상'),
                ],
                default='NONE', max_length=5, verbose_name='글자 수 제한 유형',
            ),
        ),
        migrations.RunPython(migrate_limit_to_range, migrations.RunPython.noop),
    ]
