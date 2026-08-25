from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('activities', '0015_answer_notebook_pages')]

    operations = [
        migrations.AddField(
            model_name='answer',
            name='score',
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(0, '0점'), (1, '1점'), (2, '2점'), (3, '3점'), (4, '4점'), (5, '5점')],
                null=True,
                verbose_name='퀵 점수',
            ),
        ),
    ]
