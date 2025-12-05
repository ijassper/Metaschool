from django.core.management.base import BaseCommand
from accounts.models import PromptCategory, PromptTemplate

class Command(BaseCommand):
    help = '프롬프트 카테고리 구조를 진단합니다.'

    def handle(self, *args, **kwargs):
        self.stdout.write("\n" + "="*40)
        self.stdout.write("🕵️‍♂️ [1단계] 저장된 데이터 전수 조사")
        self.stdout.write("="*40)

        cats = PromptCategory.objects.all()
        if not cats.exists():
            self.stdout.write(self.style.ERROR("❌ 카테고리가 하나도 없습니다!"))
        else:
            for c in cats:
                p_name = c.parent.name if c.parent else "🔴 [대분류/ROOT]"
                self.stdout.write(f"ID: {c.id} | 이름: {c.name} | 상위: {p_name}")

        self.stdout.write("\n" + "="*40)
        self.stdout.write("🌳 [2단계] 메뉴 트리 시뮬레이션")
        self.stdout.write("="*40)

        # 대분류 찾기
        roots = PromptCategory.objects.filter(parent__isnull=True)
        
        if not roots.exists():
            self.stdout.write(self.style.ERROR("❌ 대분류(상위가 없는 카테고리)가 없습니다!"))
            self.stdout.write("👉 해결책: 관리자 페이지에서 '동아리 활동'의 상위 카테고리를 '------'로 수정하세요.")
            return

        self.stdout.write(f"✅ 발견된 대분류: {roots.count()}개")

        for root in roots:
            self.stdout.write(f"\n📂 대분류: {root.name} (ID: {root.id})")
            
            subs = PromptCategory.objects.filter(parent=root)
            if not subs.exists():
                self.stdout.write(self.style.WARNING(f"   ㄴ ⚠️ 하위(소)분류가 없습니다!"))
            
            for sub in subs:
                self.stdout.write(f"   ㄴ 📁 소분류: {sub.name} (ID: {sub.id})")
                
                temps = PromptTemplate.objects.filter(category=sub)
                if not temps.exists():
                    self.stdout.write(self.style.WARNING(f"      ㄴ ⚠️ 연결된 템플릿이 없습니다!"))
                
                for t in temps:
                    self.stdout.write(self.style.SUCCESS(f"      ㄴ 📄 템플릿: {t.title}"))