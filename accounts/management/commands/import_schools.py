import pandas as pd
from django.core.management.base import BaseCommand
from accounts.models import School

class Command(BaseCommand):
    help = '전국 학교 정보(CSV)를 읽어와 DB에 저장합니다.'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='CSV 파일 경로')

    def handle(self, *args, **kwargs):
        file_path = kwargs['file_path']
        
        try:
            self.stdout.write(f"파일 읽는 중... {file_path}")
            
            # ★ CSV 파일 읽기 (한글 깨짐 방지를 위해 encoding='cp949' 사용)
            # 만약 에러 나면 'utf-8'이나 'euc-kr'로 변경 시도
            df = pd.read_csv(file_path, encoding='cp949')

            count = 0
            updated_count = 0

            for index, row in df.iterrows():
                # 1. CSV 컬럼 데이터 가져오기 (스크린샷 기준)
                # ★ 파일의 머리글(1행)과 똑같아야 합니다. 다르면 에러 납니다!
                office = row['시도교육청명']
                code = str(row['행정표준코드']) # 숫자로 인식될 수 있으니 문자로 변환
                name = row['학교명']

                # 2. 학교급(초/중/고) 자동 판단 로직
                if '초등학교' in name:
                    level = School.Level.ELEMENTARY
                elif '중학교' in name:
                    level = School.Level.MIDDLE
                elif '고등학교' in name:
                    level = School.Level.HIGH
                else:
                    level = School.Level.ETC

                # 3. DB에 저장 (update_or_create: 있으면 수정, 없으면 생성)
                # 나이스 코드(code)가 같은 게 있으면 정보를 덮어씁니다.
                obj, created = School.objects.update_or_create(
                    code=code,
                    defaults={
                        'office': office,
                        'name': name,
                        'level': level
                    }
                )

                if created:
                    count += 1
                else:
                    updated_count += 1
                
                # 진행 상황 표시 (너무 많으니 500개마다 찍기)
                if (index + 1) % 500 == 0:
                    self.stdout.write(f"... {index + 1}개 처리 중")

            self.stdout.write(self.style.SUCCESS(f'완료! [신규 등록: {count}개 / 정보 갱신: {updated_count}개]'))

        except KeyError as e:
            self.stdout.write(self.style.ERROR(f'열 이름(Header)을 찾을 수 없습니다: {str(e)}'))
            self.stdout.write("CSV 파일의 첫 번째 줄(제목)이 코드와 일치하는지 확인해주세요.")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'오류 발생: {str(e)}'))