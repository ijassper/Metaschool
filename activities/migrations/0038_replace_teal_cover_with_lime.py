from django.db import migrations, models


def replace_teal_with_lime(apps, schema_editor):
    CourseNotebook = apps.get_model('activities', 'CourseNotebook')
    CourseNotebook.objects.filter(cover_color__in=['TEAL', 'GRAY']).update(cover_color='LIME')


def restore_teal(apps, schema_editor):
    CourseNotebook = apps.get_model('activities', 'CourseNotebook')
    CourseNotebook.objects.filter(cover_color='LIME').update(cover_color='TEAL')


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0037_course_notebook_eight_cover_colors'),
    ]

    operations = [
        migrations.RunPython(replace_teal_with_lime, restore_teal),
        migrations.AlterField(
            model_name='coursenotebook',
            name='cover_color',
            field=models.CharField(
                choices=[
                    ('PURPLE', '보라'), ('BLUE', '파랑'), ('GREEN', '초록'),
                    ('YELLOW', '노랑'), ('ORANGE', '주황'), ('RED', '빨강'),
                    ('PINK', '분홍'), ('LIME', '라임'),
                ],
                default='PURPLE',
                max_length=12,
                verbose_name='표지 색상',
            ),
        ),
    ]
