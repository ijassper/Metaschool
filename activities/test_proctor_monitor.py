from datetime import timedelta

from django.template.loader import get_template
from django.test import SimpleTestCase
from django.utils import timezone

from .models import ProctorSession
from .views.exam_views import get_proctor_diagnostics
from .views.result_views import get_proctor_connection_state


class ProctorConnectionStateTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()

    def state(self, status=ProctorSession.Status.RECORDING, seconds_ago=0):
        return get_proctor_connection_state(
            status,
            self.now - timedelta(seconds=seconds_ago),
            self.now,
        )

    def test_recent_snapshot_is_live(self):
        self.assertEqual(self.state(seconds_ago=10), 'LIVE')

    def test_snapshot_between_thresholds_is_delayed(self):
        self.assertEqual(self.state(seconds_ago=11), 'DELAYED')
        self.assertEqual(self.state(seconds_ago=30), 'DELAYED')

    def test_old_snapshot_is_stopped(self):
        self.assertEqual(self.state(seconds_ago=31), 'STOPPED')

    def test_explicit_event_states_take_priority(self):
        self.assertEqual(self.state(ProctorSession.Status.AWAY), 'AWAY')
        self.assertEqual(self.state(ProctorSession.Status.ERROR), 'ERROR')
        self.assertEqual(self.state(ProctorSession.Status.ENDED), 'ENDED')
        self.assertEqual(self.state(ProctorSession.Status.DISCONNECTED), 'STOPPED')

    def test_student_without_snapshot_has_no_record(self):
        self.assertEqual(
            get_proctor_connection_state(ProctorSession.Status.RECORDING, None, self.now),
            'NONE',
        )

    def test_monitor_template_exposes_summary_and_last_receipt(self):
        source = get_template('activities/proctor_monitor.html').template.source
        self.assertIn('summaryLive', source)
        self.assertIn('마지막 수신', source)
        self.assertIn('connection_state', source)

    def test_device_diagnostics_are_allowlisted_and_bounded(self):
        diagnostics = get_proctor_diagnostics({
            'app_version': ' 0.2.0 ',
            'android_version': '14 (API 34)',
            'device_model': 'S' * 120,
            'capture_scope': 'FULL_DISPLAY',
            'android_id': 'must-not-be-stored',
        })
        self.assertEqual(diagnostics['app_version'], '0.2.0')
        self.assertEqual(len(diagnostics['device_model']), 100)
        self.assertNotIn('android_id', diagnostics)
