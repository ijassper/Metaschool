from types import SimpleNamespace
from pathlib import Path
import re

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.template.loader import get_template
from django.template import Context, Template
from django.urls import reverse
from django.conf import settings
from django.utils import timezone

from .views.exam_views import (
    normalize_notebook_pages,
    pdf_viewer,
    snapshot_char_count,
    snapshot_fingerprint,
)
from .views.result_views import parse_quick_score
from .views.main_views import get_form_config
from .views.ai_views import (
    FEEDBACK_BASE_PROMPT,
    compose_ai_system_prompt,
    build_formality_output_contract,
    get_school_level_prompt,
    normalize_tone_attribute_value,
    TASK_OUTPUT_CONTRACTS,
    TASK_USER_INSTRUCTIONS,
)
from .attachment_context import (
    estimate_openai_cost_usd,
    extract_text_from_upload,
    normalize_openai_usage,
)
from .templatetags.answer_extras import non_whitespace_length
from .models import Activity, Question, Answer, FeedbackResult


class NotebookPageDataTests(SimpleTestCase):
    def test_parses_page_json_and_preserves_page_order(self):
        self.assertEqual(
            normalize_notebook_pages('["첫 번째 쪽", "두 번째 쪽"]'),
            ['첫 번째 쪽', '두 번째 쪽'],
        )

    def test_uses_legacy_answer_as_first_page(self):
        self.assertEqual(normalize_notebook_pages('', '기존 노트'), ['기존 노트'])

    def test_always_keeps_at_least_one_page(self):
        self.assertEqual(normalize_notebook_pages('[]'), [''])

    def test_removes_empty_pages_but_keeps_written_page_order(self):
        self.assertEqual(
            normalize_notebook_pages('["첫 쪽", "", "   ", "마지막 쪽"]'),
            ['첫 쪽', '마지막 쪽'],
        )

    def test_revision_character_count_does_not_double_count_notebook_pages(self):
        snapshot = {
            'ans_q1': '레거시 합본',
            'ans_q2': '',
            'ans_q3': '',
            'notebook_pages': ['첫 쪽', '두 번째 쪽'],
        }
        self.assertEqual(snapshot_char_count(snapshot), 6)

    def test_revision_fingerprint_is_stable_for_same_snapshot(self):
        first = {'ans_q1': '답안', 'ans_q2': '', 'ans_q3': '', 'notebook_pages': []}
        second = {'notebook_pages': [], 'ans_q3': '', 'ans_q2': '', 'ans_q1': '답안'}
        self.assertEqual(snapshot_fingerprint(first), snapshot_fingerprint(second))


class QuickScoreValidationTests(SimpleTestCase):
    def test_accepts_zero_through_five(self):
        self.assertEqual([parse_quick_score(value) for value in range(6)], list(range(6)))

    def test_rejects_out_of_range_and_non_numeric_values(self):
        for invalid_value in (-1, 6, '', None, True, '오점'):
            with self.subTest(value=invalid_value), self.assertRaises((TypeError, ValueError)):
                parse_quick_score(invalid_value)


class AnswerParticipationStatusTests(SimpleTestCase):
    def make_answer(self, **kwargs):
        activity = Activity(q1_title='문항 1', q2_title='문항 2', q3_title='문항 3')
        question = Question(activity=activity, content='평가 문항')
        defaults = {
            'question': question,
            'content': '',
            'activity_log': '',
            'absence_type': '',
        }
        defaults.update(kwargs)
        return Answer(**defaults)

    def test_score_only_empty_answer_remains_not_started(self):
        answer = self.make_answer(score=3)
        self.assertEqual(answer.participation_status(deadline_passed=False), '미응시')
        self.assertEqual(answer.participation_status(deadline_passed=True), '미응시')

    def test_started_unsubmitted_answer_changes_to_not_submitted_after_deadline(self):
        answer = self.make_answer(activity_log='[입장] 답안지 페이지 입장')
        self.assertEqual(answer.participation_status(deadline_passed=False), '응시 중')
        self.assertEqual(answer.participation_status(deadline_passed=True), '미제출')

    def test_submitted_empty_and_written_answers_are_distinguished(self):
        submitted_at = timezone.now()
        blank_answer = self.make_answer(submitted_at=submitted_at)
        written_answer = self.make_answer(submitted_at=submitted_at, ans_q1='작성한 답안')
        self.assertEqual(blank_answer.participation_status(), '백지 제출')
        self.assertEqual(written_answer.participation_status(), '제출 완료')


