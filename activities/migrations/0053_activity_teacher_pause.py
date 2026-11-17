from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def preserve_manual_off(apps, schema_editor):
    activity_model = apps.get_model('activities', 'Activity')
    now = timezone.now()
    in_period = (
        (Q(start_time__isnull=True) | Q(start_time__lte=now))
        & (Q(deadline__isnull=True) | Q(deadline__gte=now))
    )
    activity_model.objects.filter(in_period, is_active=False).update(is_paused=True)


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0052_proctor_session_capture_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='is_paused',
            field=models.BooleanField(default=False, verbose_name='교사 일시중지 여부'),
        ),
        migrations.RunPython(preserve_manual_off, migrations.RunPython.noop),
    ]
