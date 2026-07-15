import io

import openpyxl

_WORD_HEADERS = {"word", "단어", "영단어"}
_MEANING_HEADERS = {"meaning", "뜻", "의미"}
_EXAMPLE_HEADERS = {"example", "예문", "예시"}


def _find_col(header, names, default):
    for i, h in enumerate(header):
        if h in names:
            return i
    return default


def extract_excel_words(file_bytes):
    """엑셀 파일(첫 행: 헤더)에서 단어/뜻/예문 목록을 추출합니다."""
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    if len(rows) < 2:
        return []

    header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    word_idx = _find_col(header, _WORD_HEADERS, 0)
    meaning_idx = _find_col(header, _MEANING_HEADERS, 1)
    example_idx = _find_col(header, _EXAMPLE_HEADERS, 2)

    def cell(row, idx):
        if idx is None or idx >= len(row) or row[idx] is None:
            return ""
        return str(row[idx]).strip()

    entries = []
    seen = set()
    for row in rows[1:]:
        word = cell(row, word_idx)
        if not word or word.lower() in seen:
            continue
        seen.add(word.lower())
        entries.append({
            "word": word,
            "meaning": cell(row, meaning_idx),
            "example": cell(row, example_idx),
        })

    return entries
