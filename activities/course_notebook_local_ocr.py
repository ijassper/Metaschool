"""Run the local RapidOCR model in a separate, memory-limited process."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def recognize_notebook_image(image_path):
    python_path = os.environ.get('COURSE_NOTEBOOK_OCR_PYTHON')
    if not python_path:
        python_path = str(Path(settings.BASE_DIR) / '.ocr-venv' / 'bin' / 'python')
    if not Path(python_path).is_file():
        raise RuntimeError('오픈소스 OCR 실행 환경이 준비되지 않았습니다.')
    worker_path = Path(__file__).with_name('course_notebook_ocr_worker.py')
    environment = os.environ.copy()
    environment['OMP_NUM_THREADS'] = '2'
    try:
        completed = subprocess.run(
            [python_path, str(worker_path), str(image_path)],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=150, check=False, env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('OCR 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.') from exc
    if completed.returncode != 0:
        logger.error('Local OCR failed (exit %s): %s', completed.returncode, completed.stderr[-2000:])
        raise RuntimeError('오픈소스 OCR 실행에 실패했습니다. 서버 로그를 확인해 주세요.')
    marker = 'INGRID_OCR_RESULT='
    result_line = next(
        (line for line in reversed(completed.stdout.splitlines()) if line.startswith(marker)), None,
    )
    if not result_line:
        raise RuntimeError('OCR 결과를 읽을 수 없습니다.')
    return json.loads(result_line[len(marker):])
