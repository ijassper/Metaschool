from django.db import migrations, models
import django.db.models.deletion


def backfill_submission_revisions(apps, schema_editor):
    Answer = apps.get_model('activities', 'Answer')
    AnswerSubmissionRevision = apps.get_model('activities', 'AnswerSubmissionRevision')
    FeedbackResult = apps.get_model('activities', 'FeedbackResult')
    FeedbackSession = apps.get_model('activities', 'FeedbackSession')

    for answer in Answer.objects.filter(submitted_at__isnull=False).iterator():
        notebook_pages = list(answer.notebook_pages or [])
        legacy_answers = [answer.ans_q1 or '', answer.ans_q2 or '', answer.ans_q3 or '']
        if not notebook_pages and not any(value.strip() for value in legacy_answers):
            legacy_answers[0] = answer.content or ''
        snapshot = {
            'ans_q1': '' if notebook_pages else legacy_answers[0],
            'ans_q2': '' if notebook_pages else legacy_answers[1],
            'ans_q3': '' if notebook_pages else legacy_answers[2],
            'notebook_pages': notebook_pages,
        }
        revision = AnswerSubmissionRevision.objects.create(
            answer_id=answer.id,
            version=1,
            content_snapshot=snapshot,
            submitted_at=answer.submitted_at,
        )
        FeedbackResult.objects.filter(answer_id=answer.id, answer_revision__isnull=True).update(
            answer_revision_id=revision.id,
        )
        FeedbackSession.objects.filter(answer_id=answer.id, answer_revision__isnull=True).update(
            answer_revision_id=revision.id,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0023_alter_answerdraftrevision_char_count'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnswerSubmissionRevision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.PositiveIntegerField(verbose_name='답안 버전')),
                ('content_snapshot', models.JSONField(default=dict, verbose_name='제출 답안 스냅샷')),
                ('submitted_at', models.DateTimeField(verbose_name='제출 일시')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='기록 일시')),
                ('answer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='submission_revisions', to='activities.answer', verbose_name='답안')),
            ],
            options={
                'verbose_name': '제출 답안 버전',
                'verbose_name_plural': '제출 답안 버전 목록',
                'ordering': ['version', 'id'],
                'indexes': [models.Index(fields=['answer', 'version'], name='answer_submission_ver_idx')],
                'constraints': [models.UniqueConstraint(fields=('answer', 'version'), name='unique_answer_submission_version')],
            },
        ),
        migrations.AddField(
            model_name='feedbackresult',
            name='answer_revision',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='feedback_results', to='activities.answersubmissionrevision', verbose_name='기준 답안 버전'),
        ),
        migrations.AddField(
            model_name='feedbacksession',
            name='answer_revision',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='feedback_sessions', to='activities.answersubmissionrevision', verbose_name='기준 답안 버전'),
        ),
        migrations.RunPython(backfill_submission_revisions, migrations.RunPython.noop),
    ]
