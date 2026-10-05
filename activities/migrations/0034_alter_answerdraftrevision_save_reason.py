from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0033_coursenotebookpage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='answerdraftrevision',
            name='save_reason',
            field=models.CharField(
                choices=[
                    ('PERIODIC', '정기 자동저장'),
                    ('DESTRUCTIVE_EDIT', '대량 삭제 직전'),
                    ('MANUAL', '수동 임시저장'),
                    ('PAGE_EXIT', '페이지 이동 전'),
                    ('AUTO_RECOVERY', '비정상 종료 자동복구'),
                    ('CONFLICT_BACKUP', '저장 충돌 후보 보관'),
                ],
                default='PERIODIC',
                max_length=20,
                verbose_name='저장 사유',
            ),
        ),
    ]
