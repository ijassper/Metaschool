from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_customuser_approval_status_customuser_is_approved'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='current_session_key',
            field=models.CharField(blank=True, max_length=40, null=True),
        ),
    ]