@override_settings(
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage'
)
class PdfViewerTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True)

    def test_pdf_viewer_accepts_same_origin_media_path(self):
        request = self.factory.get(
            reverse('pdf_viewer'),
            {'file': '/media/activity_files/reference.pdf'},
        )
        request.user = self.user

        response = pdf_viewer(request)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/media/activity_files/reference.pdf')

    def test_pdf_viewer_rejects_external_url(self):
        request = self.factory.get(
            reverse('pdf_viewer'),
            {'file': 'https://example.com/reference.pdf'},
        )
        request.user = self.user

        response = pdf_viewer(request)

        self.assertEqual(response.status_code, 400)
        self.assertContains(
            response,
            '올바른 PDF 파일 경로가 아닙니다.',
            status_code=400,
        )

    def test_pdf_viewer_rejects_path_traversal(self):
        request = self.factory.get(
            reverse('pdf_viewer'),
            {'file': '/media/../private/reference.pdf'},
        )
        request.user = self.user

        response = pdf_viewer(request)

        self.assertEqual(response.status_code, 400)

    def test_exam_and_pdf_viewer_templates_compile(self):
        base_source = get_template('base.html').template.source

        self.assertIsNotNone(get_template('activities/take_test.html'))
        self.assertIsNotNone(get_template('activities/pdf_viewer.html'))
        self.assertIn("{% static 'images/ingrid_logo.jpg' %}", base_source)
        self.assertIn('Mixed Content', base_source)
        self.assertIn("form.action.replace('http://', 'https://')", base_source)
        self.assertNotIn('src="http://', base_source)
        self.assertNotIn('href="http://', base_source)

    def test_pdf_controls_are_non_submitting_and_stop_event_propagation(self):
        template_source = get_template(
            'activities/pdf_viewer.html'
        ).template.source

        self.assertIn('class="modal-button"', template_source)
        self.assertIn('tabindex="-1"', template_source)
        self.assertIn('event.preventDefault()', template_source)
        self.assertIn('event.stopPropagation()', template_source)
        self.assertNotIn('location.reload', template_source)
        self.assertNotIn('window.location.href =', template_source)

    def test_exam_security_ignores_only_active_pdf_modal_focus(self):
        template_source = get_template(
            'activities/take_test.html'
        ).template.source

        self.assertIn('let is_modal_active = false', template_source)
        self.assertIn('isPdfModalInteractionActive()', template_source)
        self.assertIn("event.data.type === 'pdf-viewer-interaction'", template_source)

    def test_pdf_modal_supports_drag_resize_minimize_and_reset(self):
        template_source = get_template(
            'activities/take_test.html'
        ).template.source

        self.assertIn('class="modal-dialog resizable-modal"', template_source)
        self.assertIn('id="filePreviewDragHandle"', template_source)
        self.assertIn('id="filePreviewResizeHandle"', template_source)
        self.assertIn("addEventListener('pointerdown'", template_source)
        self.assertIn("setPointerCapture(event.pointerId)", template_source)
        self.assertIn("addEventListener('touchstart'", template_source)
        self.assertIn("addEventListener('touchmove'", template_source)
        self.assertIn("addEventListener('touchend'", template_source)
        self.assertIn('function constrainPreviewRect', template_source)
        self.assertIn('function togglePreviewMinimize', template_source)
        self.assertIn('function resetPreviewDialog', template_source)
        self.assertIn("width: min(40vw, 640px)", template_source)
        self.assertIn('min-width: 300px', template_source)
        self.assertIn('min-height: 200px', template_source)

    def test_exam_start_labels_and_fullscreen_navigation_are_standardized(self):
        template_root = Path(settings.BASE_DIR) / 'templates'
        combined_templates = '\n'.join(
            path.read_text(encoding='utf-8')
            for path in template_root.rglob('*.html')
        )
        take_test_source = get_template(
            'activities/take_test.html'
        ).template.source
        typing_views_source = (
            Path(settings.BASE_DIR) / 'activities' / 'views' / 'typing_views.py'
        ).read_text(encoding='utf-8')
        dashboard_source = get_template(
            'activities/student_dashboard.html'
        ).template.source

        self.assertNotIn('전체 화면으로 복귀하여 응시 계속하기', combined_templates)
        self.assertNotIn('응시 시작하기', combined_templates)
        self.assertIn('id="start-btn"', take_test_source)
        self.assertIn('타자연습 커버', take_test_source)
        self.assertIn('타자연습 과제명', take_test_source)
        self.assertIn('타자연습 유형', take_test_source)
        self.assertIn('연습 타자 위치', take_test_source)
        self.assertIn('타자연습 수준', take_test_source)
        self.assertIn('타자연습 시작하기', take_test_source)
        self.assertIn('타자연습 실전', take_test_source)
        self.assertNotIn('id="typingTargetDisplay"', take_test_source)
        self.assertIn('typingProgressBar', take_test_source)
        self.assertIn('typingProgressLabel', take_test_source)
        self.assertIn('typing-progress-wrap', take_test_source)
        self.assertIn('typing-progress-track', take_test_source)
        self.assertIn('typingSpeed', take_test_source)
        self.assertIn('typingErrorCount', take_test_source)
        self.assertIn('typing-topic-title', take_test_source)
        self.assertIn('typing-header-grid', take_test_source)
        self.assertIn('{{ activity.subject_name }}', take_test_source)
        self.assertIn('{% if activity.subject_name %}', take_test_source)
        self.assertIn('{{ activity.title }}', take_test_source)
        self.assertIn('typing-student-card', take_test_source)
        self.assertIn('typing-stats-line', take_test_source)
        self.assertIn('id="typingAccuracy"', take_test_source)
        self.assertNotIn('typingCurrentKey', take_test_source)
        self.assertIn('main-content-shell', take_test_source)
        self.assertIn('overflow-y: auto !important', take_test_source)
        self.assertIn('typingGuideCurrent', take_test_source)
        self.assertIn('id="typingKeyboard"', take_test_source)
        self.assertIn('typing-context-char is-current', take_test_source)
        self.assertIn('const offsets = [-3, -2, -1, 0, 1, 2, 3]', take_test_source)
        self.assertIn('acceptStrictTypingChars', take_test_source)
        self.assertIn('handleTypingBeforeInput', take_test_source)
        self.assertIn("input.addEventListener('beforeinput', handleTypingBeforeInput)", take_test_source)
        self.assertIn('KOREAN_KEY_CODE_MAP', take_test_source)
        self.assertIn('typingLastAcceptedValue', take_test_source)
        self.assertIn('event.code && KOREAN_KEY_CODE_MAP[event.code]', take_test_source)
        self.assertIn('typingSkipNextBeforeInput', take_test_source)
        self.assertIn('Date.now() + 250', take_test_source)
        self.assertIn('typingSkipNextBeforeInput >= Date.now()', take_test_source)
        self.assertIn('USE_KEYDOWN_TEXT_FALLBACK', take_test_source)
        self.assertIn("!('InputEvent' in window)", take_test_source)
        self.assertIn('restoreAcceptedTypingValue', take_test_source)
        self.assertIn('isNativeDuplicateValue', take_test_source)
        self.assertIn('if (typingIsManualInsert)', take_test_source)
        self.assertIn('}, 120)', take_test_source)
        self.assertIn('typingLastAcceptedInsert', take_test_source)
        self.assertIn('isDuplicateNativeTypingInsert', take_test_source)
        self.assertIn('is-rejected', take_test_source)
        self.assertIn("guide.querySelector('.typing-context-char.is-current')", take_test_source)
        self.assertIn('window.requestAnimationFrame(() => triggerTypingInputShake(input))', take_test_source)
        self.assertLess(
            take_test_source.index('for="typingInput"'),
            take_test_source.index('id="typingKeyboard"'),
        )
        self.assertNotIn('id="typingFingerGuide"', take_test_source)
        self.assertNotIn('typing-finger-dot" data-finger', take_test_source)
        self.assertIn('typing-result-modal-dialog', take_test_source)
        self.assertIn('typing-result-modal-content', take_test_source)
        self.assertIn('requestTypingFullscreenOnLoad', take_test_source)
        self.assertIn('!ENABLE_EXIT_DETECTION && !IS_TYPING_ACTIVITY', take_test_source)
        self.assertIn("logFullscreenState('start-click-success')", take_test_source)
        self.assertIn('TYPING_DATA_URL', take_test_source)
        self.assertIn('typing_data.json', take_test_source)
        self.assertIn('loadTypingKeyData', take_test_source)
        self.assertIn('updateTypingMainGuide', take_test_source)
        self.assertIn('LEFT_TYPING_KEYS', take_test_source)
        self.assertIn('shuffleTypingKeys', take_test_source)
        self.assertIn('Math.random()', take_test_source)
        self.assertIn('Array.from({ length: 4 }', take_test_source)
        self.assertIn('RIGHT_TYPING_KEY_SET', take_test_source)
        self.assertIn('LEFT_TYPING_KEY_SET', take_test_source)
        self.assertIn('DISABLED_TYPING_SYMBOL_SET', take_test_source)
        self.assertNotIn('RIGHT_TYPING_KEYBOARD_ROWS', take_test_source)
        self.assertIn('filterRightTypingText', take_test_source)
        self.assertIn('getTypingKeyboardLayout', take_test_source)
        self.assertIn('getTypingKeycapModeClasses', take_test_source)
        self.assertIn('is-practice-zone', take_test_source)
        self.assertIn('is-muted', take_test_source)
        self.assertIn('is-disabled-symbol', take_test_source)
        self.assertIn("if (TYPING_POSITION === 'RIGHT')", take_test_source)
        self.assertNotIn("const RIGHT_TYPING_KEYS = ['\\u315b','\\u3155','\\u3151','\\u3150','\\u3154','[',']'", take_test_source)
        self.assertNotIn('const keyLine = keys.join', take_test_source)
        self.assertIn('updateTypingStats', take_test_source)
        self.assertIn('typingTimer', take_test_source)
        self.assertIn('startTypingTimer', take_test_source)
        self.assertIn('submitTypingResult', take_test_source)
        self.assertIn('normalizeTypingLine', take_test_source)
        self.assertIn('getStrictTypingState', take_test_source)
        self.assertIn('correctPrefixLength', take_test_source)
        self.assertIn('typingCorrectionCount', take_test_source)
        self.assertIn('correction_count', take_test_source)
        self.assertIn("'typing-context-char is-current'", take_test_source)
        self.assertIn('ime-mode: disabled', take_test_source)
        self.assertIn('handleTypingKeydown', take_test_source)
        self.assertIn('compositionstart', take_test_source)
        self.assertIn('preventTypingComposition', take_test_source)
        self.assertIn('handleTypingCompositionEnd', take_test_source)
        self.assertIn("input.addEventListener('compositionend', handleTypingCompositionEnd)", take_test_source)
        self.assertIn("event.type.startsWith('composition')", take_test_source)
        self.assertIn('decomposeHangulTypingValue', take_test_source)
        self.assertIn('HANGUL_COMPAT_COMPOUND', take_test_source)
        self.assertIn('enforceStrictTypingInputValue', take_test_source)
        self.assertIn('rejectTypingInput', take_test_source)
        self.assertIn('triggerTypingInputShake', take_test_source)
        self.assertIn('typingRejectedErrorCount', take_test_source)
        self.assertIn('rejected_error_count', take_test_source)
        self.assertIn("input.value = strictState.inputChars.slice(0, strictState.correctPrefixLength).join('')", take_test_source)
        self.assertIn('maybeAdvanceTypingLine', take_test_source)
        self.assertIn('total_typing_time', take_test_source)
        self.assertIn('typing_speed', take_test_source)
        self.assertIn('error_count', take_test_source)
        self.assertIn('id="stop-btn"', take_test_source)
        self.assertIn('연습 중단', take_test_source)
        self.assertIn('stopTypingPractice', take_test_source)
        self.assertIn('중단 시 기록은 저장되지 않습니다', take_test_source)
        self.assertIn('typingResultModal', take_test_source)
        self.assertIn('showTypingResultModal', take_test_source)
        self.assertIn('saveTypingResultButton', take_test_source)
        self.assertIn('analyze_typing_result', take_test_source)
        self.assertIn('average_wpm', take_test_source)
        self.assertIn('strong_keys', take_test_source)
        self.assertIn('weak_keys', take_test_source)
        self.assertIn('RIGHT_TYPING_KEYS', typing_views_source)
        self.assertIn('filter_right_typing_text', typing_views_source)
        self.assertIn("activity.typing_position == 'RIGHT'", typing_views_source)
        self.assertIn('async function startTest(event)', take_test_source)
        self.assertIn('await requestExamFullscreen()', take_test_source)
        self.assertIn('let isStartingExam = false', take_test_source)
        self.assertIn(
            'isSubmitting || isStartingExam || IS_DEMO',
            take_test_source,
        )
        self.assertNotIn('const wasStarted = testStarted', take_test_source)
        self.assertIn(
            'await document.documentElement.requestFullscreen()',
            dashboard_source,
        )
        self.assertIn('window.location.href = card.dataset.href', dashboard_source)


    def test_answer_print_layout_is_compact_and_fragmentable(self):
        modal_source = get_template(
            'components/answer_view_modal.html'
        ).template.source
        print_source = get_template(
            'activities/print_answers.html'
        ).template.source
        print_component_source = get_template(
            'components/answer_sheet_print.html'
        ).template.source

        self.assertIn('answer-meta-left', modal_source)
        self.assertIn('answer-meta-right', modal_source)
        self.assertIn('answer-meta-label', modal_source)
        self.assertIn('<span class="answer-meta-divider" aria-hidden="true">|</span>', modal_source)
        self.assertIn('justify-content: space-between', modal_source)
        self.assertIn('class="answer-section answer-question-panel bg-gray-50 rounded-xl p-4"', modal_source)
        self.assertIn('문항 1. 평가 문항', modal_source)
        self.assertIn('class="p-0 answer-question-box"', modal_source)
        self.assertIn('font-size: 0.9rem', modal_source)
        self.assertIn('font-weight: normal', modal_source)
        self.assertIn('font-size: 0.995rem', modal_source)
        self.assertIn('-webkit-print-color-adjust: exact', modal_source)
        self.assertIn('print-color-adjust: exact', modal_source)
        self.assertIn('formatPrintAnswerContent(data.answerContent)', modal_source)
        self.assertIn('print-answer-title', modal_source)
        self.assertIn('print-meta-left', modal_source)
        self.assertIn('print-meta-right', modal_source)
        self.assertIn('print-question-panel', modal_source)
        self.assertIn('백지 제출', modal_source)

        self.assertIn("{% include 'components/answer_sheet_print.html' %}", print_source)
        self.assertIn('student-meta-left', print_source)
        self.assertIn('student-meta-right', print_source)
        self.assertIn('justify-content: space-between', print_source)
        self.assertIn('font-size: 10pt', print_source)
        self.assertIn('page-break-inside: auto', print_source)
        self.assertIn('break-inside: auto', print_source)
        self.assertIn('box-decoration-break: clone', print_source)
        self.assertIn('-webkit-box-decoration-break: clone', print_source)
        self.assertIn('data-format-answer-titles', print_source)
        self.assertIn('titleMatch = line.match', print_source)
        self.assertIn('백지 제출', print_source)
        self.assertNotIn('activity-title', print_source)
        self.assertNotIn('<table', print_source.lower())

        self.assertIn('student-meta-left', print_component_source)
        self.assertIn('student-meta-right', print_component_source)
        self.assertIn('문항 1. 평가 문항', print_component_source)
        self.assertIn('print-question-panel bg-gray-50 rounded-xl p-4', print_component_source)
        self.assertIn('백지 제출', print_component_source)

    def test_bulk_print_view_and_iframe_preview_are_resilient(self):
        export_view_source = (
            Path(settings.BASE_DIR) / 'activities' / 'views' / 'export_views.py'
        ).read_text(encoding='utf-8')
        result_source = get_template(
            'activities/activity_result.html'
        ).template.source

        self.assertIn('students = list(students)', export_view_source)
        self.assertIn('answers_by_student_id', export_view_source)
        self.assertIn("select_related('student', 'question')", export_view_source)
        self.assertNotIn('activity.get_student_answer(s)', export_view_source)
        self.assertIn('id="pdfPreviewStatus"', result_source)
        self.assertIn("iframe.getAttribute('src') === 'about:blank'", result_source)
        self.assertIn('일괄 출력 화면이 비어 있습니다.', result_source)
        self.assertIn('iframeDoc.body.innerText.trim().length > 0', result_source)
        self.assertIn('로딩이 오래 걸리고 있습니다.', result_source)
        self.assertIn('새 창에서 확인', result_source)

    def test_templates_using_localtime_load_tz_library(self):
        template_root = Path(settings.BASE_DIR) / 'templates'
        missing_tz_load = []

        for template_path in template_root.rglob('*.html'):
            source = template_path.read_text(encoding='utf-8')
            if 'localtime' not in source:
                continue

            load_tags = re.findall(r'{%\s*load\s+([^%]+?)\s*%}', source)
            has_tz = any('tz' in tag.split() for tag in load_tags)
            if not has_tz:
                missing_tz_load.append(str(template_path.relative_to(template_root)))

        self.assertEqual([], missing_tz_load)
    def test_activity_date_field_is_disabled_in_unified_form_and_save_logic(self):
        form_source = get_template(
            'activities/unified_form.html'
        ).template.source
        manage_source = (
            Path(settings.BASE_DIR) / 'activities' / 'views' / 'manage_views.py'
        ).read_text(encoding='utf-8')
        update_source = manage_source[
            manage_source.index('def unified_update'):
            manage_source.index('def unified_delete')
        ]
        main_source = (
            Path(settings.BASE_DIR) / 'activities' / 'views' / 'main_views.py'
        ).read_text(encoding='utf-8')

        self.assertIn('[비활성화] 수업 일시 필드', form_source)
        self.assertIn('name="activity_date"', form_source)
        self.assertIn('readonly disabled', form_source)
        self.assertNotIn('<input type="text" name="activity_date"', form_source.replace('<!--', '').split('-->')[-1])
        self.assertIn('activity_date=None', manage_source)
        self.assertNotIn('cleaned_data', update_source)
        self.assertNotIn("parse_dt(request.POST.get('activity_date'))", update_source)
        self.assertNotIn('activity.activity_date =', update_source)
        self.assertIn("config['detail'].pop('date', None)", main_source)

    def test_typing_activity_model_config_form_and_save_logic_exist(self):
        model_source = (
            Path(settings.BASE_DIR) / 'activities' / 'models.py'
        ).read_text(encoding='utf-8')
        main_source = (
            Path(settings.BASE_DIR) / 'activities' / 'views' / 'main_views.py'
        ).read_text(encoding='utf-8')
        manage_source = (
            Path(settings.BASE_DIR) / 'activities' / 'views' / 'manage_views.py'
        ).read_text(encoding='utf-8')
        form_source = get_template(
            'activities/unified_form.html'
        ).template.source

        for field_name in [
            'typing_type',
            'typing_position',
            'typing_level',
            'duration',
            'show_keyboard',
            'target_data',
        ]:
            self.assertIn(field_name, model_source)
            self.assertIn(field_name, form_source)

        self.assertIn('TYPING_TYPE_CHOICES', model_source)
        self.assertIn('TYPING_POSITION_CHOICES', model_source)
        self.assertIn('TYPING_LEVEL_CHOICES', model_source)
        self.assertIn("'타자 연습':", main_source)
        self.assertIn("configs['한글 타자 연습'] = configs['타자 연습']", main_source)
        self.assertIn("configs['영문 타자 연습'] = configs['타자 연습']", main_source)
        self.assertIn("'typing_fields':", main_source)
        self.assertIn("'visible_fields':", main_source)
        self.assertIn("'show_writing_rules': False", main_source)
        self.assertIn("'show_reference_materials': False", main_source)
        self.assertIn('타자연습 과제명', form_source)
        self.assertIn('연습 타자 위치', form_source)
        self.assertIn('타자 처음 왕초보', main_source)
        self.assertIn('고속 타자', main_source)
        self.assertIn('typingShortDurationOptions', form_source)
        self.assertIn('typingLongDateTimeOptions', form_source)
        self.assertIn('typing-keyboard-options', form_source)
        self.assertIn('{% if config.show_typing and config.typing_fields %}', form_source)
        self.assertIn('{% if config.show_reference_materials %}', form_source)
        self.assertIn('{% if config.show_writing_rules %}', form_source)
        self.assertIn('apply_typing_settings_from_post', manage_source)
        self.assertIn("if config.get('typing_fields'):", manage_source)


