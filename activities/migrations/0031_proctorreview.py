import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activities', '0030_proctor_security_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProctorReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('review_date', models.DateField(verbose_name='기록 날짜')),
                ('status', models.CharField(choices=[('UNREVIEWED', '미검토'), ('CLEARED', '이상 없음'), ('ATTENTION', '확인 필요')], default='UNREVIEWED', max_length=16)),
                ('note', models.CharField(blank=True, max_length=500, verbose_name='검토 메모')),
                ('reviewed_at', models.DateTimeField(blank=True, null=True, verbose_name='검토 시각')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('activity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proctor_reviews', to='activities.activity', verbose_name='활동')),
                ('reviewer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='proctor_reviews', to=settings.AUTH_USER_MODEL, verbose_name='검토자')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proctor_reviews', to='accounts.student', verbose_name='학생')),
            ],
        ),
        migrations.AddConstraint(
            model_name='proctorreview',
            constraint=models.UniqueConstraint(fields=('activity', 'student', 'review_date'), name='unique_proctor_review_day'),
        ),
        migrations.AddIndex(
            model_name='proctorreview',
            index=models.Index(fields=['activity', 'review_date', 'status'], name='proctor_review_day_idx'),
        ),
    ]
