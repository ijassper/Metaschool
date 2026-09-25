import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .proctor_storage import get_proctor_storage_report, proctor_storage_status


class ProctorStorageTests(SimpleTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'existing.jpg').write_bytes(b'x' * 800)
        settings = override_settings(
            PROCTOR_STORAGE_ROOT=str(self.root),
            PROCTOR_STORAGE_QUOTA_BYTES=1000,
            PROCTOR_STORAGE_STOP_RATIO=0.9,
            PROCTOR_STORAGE_BASELINE_BYTES=0,
            PROCTOR_STORAGE_RESERVE_BYTES=0,
        )
        settings.enable()
        self.addCleanup(settings.disable)

    def test_reservation_blocks_at_threshold_across_calls(self):
        with proctor_storage_status(99) as status:
            self.assertTrue(status['allowed'])
        with proctor_storage_status(1) as status:
            self.assertFalse(status['allowed'])
            self.assertEqual(status['used_bytes'], 899)

    def test_measurement_failure_denies_snapshots(self):
        with patch('activities.proctor_storage._measure_bytes', side_effect=OSError):
            with proctor_storage_status(1) as status:
                self.assertFalse(status['allowed'])
                self.assertIsNone(status['used_percent'])

    def test_save_failure_propagates_and_releases_lock(self):
        with self.assertRaisesRegex(OSError, 'save failed'):
            with proctor_storage_status(1):
                raise OSError('save failed')
        with proctor_storage_status() as status:
            self.assertTrue(status['allowed'])

    def test_baseline_and_headroom_are_included(self):
        with override_settings(PROCTOR_STORAGE_BASELINE_BYTES=50,
                               PROCTOR_STORAGE_RESERVE_BYTES=40):
            with proctor_storage_status(10) as status:
                self.assertFalse(status['allowed'])

    def test_recount_detects_other_file_growth(self):
        with proctor_storage_status() as status:
            self.assertTrue(status['allowed'])
        (self.root / 'other.bin').write_bytes(b'x' * 100)
        with patch('activities.proctor_storage.time.time', return_value=99999999999):
            with proctor_storage_status() as status:
                self.assertFalse(status['allowed'])

    def test_admin_report_includes_snapshot_usage_and_warning_level(self):
        snapshot_dir = self.root / 'media' / 'proctor_snapshots'
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / 'one.jpg').write_bytes(b'x' * 75)
        with override_settings(MEDIA_ROOT=str(self.root / 'media')):
            report = get_proctor_storage_report()
        self.assertEqual(report['snapshot_bytes'], 75)
        self.assertEqual(report['snapshot_files'], 1)
        self.assertEqual(report['level'], 'warning')
