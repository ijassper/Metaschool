import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def rename_scratchpad(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    Activity.objects.filter(sub_category='수업 노트/연습장').update(sub_category='다목적 연습장')


def restore_scratchpad_name(apps, schema_editor):
    Activity = apps.get_model('activities', 'Activity')
    Activity.objects.filter(sub_category='다목적 연습장').update(sub_category='수업 노트/연습장')


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('activities', '0031_proctorreview'),
    ]
    operations = [
        migrations.CreateModel(
            name='CourseNotebook',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=120, verbose_name='노트 이름')),
                ('subject', models.CharField(max_length=60, verbose_name='과목명')),
                ('academic_year', models.PositiveSmallIntegerField(verbose_name='학년도')),
                ('semester', models.CharField(choices=[('1', '1학기'), ('2', '2학기'), ('YEAR', '연간')], default='1', max_length=8)),
                ('description', models.TextField(blank=True, max_length=1000, verbose_name='사용 안내')),
                ('cover_color', models.CharField(choices=[('PURPLE', '보라'), ('BLUE', '파랑'), ('GREEN', '초록'), ('ORANGE', '주황'), ('PINK', '분홍'), ('GRAY', '회색')], default='PURPLE', max_length=12, verbose_name='표지 색상')),
                ('is_archived', models.BooleanField(default=False, verbose_name='보관 처리')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('target_students', models.ManyToManyField(blank=True, related_name='course_notebooks', to='accounts.student', verbose_name='대상 학생')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='course_notebooks', to=settings.AUTH_USER_MODEL, verbose_name='교사')),
            ],
            options={'verbose_name': '교과 수업 노트', 'verbose_name_plural': '교과 수업 노트 목록', 'ordering': ['-academic_year', 'semester', 'subject', 'title']},
        ),
        migrations.AddIndex(
            model_name='coursenotebook',
            index=models.Index(fields=['teacher', 'is_archived'], name='course_note_teacher_idx'),
        ),
        migrations.RunPython(rename_scratchpad, restore_scratchpad_name),
    ]
