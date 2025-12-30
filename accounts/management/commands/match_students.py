from django.core.management.base import BaseCommand
from accounts.models import Student, CustomUser

class Command(BaseCommand):
    help = '학생 명렬표의 이메일을 정밀 매칭합니다 (학번 활용)'

    def handle(self, *args, **kwargs):
        teacher_email = 'poodoldaddy@daum.net'
        try:
            teacher = CustomUser.objects.get(email=teacher_email)
        except CustomUser.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ 선생님 계정을 찾을 수 없습니다."))
            return

        school = teacher.school
        self.stdout.write(f"🛡️ [{teacher.name}] 선생님의 학생 데이터 정밀 복구 시작...")

        students = Student.objects.filter(teacher=teacher)
        success_count = 0
        fail_count = 0
        
        for s in students:
            # 1. 이름으로 후보군 검색
            candidates = CustomUser.objects.filter(name=s.name, role='STUDENT')
            
            target_user = None
            
            # 2. 후보군 중에서 '학번'이 일치하는지 검사
            # (우리가 만든 아이디 규칙: 이메일 앞부분에 학번 숫자가 포함됨)
            # 예: 강지원 (1학년 1반 1번) -> 학번코드 '10101'
            student_code = f"{s.grade}{s.class_no:02d}{s.number:02d}"
            
            for cand in candidates:
                # 후보자의 이메일(아이디)에 학번코드(10101)가 포함되어 있는지 확인
                if student_code in cand.email:
                    target_user = cand
                    break
            
            if target_user:
                # [성공] 학번까지 일치하는 사람 찾음!
                s.email = target_user.email
                s.save()
                
                # 학교 정보 채워주기
                if not target_user.school:
                    target_user.school = school
                    target_user.save()
                    
                success_count += 1
                # self.stdout.write(f"✅ {s.name} ({student_code}) 연결 성공")
            else:
                self.stdout.write(self.style.ERROR(f"❌ {s.name} ({student_code}) 계정을 못 찾음 (후보 {candidates.count()}명 중 일치 없음)"))
                fail_count += 1

        self.stdout.write("\n" + "="*30)
        self.stdout.write(self.style.SUCCESS(f"✅ 최종 성공: {success_count}명"))
        self.stdout.write(self.style.ERROR(f"❌ 실패: {fail_count}명"))