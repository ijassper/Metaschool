from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('activities', '0012_activity_notebook_settings')]

    operations = [
        migrations.AlterField(
            model_name='activity',
            name='note_background',
            field=models.CharField(
                blank=True,
                choices=[('WHITE', '무지(흰 배경)'), ('CREAM', '크림'), ('PINK', '핑크'), ('LAVENDER', '라벤더'), ('BLUE', '블루'), ('MINT', '민트')],
                default='',
                max_length=20,
                verbose_name='노트 배경 색상',
            ),
        ),
    ]
