from django.db import migrations, models


def replace_legacy_gray(apps, schema_editor):
    CourseNotebook = apps.get_model('activities', 'CourseNotebook')
    CourseNotebook.objects.filter(cover_color='GRAY').update(cover_color='TEAL')


def restore_legacy_gray(apps, schema_editor):
    CourseNotebook = apps.get_model('activities', 'CourseNotebook')
    CourseNotebook.objects.filter(cover_color='TEAL').update(cover_color='GRAY')


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0036_alter_course_notebook_semester'),
    ]

    operations = [
        migrations.RunPython(replace_legacy_gray, restore_legacy_gray),
        migrations.AlterField(
            model_name='coursenotebook',
            name='cover_color',
            field=models.CharField(
                choices=[
                    ('PURPLE', '보라'), ('BLUE', '파랑'), ('GREEN', '초록'),
                    ('YELLOW', '노랑'), ('ORANGE', '주황'), ('RED', '빨강'),
                    ('PINK', '분홍'), ('TEAL', '청록'),
                ],
                default='PURPLE',
                max_length=12,
                verbose_name='표지 색상',
            ),
        ),
    ]
