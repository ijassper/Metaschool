"""Automatic retention cleanup for proctor screenshots.

Container hosting does not always provide cron.  A system-admin login can call
``schedule_cleanup_after_admin_login``; the actual file deletion then runs in a
daemon thread so that login is not delayed.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from datetime import timedelta
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

_thread_guard = threading.Lock()
_thread_running = False


def _work_dir() -> Path:
    configured = getattr(settings, "PROCTOR_CLEANUP_STATE_DIR", "")
    return Path(configured) if configured else Path(settings.MEDIA_ROOT) / ".proctor-cleanup"


def _completed_today(state_file: Path) -> bool:
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        return payload.get("completed_date") == timezone.localdate().isoformat()
    except (OSError, ValueError, TypeError):
        return False


def delete_snapshot_files(frames) -> int:
    """Delete image objects and their database rows in small batches."""
    deleted = 0
    for frame in frames.iterator(chunk_size=100):
        frame.image.delete(save=False)
        frame.delete()
        deleted += 1
    return deleted


def cleanup_expired_snapshots(days: Optional[int] = None) -> int:
    from activities.models import ProctorSnapshot

    retention_days = days or getattr(settings, "PROCTOR_RETENTION_DAYS", 30)
    cutoff = timezone.now() - timedelta(days=retention_days)
    frames = ProctorSnapshot.objects.filter(created_at__lt=cutoff).order_by("id")
    return delete_snapshot_files(frames)


def get_cleanup_status() -> dict:
    """Return display-safe status for the admin operations screen."""
    work_dir = _work_dir()
    state_file = work_dir / "state.json"
    payload = {}
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    return {
        "completed_date": payload.get("completed_date"),
        "completed_at": payload.get("completed_at"),
        "deleted": payload.get("deleted"),
        "running": (work_dir / "running.lock").exists() or _thread_running,
        "retention_days": getattr(settings, "PROCTOR_RETENTION_DAYS", 30),
        "enabled": getattr(settings, "PROCTOR_AUTO_CLEANUP_ENABLED", True),
    }


def _claim_daily_run(work_dir: Path, force: bool = False) -> Optional[Path]:
    work_dir.mkdir(parents=True, exist_ok=True)
    state_file = work_dir / "state.json"
    if not force and _completed_today(state_file):
        return None

    lock_dir = work_dir / "running.lock"
    try:
        lock_dir.mkdir()
    except FileExistsError:
        # A crashed worker must not block cleanup forever.
        try:
            age_seconds = timezone.now().timestamp() - lock_dir.stat().st_mtime
            if age_seconds <= 60 * 60:
                return None
            shutil.rmtree(lock_dir)
            lock_dir.mkdir()
        except (FileExistsError, FileNotFoundError, OSError):
            return None

    if not force and _completed_today(state_file):
        shutil.rmtree(lock_dir, ignore_errors=True)
        return None
    return lock_dir


def _run_daily_cleanup(force: bool = False) -> None:
    global _thread_running
    close_old_connections()
    work_dir = _work_dir()
    lock_dir = None
    try:
        lock_dir = _claim_daily_run(work_dir, force=force)
        if lock_dir is None:
            return

        deleted = cleanup_expired_snapshots()
        state_file = work_dir / "state.json"
        temporary = work_dir / f"state.{os.getpid()}.tmp"
        temporary.write_text(
            json.dumps(
                {
                    "completed_date": timezone.localdate().isoformat(),
                    "completed_at": timezone.now().isoformat(),
                    "deleted": deleted,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, state_file)
        logger.info("감독 기록 자동 정리 완료: %s장 삭제", deleted)
    except Exception:
        logger.exception("감독 기록 자동 정리에 실패했습니다. 다음 최고관리자 로그인 때 재시도합니다.")
    finally:
        if lock_dir is not None:
            shutil.rmtree(lock_dir, ignore_errors=True)
        close_old_connections()
        with _thread_guard:
            _thread_running = False


def schedule_cleanup_after_admin_login(force: bool = False) -> bool:
    """Schedule today's cleanup once. Returns True only when a thread starts."""
    global _thread_running
    if not force and not getattr(settings, "PROCTOR_AUTO_CLEANUP_ENABLED", True):
        return False

    state_file = _work_dir() / "state.json"
    if not force and _completed_today(state_file):
        return False

    with _thread_guard:
        if _thread_running:
            return False
        _thread_running = True

    thread = threading.Thread(
        target=_run_daily_cleanup,
        kwargs={"force": force},
        name="proctor-retention-cleanup",
        daemon=True,
    )
    thread.start()
    return True
