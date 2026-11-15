"""Point byte-identical archive copies at their surviving notebook image."""

import hashlib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from activities.course_notebook_processing import PROCESSING_VERSION
from activities.models import CourseNotebookPage


def _matching_digest(first, second):
    """Return the image digest only when both stored files match byte for byte."""
    if first.size != second.size:
        return None
    digest = hashlib.sha256()
    with first.open('rb') as source, second.open('rb') as archive:
        while chunk := source.read(1024 * 1024):
            if chunk != archive.read(len(chunk)):
                return None
            digest.update(chunk)
        if archive.read(1):
            return None
    return digest.hexdigest()


class Command(BaseCommand):
    help = 'Find identical original/archive notebook images; use --apply to remove redundant copies.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Update references and delete verified identical copies')
        parser.add_argument('--limit', type=int, default=0, help='Stop after this many matching pages (0: all)')

    def handle(self, *args, **options):
        limit = options['limit']
        if limit < 0:
            raise CommandError('--limit must be zero or greater')
        scanned = matched = freed_bytes = skipped = 0
        candidates = CourseNotebookPage.objects.exclude(processed_image='').order_by('pk')
        for candidate in candidates.iterator(chunk_size=100):
            if limit and matched >= limit:
                break
            scanned += 1
            with transaction.atomic():
                page = (CourseNotebookPage.objects.select_for_update().get(pk=candidate.pk)
                        if options['apply'] else candidate)
                original = page.image
                archive = page.processed_image
                if (not original or not archive or original.name == archive.name
                        or page.processing_version != PROCESSING_VERSION
                        or original.storage is not archive.storage):
                    continue
                old_name = archive.name
                if CourseNotebookPage.objects.exclude(pk=page.pk).filter(
                    Q(image=old_name) | Q(processed_image=old_name)
                ).exists():
                    skipped += 1
                    continue
                try:
                    digest = _matching_digest(original, archive)
                    size = archive.size if digest else 0
                except OSError:
                    skipped += 1
                    continue
                if not digest:
                    continue
                matched += 1
                freed_bytes += size
                if options['apply']:
                    page.processed_image = original.name
                    page.source_hash = digest
                    page.save(update_fields=['processed_image', 'source_hash'])
                    transaction.on_commit(
                        lambda storage=archive.storage, name=old_name: storage.delete(name)
                    )
        action = '정리 완료' if options['apply'] else '정리 가능 (변경 없음)'
        self.stdout.write(self.style.SUCCESS(
            f'{action}: 검사 {scanned}장, 동일 사본 {matched}장, '
            f'예상 절감 {freed_bytes / 1024 / 1024:.1f} MiB, 확인 불가 {skipped}장'
        ))
