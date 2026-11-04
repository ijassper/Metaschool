"""Run the optional local ONNX OCR model outside the web worker process."""

import fcntl
import json
import sys
import time
from pathlib import Path


def main():
    import rapidocr
    from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

    models = Path(rapidocr.__file__).resolve().parent / 'models'
    detection = models / 'ch_PP-OCRv5_det_mobile_ir9.onnx'
    recognition = models / 'korean_PP-OCRv5_rec_mobile_ir9.onnx'
    if not detection.is_file() or not recognition.is_file():
        raise RuntimeError('OCR 모델 파일이 준비되지 않았습니다.')
    with open('/tmp/ingrid-course-notebook-ocr.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        started = time.monotonic()
        ocr = RapidOCR(params={
            'Det.ocr_version': OCRVersion.PPOCRV5,
            'Det.model_type': ModelType.MOBILE,
            'Det.model_path': str(detection),
            'Det.limit_side_len': 1280,
            'Det.box_thresh': 0.3,
            'Rec.ocr_version': OCRVersion.PPOCRV5,
            'Rec.lang_type': LangRec.KOREAN,
            'Rec.model_type': ModelType.MOBILE,
            'Rec.model_path': str(recognition),
        })
        result = ocr(sys.argv[1])
        lines = [str(line) for line in result.txts] if result.txts is not None else []
        scores = list(result.scores) if result.scores is not None else []
        print('INGRID_OCR_RESULT=' + json.dumps({
            'text': '\n'.join(lines).strip(),
            'confidence': float(sum(scores) / len(scores)) if scores else None,
            'seconds': round(time.monotonic() - started, 2),
        }, ensure_ascii=False))


if __name__ == '__main__':
    main()
