from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('activities', '0025_feedbackresult_is_rewrite_assigned'),
    ]

    operations = [
        migrations.AddField(
            model_name='activity',
            name='proctor_mode',
            field=models.BooleanField(default=False, verbose_name='감독 모드'),
        ),
        migrations.CreateModel(
            name='ProctorSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.FileField(upload_to='proctor_snapshots/%Y/%m/%d/', verbose_name='화면 이미지')),
                ('client_captured_at', models.DateTimeField(blank=True, null=True, verbose_name='학생 기기 촬영 시각')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='서버 수신 시각')),
                ('activity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proctor_snapshots', to='activities.activity', verbose_name='활동')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proctor_snapshots', to='accounts.student', verbose_name='학생')),
            ],
            options={
                'verbose_name': '감독 화면 스냅숏',
                'verbose_name_plural': '감독 화면 스냅숏 목록',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='proctorsnapshot',
            index=models.Index(fields=['activity', 'student', '-created_at'], name='proctor_activity_student_idx'),
        ),
        migrations.AddIndex(
            model_name='proctorsnapshot',
            index=models.Index(fields=['activity', '-created_at'], name='proctor_activity_time_idx'),
        ),
    ]
