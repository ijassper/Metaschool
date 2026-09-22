from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('activities', '0026_activity_proctor_mode_proctorsnapshot')]

    operations = [
        migrations.CreateModel(
            name='ProctorSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('WAITING', '대기'), ('RECORDING', '녹화 중'), ('AWAY', '앱 이탈'), ('DISCONNECTED', '연결 끊김'), ('ENDED', '종료'), ('ERROR', '오류')], default='WAITING', max_length=20)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('last_seen_at', models.DateTimeField(blank=True, null=True)),
                ('left_at', models.DateTimeField(blank=True, null=True)),
                ('returned_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('last_message', models.CharField(blank=True, max_length=255)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('activity', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proctor_sessions', to='activities.activity', verbose_name='활동')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='proctor_sessions', to='accounts.student', verbose_name='학생')),
            ],
        ),
        migrations.CreateModel(
            name='ProctorEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('CAPTURE_STARTED', '녹화 시작'), ('APP_BACKGROUND', '앱 이탈'), ('APP_FOREGROUND', '앱 복귀'), ('CAPTURE_STOPPED', '녹화 중단'), ('EXAM_ENDED', '시험 종료'), ('ERROR', '오류')], max_length=30)),
                ('client_occurred_at', models.DateTimeField(blank=True, null=True)),
                ('message', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='activities.proctorsession', verbose_name='감독 세션')),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
        migrations.AddConstraint(
            model_name='proctorsession',
            constraint=models.UniqueConstraint(fields=('activity', 'student'), name='unique_proctor_session'),
        ),
        migrations.AddIndex(
            model_name='proctorsession',
            index=models.Index(fields=['activity', 'status'], name='proctor_session_status_idx'),
        ),
        migrations.AddIndex(
            model_name='proctorevent',
            index=models.Index(fields=['session', '-created_at'], name='proctor_event_time_idx'),
        ),
    ]
