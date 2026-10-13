from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0038_replace_teal_cover_with_lime'),
    ]

    operations = [
        migrations.AddField(
            model_name='coursenotebookpage',
            name='processed_image',
            field=models.FileField(blank=True, upload_to='course_notebooks/processed/%Y/%m/%d/', verbose_name='보정된 노트 이미지'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_status',
            field=models.CharField(choices=[('UPLOADED', '변환 대기'), ('PROCESSING', '텍스트 변환 중'), ('COMPLETED', '변환 완료'), ('NEEDS_REVIEW', '확인 필요'), ('REVIEWED', '학생 확인 완료'), ('FAILED', '변환 실패')], default='UPLOADED', max_length=20, verbose_name='텍스트 변환 상태'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_raw_text',
            field=models.TextField(blank=True, verbose_name='OCR 원문'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_corrected_text',
            field=models.TextField(blank=True, verbose_name='확인된 텍스트'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_layout',
            field=models.JSONField(blank=True, default=dict, verbose_name='문서 구조와 좌표'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_provider',
            field=models.CharField(blank=True, max_length=40, verbose_name='OCR 제공자'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_model_version',
            field=models.CharField(blank=True, max_length=80, verbose_name='OCR 모델 버전'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_confidence',
            field=models.FloatField(blank=True, null=True, verbose_name='OCR 신뢰도'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_error',
            field=models.CharField(blank=True, max_length=500, verbose_name='OCR 오류'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='ocr_processed_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='OCR 처리 시각'),
        ),
        migrations.AddField(
            model_name='coursenotebookpage',
            name='processing_version',
            field=models.PositiveSmallIntegerField(default=1, verbose_name='처리 버전'),
        ),
    ]
