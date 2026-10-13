"""교과 수업 노트의 색상 보존 보정과 OCR 처리."""

import base64
import hashlib
import io

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


PROCESSING_VERSION = 1
MAX_IMAGE_EDGE = 2400


def _read_original(page):
    page.image.open('rb')
    try:
        return page.image.read()
    finally:
        page.image.close()


def correct_notebook_image(data):
    """색 펜과 형광펜을 유지하면서 불균일한 조명과 그림자를 완화한다."""
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)

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
    corrected.save(output, format='JPEG', quality=88, optimize=True, progressive=True)
    return output.getvalue()


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
        corrected = correct_notebook_image(original)
        if page.processed_image:
            page.processed_image.delete(save=False)
        page.processed_image.save(
            f'notebook-page-{page.id}-v{PROCESSING_VERSION}.jpg',
            ContentFile(corrected), save=False,
        )

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
