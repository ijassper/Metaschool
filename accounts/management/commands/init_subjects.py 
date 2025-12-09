from django.core.management.base import BaseCommand
from accounts.models import Subject, CustomUser

class Command(BaseCommand):
    help = '기본 교과목 생성 및 기존 사용자 데이터 마이그레이션'

    def handle(self, *args, **kwargs):
        # 1. 기본 교과목 리스트
        subjects = [
            "국어", "수학", "영어", "일반사회", "역사", "지리", "윤리",
            "물리", "화학", "생물", "지구과학", "체육", "음악", "미술",
            "한문", "일본어", "독일어", "프랑스어", "중국어",
            "기술", "가정", "정보", "보건", "사서", "영양",
            "특수", "전문상담", "기계", "전자", "상업", "기타"
        ]

        # 2. 교과목 DB 생성
        self.stdout.write("1. 교과목 데이터 생성 중...")
        for name in subjects:
            Subject.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS(f"✅ 교과목 {len(subjects)}개 준비 완료!"))

        # 3. 기존 선생님 데이터 이사 (Text -> ForeignKey)
        self.stdout.write("2. 기존 선생님 데이터 연결 중...")
        users = CustomUser.objects.all()
        count = 0
        
        for user in users:
            if user.subject: # 기존에 입력한 과목이 있다면
                # 공백 제거 후 찾기 (예: " 국어 " -> "국어")
                clean_name = user.subject.strip()
                
                # DB에서 해당 과목 찾기
                try:
                    sub_obj = Subject.objects.get(name=clean_name)
                    user.new_subject = sub_obj # 새 필드에 연결!
                    user.save()
                    count += 1
                except Subject.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"⚠️ 매칭 실패: {user.name} 선생님의 '{clean_name}' 과목이 리스트에 없습니다."))
                    # (필요시 '기타'로 연결하거나 수동 수정)
        
        self.stdout.write(self.style.SUCCESS(f"✅ 선생님 {count}명의 과목 정보를 안전하게 옮겼습니다!"))