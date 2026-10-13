"""교과 수업 노트의 색상 보존 보정과 OCR 처리."""

import base64
import hashlib
import io
import math

import requests
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageFilter, ImageMath, ImageOps

from accounts.models import SystemConfig
from .attachment_context import (
    estimate_openai_cost_usd,
    extract_text_with_openai_ocr,
    normalize_openai_usage,
)
from .models import CourseNotebookPage


PROCESSING_VERSION = 2
MAX_IMAGE_EDGE = 2400
A4_PAGE_SIZE = (1240, 1754)


def _read_original(page):
    page.image.open('rb')
    try:
        return page.image.read()
    finally:
        page.image.close()


def _order_quad(points):
    """OpenCV 문서 모서리를 좌상단부터 시계 방향으로 정렬한다."""
    import numpy as np

    points = np.asarray(points, dtype='float32').reshape(4, 2)
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    return np.asarray([
        points[sums.argmin()], points[differences.argmin()],
        points[sums.argmax()], points[differences.argmax()],
    ], dtype='float32')


def _deskew_document(image):
    """배경에서 가장 큰 종이 경계를 찾아 A4 세로 규격으로 원근 보정한다."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    rgb = np.asarray(image)
    height, width = rgb.shape[:2]
    scale = min(1.0, 1400 / max(width, height))
    work = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(work, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 45, 135)
    edges = cv2.morphologyEx(
        edges, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
        iterations=2,
    )
    contours = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]
    image_area = work.shape[0] * work.shape[1]
    quad = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:15]:
        if cv2.contourArea(contour) < image_area * .12:
            break
        perimeter = cv2.arcLength(contour, True)
        candidate = cv2.approxPolyDP(contour, .02 * perimeter, True)
        if len(candidate) == 4 and cv2.isContourConvex(candidate):
            quad = candidate.reshape(4, 2) / scale
            break
    if quad is None:
        return None

    source = _order_quad(quad)
    top = math.dist(source[0], source[1])
    bottom = math.dist(source[3], source[2])
    left = math.dist(source[0], source[3])
    right = math.dist(source[1], source[2])
    if max(top, bottom) > max(left, right):
        source = source[[1, 2, 3, 0]]
    target_width, target_height = A4_PAGE_SIZE
    destination = np.asarray([
        [0, 0], [target_width - 1, 0],
        [target_width - 1, target_height - 1], [0, target_height - 1],
    ], dtype='float32')
    matrix = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(
        rgb, matrix, A4_PAGE_SIZE, flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255),
    )
    return Image.fromarray(warped, 'RGB')


def correct_notebook_image(data):
    """종이 원근을 A4로 펴고 색 펜을 유지하면서 그림자를 완화한다."""
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    document = _deskew_document(image)
    if document is not None:
        image = document
    else:
        image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
        image = ImageOps.pad(image, A4_PAGE_SIZE, method=Image.Resampling.LANCZOS, color='white')

    hue, saturation, value = image.convert('HSV').split()
    radius = max(24, min(image.size) // 18)
    background = value.filter(ImageFilter.GaussianBlur(radius=radius))
    normalized = ImageMath.eval(
        "convert((value * 242) / (background + 1), 'L')",
        value=value, background=background,
    )
    normalized = ImageOps.autocontrast(normalized, cutoff=(0.4, 0.4))
    corrected_value = Image.blend(value, normalized, 0.78)
    corrected = Image.merge('HSV', (hue, saturation, corrected_value)).convert('RGB')
    corrected = corrected.filter(ImageFilter.UnsharpMask(radius=1.2, percent=115, threshold=3))

    output = io.BytesIO()
    corrected.save(output, format='JPEG', quality=88, optimize=True, progressive=True, dpi=(150, 150))
    return output.getvalue()


def ensure_archive_image(page):
    """PDF/책장 UI용 A4 보정 이미지를 만들고 원본과 별도로 보존한다."""
    original = _read_original(page)
    source_hash = hashlib.sha256(original).hexdigest()
    if (
        page.processed_image
        and page.source_hash == source_hash
        and page.processing_version == PROCESSING_VERSION
    ):
        return page
    corrected = correct_notebook_image(original)
    if page.processed_image:
        page.processed_image.delete(save=False)
    page.processed_image.save(
        f'notebook-page-{page.id}-a4-v{PROCESSING_VERSION}.jpg',
        ContentFile(corrected), save=False,
    )
    page.source_hash = source_hash
    page.processing_version = PROCESSING_VERSION
    page.save(update_fields=['processed_image', 'source_hash', 'processing_version'])
    return page


def accept_native_document_scan(page):
    """ML Kit에서 보정한 JPEG를 추가 서버 필터 없이 아카이브 원본으로 채택한다."""
    scanned = _read_original(page)
    source_hash = hashlib.sha256(scanned).hexdigest()
    if page.processed_image:
        page.processed_image.delete(save=False)
    page.processed_image.save(
        f'notebook-page-{page.id}-native.jpg', ContentFile(scanned), save=False,
    )
    page.source_hash = source_hash
    page.processing_version = PROCESSING_VERSION
    page.save(update_fields=['processed_image', 'source_hash', 'processing_version'])
    return page


def _config_value(key):
    return (SystemConfig.objects.filter(key_name=key).values_list('value', flat=True).first() or '').strip()


def _simplify_google_layout(annotation):
    result = {'pages': []}
    for page in annotation.get('pages') or []:
        blocks = []
        for block in page.get('blocks') or []:
            parts = []
            for paragraph in block.get('paragraphs') or []:
                words = []
                for word in paragraph.get('words') or []:
                    words.append(''.join(symbol.get('text', '') for symbol in word.get('symbols') or []))
                if words:
                    parts.append(' '.join(words))
            blocks.append({
                'text': '\n'.join(parts),
                'confidence': block.get('confidence'),
                'vertices': (block.get('boundingBox') or {}).get('normalizedVertices')
                    or (block.get('boundingBox') or {}).get('vertices') or [],
            })
        result['pages'].append({
            'width': page.get('width'), 'height': page.get('height'), 'blocks': blocks,
        })
    return result


def _google_vision_ocr(data, api_key):
    response = requests.post(
        f'https://vision.googleapis.com/v1/images:annotate?key={api_key}',
        json={'requests': [{
            'image': {'content': base64.b64encode(data).decode('ascii')},
            'features': [{'type': 'DOCUMENT_TEXT_DETECTION'}],
            'imageContext': {'languageHints': ['ko']},
        }]},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    item = (payload.get('responses') or [{}])[0]
    if item.get('error'):
        raise RuntimeError(item['error'].get('message') or 'Google Vision OCR 처리에 실패했습니다.')
    annotation = item.get('fullTextAnnotation') or {}
    text = (annotation.get('text') or '').strip()
    confidences = [
        block.get('confidence') for page in annotation.get('pages') or []
        for block in page.get('blocks') or [] if block.get('confidence') is not None
    ]
    return text, _simplify_google_layout(annotation), (
        sum(confidences) / len(confidences) if confidences else None
    )


def process_course_notebook_page(page):
    original = _read_original(page)
    source_hash = hashlib.sha256(original).hexdigest()
    if (
        page.source_hash == source_hash
        and page.processing_version == PROCESSING_VERSION
        and page.processed_image
        and page.ocr_raw_text
        and page.ocr_status in {
            CourseNotebookPage.OcrStatus.COMPLETED,
            CourseNotebookPage.OcrStatus.NEEDS_REVIEW,
            CourseNotebookPage.OcrStatus.REVIEWED,
        }
    ):
        return page

    page.ocr_status = CourseNotebookPage.OcrStatus.PROCESSING
    page.ocr_error = ''
    page.ocr_processed_at = timezone.now()
    page.save(update_fields=['ocr_status', 'ocr_error', 'ocr_processed_at'])
    try:
        page = ensure_archive_image(page)
        page.processed_image.open('rb')
        try:
            corrected = page.processed_image.read()
        finally:
            page.processed_image.close()

        vision_key = _config_value('GOOGLE_VISION_API_KEY')
        openai_keys = [key.strip() for key in _config_value('OPENAI_API_KEY').split(',') if key.strip()]
        if vision_key:
            text, layout, confidence = _google_vision_ocr(corrected, vision_key)
            provider, model = 'google-vision', 'DOCUMENT_TEXT_DETECTION'
            usage = {'billable_images': 1, 'estimated_unit_cost_usd': '0.0015'}
        elif openai_keys:
            instruction = (
                '한국 학생이 손글씨로 작성한 교과 수업 노트입니다. 보이는 글자를 읽기 순서대로 정확히 옮기세요. '
                '제목, 글머리표, 문단과 표의 행·열 관계를 보존하되 이미지에 없는 내용은 추측하지 마세요. '
                '그래프나 그림은 [그래프] 또는 [그림]으로 표시하고, 인식한 텍스트만 반환하세요.'
            )
            text, response_data = extract_text_with_openai_ocr(
                filename='notebook.jpg', data=corrected, api_key=openai_keys[0],
                model='gpt-4o-mini', detail='high', instruction=instruction,
            )
            normalized_usage = normalize_openai_usage(response_data)
            normalized_usage['estimated_cost_usd'] = str(
                estimate_openai_cost_usd('gpt-4o-mini', normalized_usage)
            )
            layout, confidence = {}, None
            provider, model, usage = 'openai', 'gpt-4o-mini', normalized_usage
        else:
            raise RuntimeError('OCR API 키가 없습니다. 시스템 설정 센터에서 Google Vision 또는 OpenAI API 키를 등록해 주세요.')

        if not text:
            raise RuntimeError('사진에서 변환할 텍스트를 찾지 못했습니다.')
        page.ocr_raw_text = text[:100_000]
        page.ocr_layout = layout
        page.ocr_provider = provider
        page.ocr_model_version = model
        page.ocr_confidence = confidence
        page.ocr_usage = usage
        page.ocr_status = CourseNotebookPage.OcrStatus.NEEDS_REVIEW
        page.ocr_error = ''
    except Exception as exc:
        page.ocr_status = CourseNotebookPage.OcrStatus.FAILED
        page.ocr_error = str(exc)[:500]
    page.source_hash = source_hash
    page.processing_version = PROCESSING_VERSION
    page.ocr_processed_at = timezone.now()
    page.save()
    return page
