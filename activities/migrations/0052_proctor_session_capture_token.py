from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('activities', '0051_attendance_report_numbers'),
    ]

    operations = [
        migrations.AddField(
            model_name='proctorsession',
            name='capture_token',
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
