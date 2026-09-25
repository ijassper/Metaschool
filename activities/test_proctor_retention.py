import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from activities import proctor_retention


class ProctorRetentionScheduleTests(SimpleTestCase):
    def tearDown(self):
        proctor_retention._thread_running = False

    def test_completed_today_prevents_duplicate_schedule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / 'state.json'
            state.write_text(
                json.dumps({'completed_date': timezone.localdate().isoformat()}),
                encoding='utf-8',
            )
            with override_settings(PROCTOR_CLEANUP_STATE_DIR=temp_dir):
                self.assertFalse(proctor_retention.schedule_cleanup_after_admin_login())

    @override_settings(PROCTOR_AUTO_CLEANUP_ENABLED=False)
    def test_cleanup_can_be_disabled(self):
        self.assertFalse(proctor_retention.schedule_cleanup_after_admin_login())

    def test_successful_run_records_completion_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(PROCTOR_CLEANUP_STATE_DIR=temp_dir), patch.object(
                proctor_retention, 'cleanup_expired_snapshots', return_value=12
            ):
                proctor_retention._run_daily_cleanup()

            payload = json.loads((Path(temp_dir) / 'state.json').read_text(encoding='utf-8'))
            self.assertEqual(payload['deleted'], 12)
            self.assertEqual(payload['completed_date'], timezone.localdate().isoformat())
            self.assertFalse((Path(temp_dir) / 'running.lock').exists())

    def test_status_exposes_last_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / 'state.json'
            state.write_text(
                json.dumps({
                    'completed_date': '2026-09-25',
                    'completed_at': '2026-09-25T09:00:00+09:00',
                    'deleted': 18,
                }),
                encoding='utf-8',
            )
            with override_settings(PROCTOR_CLEANUP_STATE_DIR=temp_dir, PROCTOR_RETENTION_DAYS=30):
                status = proctor_retention.get_cleanup_status()
            self.assertEqual(status['deleted'], 18)
            self.assertEqual(status['retention_days'], 30)

    def test_force_claim_ignores_completed_today(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / 'state.json'
            state.write_text(
                json.dumps({'completed_date': timezone.localdate().isoformat()}),
                encoding='utf-8',
            )
            lock = proctor_retention._claim_daily_run(Path(temp_dir), force=True)
            self.assertIsNotNone(lock)
            if lock:
                lock.rmdir()
