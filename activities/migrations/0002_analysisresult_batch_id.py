# Generated manually for batch_id field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='analysisresult',
            name='batch_id',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='분석 세션 ID'),
        ),
    ]
