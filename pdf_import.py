import re

import fitz
import requests
from deep_translator import GoogleTranslator

HIGHLIGHT_ANNOT_TYPE = 8


def _is_yellow(rgb):
    if not rgb or len(rgb) < 3:
        return False
    r, g, b = rgb[:3]
    return r > 0.6 and g > 0.6 and b < 0.5


def extract_highlighted_words(pdf_bytes):
    """PDF 바이트에서 노란색으로 하이라이트된 영단어 목록을 추출합니다."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    raw_texts = []

    for page in doc:
        for annot in page.annots() or []:
            if annot.type[0] != HIGHLIGHT_ANNOT_TYPE:
                continue
            if not _is_yellow((annot.colors or {}).get("stroke")):
                continue

            points = annot.vertices
            if not points:
                continue

            for i in range(0, len(points), 4):
                quad_pts = points[i:i + 4]
                if len(quad_pts) < 4:
                    continue
                rect = fitz.Quad(quad_pts).rect
                text = page.get_textbox(rect).strip()
                if text:
                    raw_texts.append(text)

    doc.close()

    words = []
    seen = set()
    for text in raw_texts:
        for token in re.findall(r"[A-Za-z][A-Za-z'-]*", text):
            key = token.lower()
            if len(token) > 1 and key not in seen:
                seen.add(key)
                words.append(token)

    return words


def lookup_word(word):
    """단어의 한글 뜻(번역)과 영어 예문을 조회합니다. 실패 시 빈 값을 반환합니다."""
    meaning = ""
    example = ""

    try:
        meaning = GoogleTranslator(source="en", target="ko").translate(word)
    except Exception:
        meaning = ""

    try:
        resp = requests.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", timeout=5
        )
        if resp.status_code == 200:
            for entry in resp.json():
                for meaning_block in entry.get("meanings", []):
                    for definition in meaning_block.get("definitions", []):
                        if definition.get("example"):
                            example = definition["example"]
                            break
                    if example:
                        break
                if example:
                    break
    except Exception:
        example = ""

    return meaning or "(뜻을 찾을 수 없음)", example
