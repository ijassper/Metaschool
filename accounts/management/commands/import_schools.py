import pandas as pd
from django.core.management.base import BaseCommand
from accounts.models import School

class Command(BaseCommand):
    help = '엑셀 파일에서 학교 정보를 읽어와 DB에 저장합니다.'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='엑셀 파일 경로')

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']
        try:
            df = pd.read_excel(file_path)
            count = 0
            for index, row in df.iterrows():
                # 엑셀 헤더 이름 확인 필수: '교육청', '학교명', '나이스 학교코드'
                school, created = School.objects.get_or_create(
                    code=row['나이스 학교코드'],
                    defaults={
                        'office': row['교육청'],
                        'name': row['학교명'],
                        'level': School.Level.HIGH # 일단 고등학교로 고정
                    }
                )
                if created: count += 1
            self.stdout.write(self.style.SUCCESS(f'{count}개 학교 등록 완료!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'오류: {str(e)}'))