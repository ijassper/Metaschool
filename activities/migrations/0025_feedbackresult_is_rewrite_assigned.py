from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0024_answer_submission_revisions'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedbackresult',
            name='is_rewrite_assigned',
            field=models.BooleanField(default=False, verbose_name='고쳐쓰기 과제 배부 여부'),
        ),
    ]
