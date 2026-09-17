"""Shared, conservative quota guard for local proctor image uploads.

The host's contractual quota is not shutil.disk_usage().total. Configure the
account storage root and quota explicitly; baseline covers files outside root.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from contextlib import ExitStack, contextmanager

from django.conf import settings

_thread_lock = threading.Lock()


def _measure_bytes(root):
    total = 0

    def raise_error(error):
        raise error

    for directory, _, files in os.walk(root, onerror=raise_error, followlinks=False):
        for filename in files:
            path = Path(directory) / filename
            if not path.is_symlink():
                total += path.stat().st_size
    if not root.is_dir():
        raise OSError('Storage root is unavailable')
    return total


@contextmanager
def _shared_lock(path):
    with _thread_lock, open(path, 'a+b') as handle:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            if not handle.read(1):
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def proctor_storage_status(incoming_bytes=0):
    """Check and reserve bytes across workers; failures deny only snapshots.

    Reservations are intentionally not refunded on upload errors. Recounting
    every 60 seconds reconciles these estimates. Keep the lock through the
    caller's save to avoid recounting in-flight reservations.
    """
    return _storage_guard(incoming_bytes)


@contextmanager
def _storage_guard(incoming_bytes):
    root = Path(settings.PROCTOR_STORAGE_ROOT).resolve()
    quota = settings.PROCTOR_STORAGE_QUOTA_BYTES
    threshold = int(quota * settings.PROCTOR_STORAGE_STOP_RATIO)
    key = hashlib.sha256(str(root).encode()).hexdigest()[:24]
    state_path = Path(tempfile.gettempdir()) / f'ingrid-proctor-{key}.json'
    lock_path = state_path.with_suffix('.lock')
    with ExitStack() as stack:
        try:
            stack.enter_context(_shared_lock(lock_path))
            if quota <= 0 or incoming_bytes < 0:
                raise ValueError('Invalid storage quota')
            try:
                state = json.loads(state_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                state = {}
            now = time.time()
            if now - state.get('measured_at', 0) >= 60 or state.get('root') != str(root):
                state = {
                    'root': str(root),
                    'measured_at': now,
                    'used': _measure_bytes(root),
                }
            used = state['used'] + settings.PROCTOR_STORAGE_BASELINE_BYTES
            projected = used + incoming_bytes
            allowed = projected < threshold - settings.PROCTOR_STORAGE_RESERVE_BYTES
            status = {
                'allowed': allowed,
                'used_bytes': used,
                'quota_bytes': quota,
                'used_percent': round(used / quota * 100, 1),
                'stop_percent': settings.PROCTOR_STORAGE_STOP_RATIO * 100,
                'message': '' if allowed else '저장 공간 보호를 위해 화면 저장이 중단되었습니다. 답안 작성과 저장은 계속할 수 있습니다.',
            }
            if allowed and incoming_bytes:
                state['used'] += incoming_bytes
            state_path.write_text(json.dumps(state), encoding='utf-8')
            # Saving while locked prevents another worker from recounting
            # before the reserved image reaches disk.
        except (OSError, ValueError, KeyError, TypeError):
            status = {
                'allowed': False,
                'used_percent': None,
                'stop_percent': settings.PROCTOR_STORAGE_STOP_RATIO * 100,
                'message': '저장 공간을 확인할 수 없어 화면 저장을 중단했습니다. 답안 작성과 저장은 계속할 수 있습니다.',
            }
        yield status
