from django.db import migrations, models


def backfill_notebook_pages(apps, schema_editor):
    Answer = apps.get_model('activities', 'Answer')
    answers = (
        Answer.objects.filter(question__activity__sub_category='수업 노트/연습장')
        .exclude(ans_q1__isnull=True)
        .exclude(ans_q1='')
    )
    for answer in answers.iterator():
        if not answer.notebook_pages:
            answer.notebook_pages = [answer.ans_q1]
            answer.save(update_fields=['notebook_pages'])


class Migration(migrations.Migration):
    dependencies = [('activities', '0014_feedbackresult_feedback_title')]

    operations = [
        migrations.AddField(
            model_name='answer',
            name='notebook_pages',
            field=models.JSONField(blank=True, default=list, verbose_name='노트 페이지'),
        ),
        migrations.RunPython(backfill_notebook_pages, migrations.RunPython.noop),
    ]
