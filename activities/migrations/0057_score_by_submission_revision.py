from django.db import migrations, models
import django.db.models.deletion


def attach_legacy_scores_to_latest_revision(apps, schema_editor):
    ActivityStudentScore = apps.get_model('activities', 'ActivityStudentScore')
    Answer = apps.get_model('activities', 'Answer')
    AnswerSubmissionRevision = apps.get_model('activities', 'AnswerSubmissionRevision')

    for score in ActivityStudentScore.objects.filter(answer_revision__isnull=True).iterator():
        answer = (
            Answer.objects.filter(
                student_id=score.student_id,
                question__activity_id=score.activity_id,
                submitted_at__isnull=False,
            )
            .order_by('-submitted_at', '-id')
            .first()
        )
        if not answer:
            continue
        revision = (
            AnswerSubmissionRevision.objects.filter(answer_id=answer.id)
            .order_by('-version', '-id')
            .first()
        )
        if revision:
            score.answer_revision_id = revision.id
            score.save(update_fields=['answer_revision'])


class Migration(migrations.Migration):
    dependencies = [('activities', '0056_answer_rewrite_draft')]

    operations = [
        migrations.RemoveConstraint(
            model_name='activitystudentscore',
            name='unique_activity_student_score',
        ),
        migrations.AddField(
            model_name='activitystudentscore',
            name='answer_revision',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='quick_scores',
                to='activities.answersubmissionrevision',
                verbose_name='제출 답안 버전',
            ),
        ),
        migrations.RunPython(attach_legacy_scores_to_latest_revision, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='activitystudentscore',
            constraint=models.UniqueConstraint(
                fields=('answer_revision',),
                name='unique_answer_revision_quick_score',
            ),
        ),
    ]
