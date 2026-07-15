import io
import re

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, find_objects, label

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def _yellow_mask(arr):
    r = arr[..., 0].astype(int)
    g = arr[..., 1].astype(int)
    b = arr[..., 2].astype(int)
    return (r > 170) & (g > 170) & (b < 140)


def extract_highlighted_words(image_bytes):
    """이미지에서 노란색으로 하이라이트된 영단어 목록을 추출합니다."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(image)

    mask = _yellow_mask(arr)
    if not mask.any():
        return []

    # 글자 사이의 작은 틈을 이어붙여 하이라이트 영역을 단어/구 단위로 묶는다
    mask = binary_dilation(mask, structure=np.ones((3, 9)), iterations=2)
    labeled, num_regions = label(mask)

    reader = _get_reader()
    words = []
    seen = set()
    pad = 4

    for region_slice in find_objects(labeled):
        if region_slice is None:
            continue
        y0, y1 = region_slice[0].start, region_slice[0].stop
        x0, x1 = region_slice[1].start, region_slice[1].stop
        if (y1 - y0) * (x1 - x0) < 40:
            continue

        y0p, y1p = max(y0 - pad, 0), min(y1 + pad, arr.shape[0])
        x0p, x1p = max(x0 - pad, 0), min(x1 + pad, arr.shape[1])
        crop = arr[y0p:y1p, x0p:x1p]

        for _bbox, text, _confidence in reader.readtext(crop):
            for token in re.findall(r"[A-Za-z][A-Za-z'-]*", text):
                key = token.lower()
                if len(token) > 1 and key not in seen:
                    seen.add(key)
                    words.append(token)

    return words
