from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0018_answerdraftrevision'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedbackresult',
            name='is_published',
            field=models.BooleanField(default=False, verbose_name='학생 공개 여부'),
        ),
        migrations.AddField(
            model_name='feedbackresult',
            name='is_read',
            field=models.BooleanField(default=False, verbose_name='학생 열람 여부'),
        ),
        migrations.AddField(
            model_name='feedbackresult',
            name='published_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='학생 공개 일시'),
        ),
        migrations.AddField(
            model_name='feedbackresult',
            name='read_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='학생 최초 열람 일시'),
        ),
        migrations.AddField(
            model_name='feedbackresult',
            name='source_session',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='final_result',
                to='activities.feedbacksession',
                verbose_name='원본 피드백 작업 세션',
            ),
        ),
    ]
