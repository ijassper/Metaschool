from django.core.management.base import BaseCommand
from accounts.models import Student, CustomUser

class Command(BaseCommand):
    help = '학생 명렬표의 이메일을 실제 계정과 매칭합니다 (동명이인 제외)'

    def handle(self, *args, **kwargs):
        # 1. 선생님 찾기
        teacher_email = 'poodoldaddy@daum.net'
        try:
            teacher = CustomUser.objects.get(email=teacher_email)
        except CustomUser.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ 선생님 계정({teacher_email})을 찾을 수 없습니다."))
            return

        school = teacher.school
        self.stdout.write(f"🛡️ [{teacher.name}] 선생님의 학생 데이터 안전 복구 시작...")

        # 2. 학생 명부 가져오기
        students = Student.objects.filter(teacher=teacher)
        success_count = 0
        duplicate_count = 0
        fail_count = 0
        
        # 3. 매칭 시작
        for s in students:
            # 이름과 학생 권한으로 검색
            candidates = CustomUser.objects.filter(name=s.name, role='STUDENT')
            
            if candidates.count() == 1:
                # [성공] 딱 1명만 검색됨 -> 100% 본인
                user = candidates.first()
                s.email = user.email
                s.save()
                
                # 학교 정보도 채워주기
                if not user.school:
                    user.school = school
                    user.save()
                    
                success_count += 1
                # self.stdout.write(f"✅ {s.name} 연결 완료")

            elif candidates.count() > 1:
                # [위험] 2명 이상 검색됨 -> 동명이인
                self.stdout.write(self.style.WARNING(f"🚨 [동명이인] {s.name} ({s.grade}-{s.class_no}): {candidates.count()}명이 검색되어 건너뜁니다."))
                duplicate_count += 1

            else:
                # [실패] 없음
                # self.stdout.write(f"⚠️ {s.name} 계정 없음")
                fail_count += 1

        self.stdout.write("\n" + "="*30)
        self.stdout.write(self.style.SUCCESS(f"✅ 성공: {success_count}명"))
        self.stdout.write(self.style.WARNING(f"🚨 동명이인(미처리): {duplicate_count}명"))
        self.stdout.write(self.style.ERROR(f"⚠️ 계정 없음: {fail_count}명"))
        self.stdout.write("="*30)
        self.stdout.write("※ 동명이인은 관리자 페이지(Students)에서 수동으로 이메일을 입력해주세요.")