from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('activities', '0011_rename_class_life_subcategory')]

    operations = [
        migrations.AlterField(
            model_name='activity', name='category',
            field=models.CharField(choices=[('ESSAY', '교과 논술형 평가'), ('SUBJECT_ACTIVITY', '교과 수업활동'), ('SCHOOL_EVENT', '교내 행사활동'), ('CREATIVE', '자율활동'), ('CLUB', '동아리활동'), ('CAREER', '진로활동'), ('SCHOOL_LIFE', '기타 학교생활'), ('WRITING', '기초 쓰기 활동')], default='ESSAY', max_length=20, verbose_name='활동 유형'),
        ),
        migrations.AddField(model_name='activity', name='note_template', field=models.CharField(blank=True, choices=[('BLANK', '무지'), ('LINED_LARGE', '줄노트(대)'), ('LINED_MEDIUM', '줄노트(중)'), ('LINED_SMALL', '줄노트(소)'), ('MANUSCRIPT', '원고지')], default='', max_length=20, verbose_name='노트 양식')),
        migrations.AddField(model_name='activity', name='note_background', field=models.CharField(blank=True, choices=[('CREAM', '크림'), ('PINK', '핑크'), ('LAVENDER', '라벤더'), ('BLUE', '블루'), ('MINT', '민트')], default='', max_length=20, verbose_name='노트 배경 색상')),
    ]
