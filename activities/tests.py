from types import SimpleNamespace
from pathlib import Path
import re

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.template.loader import get_template
from django.urls import reverse
from django.conf import settings

from .views.exam_views import pdf_viewer


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