class AttachmentContextUnitTests(SimpleTestCase):
    def test_utf8_text_attachment_is_extracted_without_api_call(self):
        extracted = extract_text_from_upload('reference.txt', '평가 참고 자료'.encode('utf-8'))
        self.assertEqual('평가 참고 자료', extracted)

    def test_unsupported_attachment_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_text_from_upload('archive.zip', b'not-supported')

    def test_gpt_4o_mini_cost_uses_cached_token_discount(self):
        cost = estimate_openai_cost_usd('gpt-4o-mini', {
            'prompt_tokens': 10_000,
            'cached_tokens': 4_000,
            'completion_tokens': 1_000,
        })
        self.assertEqual('0.001800', str(cost))

    def test_responses_api_usage_is_normalized_for_ocr_cost_log(self):
        usage = normalize_openai_usage({
            'usage': {'input_tokens': 800, 'output_tokens': 200, 'total_tokens': 1000}
        })
        self.assertEqual(800, usage['prompt_tokens'])
        self.assertEqual(200, usage['completion_tokens'])
        self.assertEqual(1000, usage['total_tokens'])


class AIFeedbackPromptContractTests(SimpleTestCase):
    def test_feedback_contract_requires_letter_and_forbids_activity_sheet(self):
        contract = TASK_OUTPUT_CONTRACTS['feedback']
        self.assertIn('한 편의 편지', contract)
        self.assertIn('소제목·번호·목록 없이', contract)
        self.assertIn('활동 제목', FEEDBACK_BASE_PROMPT)
        self.assertIn('만들지 마세요', FEEDBACK_BASE_PROMPT)

    def test_each_task_has_an_independent_instruction_and_contract(self):
        expected_types = {'grading', 'feedback', 'rewrite', 'relay'}
        self.assertEqual(expected_types, set(TASK_OUTPUT_CONTRACTS))
        self.assertEqual(expected_types, set(TASK_USER_INSTRUCTIONS))
        self.assertNotIn('활동 제목', TASK_USER_INSTRUCTIONS['feedback'])

    def test_feedback_definition_and_component_rules_are_fixed_materials(self):
        self.assertIn('일상적인 편지글', FEEDBACK_BASE_PROMPT)
        self.assertIn('답안 요약', FEEDBACK_BASE_PROMPT)
        self.assertIn('1~2문장', FEEDBACK_BASE_PROMPT)
        self.assertIn('선택한 항목만', FEEDBACK_BASE_PROMPT)

    def test_feedback_contract_forbids_second_person_and_student_subject_honorifics(self):
        self.assertIn("2인칭 대명사 '당신'", FEEDBACK_BASE_PROMPT)
        self.assertIn("'학생님'", FEEDBACK_BASE_PROMPT)
        self.assertIn("주체 높임 선어말어미 '-시-'", FEEDBACK_BASE_PROMPT)
        self.assertIn('학생이 나누었습니다/썼습니다/보여주었습니다/작성했습니다', FEEDBACK_BASE_PROMPT)
        self.assertIn('결과를 출력하기 전에 금지 호칭', FEEDBACK_BASE_PROMPT)

    def test_middle_school_guide_controls_readability_on_four_axes(self):
        school = SimpleNamespace(
            level='MID',
            name='영문중학교',
            get_level_display=lambda: '중학교',
        )
        prompt = get_school_level_prompt(SimpleNamespace(school=school))
        self.assertIn('영문중학교의 중학교 학생', prompt)
        self.assertIn('분석의 깊이', prompt)
        self.assertIn('단어 선택', prompt)
        self.assertIn('문장의 복잡성', prompt)
        self.assertIn('문장의 길이', prompt)
        self.assertIn('25~45자', prompt)
        self.assertIn('독해 수준 규칙을 우선', prompt)

    def test_missing_school_falls_back_to_middle_school_guide(self):
        prompt = get_school_level_prompt(SimpleNamespace(school=None))
        self.assertIn('중학교 학생 독해 수준', prompt)

    def test_system_prompt_order_is_task_school_persona_tone(self):
        prompt = compose_ai_system_prompt(
            task_prompt='FEEDBACK',
            school_level_prompt='SCHOOL_LEVEL',
            persona_prompt='PERSONA',
            effective_tone='TONE',
            effective_length='LENGTH',
            tone_style_prompt='TONE_PRESET',
        )
        positions = [
            prompt.index('FEEDBACK'),
            prompt.index('SCHOOL_LEVEL'),
            prompt.index('PERSONA'),
            prompt.index('TONE'),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('TONE_PRESET', prompt)

    def test_centered_tone_scale_maps_to_database_levels(self):
        self.assertEqual(
            [1, 2, 3, 4, 5],
            [
                normalize_tone_attribute_value(value, 'centered_5')
                for value in (-2, -1, 0, 1, 2)
            ],
        )

    def test_formality_level_four_enforces_haeyo_and_forbids_banmal(self):
        contract = build_formality_output_contract(4)
        self.assertIn('일상적 존댓말인 해요체', contract)
        self.assertIn('~했어요', contract)
        self.assertIn('~했어, ~구나, ~이야', contract)
        self.assertIn('다른 문체 속성보다 우선', contract)

    def test_formality_level_five_forbids_student_subject_honorific(self):
        contract = build_formality_output_contract(5)
        self.assertIn('공식적인 하십시오체', contract)
        self.assertIn("주체 높임 '-시-'", contract)


class FeedbackResultTitleTests(SimpleTestCase):
    def test_saved_title_is_used_for_portfolio_index(self):
        result = FeedbackResult(task_type='feedback', feedback_title='은채의 주장 글 피드백')
        self.assertEqual('은채의 주장 글 피드백', result.display_title)

    def test_legacy_result_falls_back_to_task_label(self):
        result = FeedbackResult(task_type='feedback', feedback_title='')
        self.assertEqual('피드백', result.display_title)

    def test_published_and_read_feedback_is_not_editable(self):
        result = FeedbackResult(is_published=True, is_read=True)
        self.assertFalse(result.is_editable)

    def test_unread_published_feedback_remains_editable(self):
        result = FeedbackResult(is_published=True, is_read=False)
        self.assertTrue(result.is_editable)

    def test_answer_detail_contains_publish_confirmation_ui(self):
        source = get_template('activities/answer_detail.html').template.source
        self.assertIn('feedbackPublishDialog', source)
        self.assertIn('data-publish-feedback', source)
        self.assertIn('학생이 열람한 뒤에는 피드백을 수정할 수 없습니다.', source)


class AnswerCharacterCountTests(SimpleTestCase):
    def test_non_whitespace_length_excludes_spaces_tabs_and_linebreaks(self):
        self.assertEqual(6, non_whitespace_length('가 나\t다\n라마바'))

    def test_non_whitespace_length_handles_empty_values(self):
        self.assertEqual(0, non_whitespace_length(None))
        self.assertEqual(0, non_whitespace_length(' \n\t '))

    def test_non_whitespace_length_is_registered_as_template_filter(self):
        rendered = Template(
            '{% load answer_extras %}{{ value|non_whitespace_length }}'
        ).render(Context({'value': '한 글 \n테스트'}))
        self.assertEqual('5', rendered)

    def test_answer_modal_contains_per_item_counter_renderer(self):
        source = get_template('components/answer_view_modal.html').template.source
        self.assertIn('countNonWhitespace', source)
        self.assertIn('countAnswerBodyCharacters', source)
        self.assertIn('normalizeAnswerTitle', source)
        self.assertIn('answer-character-count', source)
        self.assertIn('currentCountBadge', source)
        self.assertNotIn('totalCountBadge.hidden = hasHeader', source)


class CreativeSidebarMenuTests(SimpleTestCase):
    def test_class_grade_feature_activity_menu_is_available(self):
        source = get_template('base.html').template.source
        self.assertIn('sub=학급/학년특색활동', source)
        self.assertIn("request.GET.sub == '학급/학년특색활동'", source)

    def test_class_grade_feature_activity_has_its_own_form_config(self):
        config = get_form_config('학급/학년특색활동')
        self.assertEqual('학급/학년특색활동명', config['basic']['section'])
        self.assertEqual('평가 문항', config['detail']['content'])
        self.assertEqual(['활동 목표', '활동 과정', '배우고 느낀 점'], config['default_q'])


class SchoolLifeSidebarMenuTests(SimpleTestCase):
    def test_class_life_menu_is_renamed_to_life_education(self):
        source = get_template('base.html').template.source
        self.assertIn('sub=생활 교육', source)
        self.assertIn("request.GET.sub == '생활 교육'", source)
        self.assertNotIn('sub=학급 생활', source)

    def test_life_education_uses_the_default_activity_form_config(self):
        config = get_form_config('생활 교육')
        self.assertEqual('활동명', config['basic']['section'])
        self.assertEqual('내용', config['detail']['content'])
        self.assertEqual(['항목 1', '항목 2', '항목 3'], config['default_q'])
