from django.db import migrations, models


def backfill_feedback_titles(apps, schema_editor):
    FeedbackResult = apps.get_model('activities', 'FeedbackResult')
    FeedbackSession = apps.get_model('activities', 'FeedbackSession')

    for result in FeedbackResult.objects.filter(feedback_title='').iterator():
        session = (
            FeedbackSession.objects.filter(
                answer_id=result.answer_id,
                status='FINAL',
                content=result.feedback_content,
            )
            .exclude(feedback_title='')
            .order_by('-updated_at', '-id')
            .first()
        )
        if session:
            result.feedback_title = session.feedback_title[:150]
            result.save(update_fields=['feedback_title'])


class Migration(migrations.Migration):
    dependencies = [('activities', '0013_alter_activity_note_background')]

    operations = [
        migrations.AddField(
            model_name='feedbackresult',
            name='feedback_title',
            field=models.TextField(blank=True, max_length=150, verbose_name='작업 제목'),
        ),
        migrations.RunPython(backfill_feedback_titles, migrations.RunPython.noop),
    ]
