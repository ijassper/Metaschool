from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0022_activity_start_time'),
    ]

    operations = [
        migrations.AlterField(
            model_name='answerdraftrevision',
            name='char_count',
            field=models.PositiveIntegerField(default=0, verbose_name='공백 포함 글자 수'),
        ),
    ]
