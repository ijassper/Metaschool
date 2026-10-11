from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0035_course_notebook_learning_tools'),
    ]

    operations = [
        migrations.AlterField(
            model_name='coursenotebook',
            name='semester',
            field=models.CharField(
                choices=[('1', '1학기'), ('2', '2학기'), ('YEAR', '전학기')],
                default='YEAR',
                max_length=8,
            ),
        ),
    ]
