from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def migrate_legacy_character_limits(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    Activity.objects.filter(char_limit__gt=0).update(
        limit_type='MAX',
        limit_count=models.F('char_limit'),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0019_feedbackresult_publication_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='limit_count',
            field=models.PositiveIntegerField(
                default=0,
                validators=[MinValueValidator(0), MaxValueValidator(10000)],
                verbose_name='글자 수 제한 기준',
            ),
        ),
        migrations.AddField(
            model_name='activity',
            name='limit_type',
            field=models.CharField(
                choices=[('NONE', '제한 없음'), ('MAX', '글자 수 이내'), ('MIN', '글자 수 이상')],
                default='NONE',
                max_length=4,
                verbose_name='글자 수 제한 유형',
            ),
        ),
        migrations.RunPython(migrate_legacy_character_limits, migrations.RunPython.noop),
    ]
