from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from activities.models import ProctorSnapshot
from activities.proctor_retention import delete_snapshot_files


class Command(BaseCommand):
    help = 'Delete proctor snapshot files and rows older than the configured retention period.'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=getattr(settings, 'PROCTOR_RETENTION_DAYS', 30))
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        days = options['days']
        if days < 1:
            raise CommandError('--days must be at least 1')
        cutoff = timezone.now() - timedelta(days=days)
        frames = ProctorSnapshot.objects.filter(created_at__lt=cutoff).order_by('id')
        count = frames.count()
        if options['dry_run']:
            self.stdout.write(f'{days}일 보관 기준 삭제 대상: {count}장 (실제 삭제 없음)')
            return
        deleted = delete_snapshot_files(frames)
        self.stdout.write(self.style.SUCCESS(f'{days}일보다 오래된 감독 기록 {deleted}장을 삭제했습니다.'))
