from datetime import timedelta

from django.template.loader import get_template
from django.test import SimpleTestCase
from django.utils import timezone

from .models import ProctorSession
from .views.exam_views import get_proctor_diagnostics
from .views.result_views import get_proctor_connection_state
from .views.result_views import get_proctor_activity_for_user
from unittest.mock import MagicMock, patch
from types import SimpleNamespace


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

    def test_admin_monitor_access_does_not_apply_teacher_filter(self):
        queryset = MagicMock()
        queryset.filter.return_value = queryset
        with patch('activities.views.result_views.Activity.objects.all', return_value=queryset), \
                patch('activities.views.result_views.get_object_or_404', return_value='activity') as get:
            result = get_proctor_activity_for_user(
                SimpleNamespace(role='ADMIN', is_superuser=False), 17
            )
        self.assertEqual(result, 'activity')
        queryset.filter.assert_not_called()
        get.assert_called_once_with(queryset, id=17)

    def test_teacher_monitor_access_is_limited_to_owned_activity(self):
        queryset = MagicMock()
        owned = MagicMock()
        queryset.filter.return_value = owned
        teacher = SimpleNamespace(role='TEACHER', is_superuser=False)
        with patch('activities.views.result_views.Activity.objects.all', return_value=queryset), \
                patch('activities.views.result_views.get_object_or_404', return_value='activity') as get:
            get_proctor_activity_for_user(teacher, 17)
        queryset.filter.assert_called_once_with(teacher=teacher)
        get.assert_called_once_with(owned, id=17)
