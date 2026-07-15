from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import os
import random
from config import get_connection, init_db, SECRET_KEY
from pdf_import import extract_highlighted_words, lookup_word
from image_import import extract_highlighted_words as extract_highlighted_words_image
from excel_import import extract_excel_words

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB


@app.context_processor
def inject_asset_url():
    def asset_url(filename):
        path = os.path.join(app.static_folder, filename)
        try:
            version = int(os.path.getmtime(path))
        except OSError:
            version = 0
        return url_for("static", filename=filename) + f"?v={version}"
    return dict(asset_url=asset_url)


# ── 앞표지 ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("cover.html")


# ── 공부방 (홈) ────────────────────────────────────────────────────────────
@app.route("/room")
def room():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM Words")
    total_words = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM StudyHistory WHERE is_correct = 1")
    correct_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM StudyHistory")
    total_studied = cursor.fetchone()[0]

    cursor.execute("""
        SELECT TOP 5 w.word, w.meaning
        FROM Words w
        ORDER BY w.created_at DESC
    """)
    recent_words = cursor.fetchall()

    cursor.execute("""
        SELECT l.id, l.name, COUNT(w.id) as word_count
        FROM Lessons l
        LEFT JOIN Words w ON l.id = w.lesson_id
        GROUP BY l.id, l.name, l.sort_order
        ORDER BY l.sort_order, l.id
    """)
    lessons = cursor.fetchall()

    cursor.close()
    conn.close()

    accuracy = round(correct_count / total_studied * 100, 1) if total_studied > 0 else 0

    return render_template("room.html",
                           total_words=total_words,
                           accuracy=accuracy,
                           total_studied=total_studied,
                           recent_words=recent_words,
                           lessons=lessons)


# ── 단어 목록 ────────────────────────────────────────────────────────────────
@app.route("/words")
def wordlist():
    search = request.args.get("search", "").strip()

    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT w.id, w.word, w.meaning, w.example_sentence, w.created_at
        FROM Words w
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (w.word LIKE ? OR w.meaning LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY w.created_at DESC"
    cursor.execute(query, params)
    words = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("wordlist.html",
                           words=words,
                           search=search)


# ── 단어 추가 ────────────────────────────────────────────────────────────────
@app.route("/add", methods=["GET", "POST"])
def add_word():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM Lessons ORDER BY sort_order, id")
    lessons = cursor.fetchall()

    if request.method == "POST":
        word = request.form.get("word", "").strip()
        meaning = request.form.get("meaning", "").strip()
        example = request.form.get("example", "").strip()
        lesson_id = request.form.get("lesson_id") or None

        if not word or not meaning:
            flash("단어와 뜻은 필수 입력입니다.", "error")
        else:
            cursor.execute("SELECT id FROM Words WHERE LOWER(word) = LOWER(?)", (word,))
            if cursor.fetchone():
                flash(f"'{word}'는 이미 등록된 단어입니다.", "error")
            else:
                cursor.execute("""
                    INSERT INTO Words (word, meaning, example_sentence, lesson_id)
                    VALUES (?, ?, ?, ?)
                """, (word, meaning, example or None, lesson_id))
                conn.commit()
                flash(f"'{word}' 단어가 추가되었습니다!", "success")
                cursor.close()
                conn.close()
                if lesson_id:
                    return redirect(url_for("lesson_detail", lesson_id=lesson_id))
                return redirect(url_for("wordlist"))

    selected_lesson = request.args.get("lesson_id", "")
    cursor.close()
    conn.close()
    return render_template("add_word.html", lessons=lessons, selected_lesson=selected_lesson)


# ── 단어 수정 ────────────────────────────────────────────────────────────────
@app.route("/edit/<int:word_id>", methods=["GET", "POST"])
def edit_word(word_id):
    conn = get_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        word = request.form.get("word", "").strip()
        meaning = request.form.get("meaning", "").strip()
        example = request.form.get("example", "").strip()
        lesson_id = request.form.get("lesson_id") or None

        cursor.execute(
            "SELECT id FROM Words WHERE LOWER(word) = LOWER(?) AND id <> ?",
            (word, word_id)
        )
        if cursor.fetchone():
            flash(f"'{word}'는 이미 등록된 단어입니다.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("edit_word", word_id=word_id))

        cursor.execute("""
            UPDATE Words SET word=?, meaning=?, example_sentence=?, lesson_id=?
            WHERE id=?
        """, (word, meaning, example or None, lesson_id, word_id))
        conn.commit()
        flash("단어가 수정되었습니다.", "success")
        cursor.close()
        conn.close()
        if lesson_id:
            return redirect(url_for("lesson_detail", lesson_id=lesson_id))
        return redirect(url_for("wordlist"))

    cursor.execute("""
        SELECT id, word, meaning, example_sentence, lesson_id
        FROM Words WHERE id=?
    """, (word_id,))
    word_data = cursor.fetchone()

    cursor.execute("SELECT id, name FROM Lessons ORDER BY sort_order, id")
    lessons = cursor.fetchall()

    cursor.close()
    conn.close()

    if not word_data:
        flash("단어를 찾을 수 없습니다.", "error")
        return redirect(url_for("wordlist"))

    return render_template("edit_word.html", word=word_data, lessons=lessons)


@app.route("/api/lookup")
def api_lookup():
    """영단어의 뜻/예문 자동 조회 (AJAX)"""
    word = request.args.get("word", "").strip()
    if not word:
        return jsonify({"error": "단어를 입력하세요."}), 400

    meaning, example = lookup_word(word)
    return jsonify({"meaning": meaning, "example": example})


# ── 단어 삭제 ────────────────────────────────────────────────────────────────
@app.route("/delete/<int:word_id>", methods=["POST"])
def delete_word(word_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM StudyHistory WHERE word_id=?", (word_id,))
    cursor.execute("DELETE FROM Words WHERE id=?", (word_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("단어가 삭제되었습니다.", "success")
    return redirect(url_for("wordlist"))


@app.route("/words/bulk-delete", methods=["POST"])
def bulk_delete_words():
    word_ids = request.form.getlist("word_ids")
    if not word_ids:
        flash("삭제할 단어를 선택하세요.", "error")
        return redirect(url_for("wordlist"))

    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join("?" * len(word_ids))
    cursor.execute(f"DELETE FROM StudyHistory WHERE word_id IN ({placeholders})", word_ids)
    cursor.execute(f"DELETE FROM Words WHERE id IN ({placeholders})", word_ids)
    conn.commit()
    cursor.close()
    conn.close()

    flash(f"단어 {len(word_ids)}개가 삭제되었습니다.", "success")
    return redirect(url_for("wordlist"))


# ── 퀴즈 ────────────────────────────────────────────────────────────────────
@app.route("/quiz")
def quiz():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM Words")
    count = cursor.fetchone()[0]

    cursor.execute("SELECT id, name FROM Lessons ORDER BY sort_order, id")
    lessons = cursor.fetchall()

    cursor.close()
    conn.close()

    session.pop("quiz_queue", None)
    session.pop("quiz_last_id", None)
    session.pop("quiz_lesson_id", None)
    return render_template("quiz.html", word_count=count, lessons=lessons)


@app.route("/quiz/next")
def quiz_next():
    """퀴즈용 단어 반환 - 선택된 Lesson(또는 전체)을 무작위 순서로 한 바퀴 돈 뒤에만 다시 섞음 (AJAX)"""
    lesson_id = request.args.get("lesson_id", "")

    conn = get_connection()
    cursor = conn.cursor()

    if lesson_id:
        cursor.execute(
            "SELECT id, word, meaning, example_sentence FROM Words WHERE lesson_id=?",
            (lesson_id,)
        )
    else:
        cursor.execute("SELECT id, word, meaning, example_sentence FROM Words")
    words = cursor.fetchall()
    cursor.close()
    conn.close()

    if not words:
        return jsonify({"error": "단어가 없습니다."})

    # 선택된 Lesson이 바뀌면 큐를 새로 만든다
    if session.get("quiz_lesson_id") != lesson_id:
        session.pop("quiz_queue", None)
        session.pop("quiz_last_id", None)
        session["quiz_lesson_id"] = lesson_id

    word_map = {w[0]: w for w in words}
    queue = [word_id for word_id in session.get("quiz_queue", []) if word_id in word_map]
    last_id = session.get("quiz_last_id")

    if not queue:
        queue = list(word_map.keys())
        random.shuffle(queue)
        # 이전 라운드 마지막 단어와 새 라운드 첫 단어가 겹치지 않도록 보정
        if len(queue) > 1 and queue[0] == last_id:
            swap_at = random.randint(1, len(queue) - 1)
            queue[0], queue[swap_at] = queue[swap_at], queue[0]

    chosen_id = queue.pop(0)
    session["quiz_queue"] = queue
    session["quiz_last_id"] = chosen_id
    chosen = word_map[chosen_id]

    # 오답 보기 3개 생성
    all_meanings = [w[2] for w in words if w[0] != chosen[0]]
    wrong_choices = random.sample(all_meanings, min(3, len(all_meanings)))
    choices = wrong_choices + [chosen[2]]
    random.shuffle(choices)

    return jsonify({
        "id": chosen[0],
        "word": chosen[1],
        "meaning": chosen[2],
        "example": chosen[3] or "",
        "choices": choices,
    })


@app.route("/quiz/submit", methods=["POST"])
def quiz_submit():
    """퀴즈 정답 제출 (AJAX)"""
    data = request.get_json()
    word_id = data.get("word_id")
    is_correct = data.get("is_correct")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO StudyHistory (word_id, is_correct) VALUES (?, ?)",
        (word_id, 1 if is_correct else 0)
    )
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"status": "ok"})


# ── PDF/이미지 업로드 (하이라이트 단어 추출) ───────────────────────────────────
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


@app.route("/upload")
def upload_pdf():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM Lessons ORDER BY sort_order, id")
    lessons = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("upload.html", lessons=lessons)


@app.route("/api/extract-words", methods=["POST"])
def api_extract_words():
    """업로드된 PDF/이미지에서 하이라이트된 단어만 빠르게 추출 (AJAX, 1단계)"""
    file = request.files.get("pdf_file")
    if not file or file.filename == "":
        return jsonify({"error": "파일을 선택하세요."}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return jsonify({"error": "PDF 또는 이미지(PNG, JPG) 파일만 업로드할 수 있습니다."}), 400

    file_bytes = file.read()
    if ext == ".pdf":
        words = extract_highlighted_words(file_bytes)
    else:
        words = extract_highlighted_words_image(file_bytes)

    if not words:
        return jsonify({"error": "노란색으로 하이라이트된 단어를 찾지 못했습니다."}), 400

    default_lesson_name = os.path.splitext(file.filename)[0][:100]
    return jsonify({"words": words, "default_lesson_name": default_lesson_name})


@app.route("/api/extract-excel", methods=["POST"])
def api_extract_excel():
    """업로드된 엑셀 파일에서 단어/뜻/예문 표를 그대로 추출 (AJAX, 1단계)"""
    file = request.files.get("pdf_file")
    if not file or file.filename == "":
        return jsonify({"error": "파일을 선택하세요."}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".xlsx", ".xlsm"):
        return jsonify({"error": "엑셀(.xlsx) 파일만 업로드할 수 있습니다."}), 400

    entries = extract_excel_words(file.read())
    if not entries:
        return jsonify({"error": "엑셀에서 단어를 찾지 못했습니다. 첫 행에 '단어' 열이 있는지 확인하세요."}), 400

    default_lesson_name = os.path.splitext(file.filename)[0][:100]
    return jsonify({"entries": entries, "default_lesson_name": default_lesson_name})


@app.route("/api/save-words", methods=["POST"])
def api_save_words():
    """추출/조회된 단어들을 Lesson에 저장 (AJAX, 3단계)"""
    data = request.get_json()
    lesson_id = data.get("lesson_id") or None
    lesson_name = (data.get("lesson_name") or "").strip()[:100]
    entries = data.get("words") or []

    if not lesson_id and not lesson_name:
        return jsonify({"error": "Lesson 정보가 없습니다."}), 400

    conn = get_connection()
    cursor = conn.cursor()

    if lesson_id:
        cursor.execute("SELECT name FROM Lessons WHERE id=?", (lesson_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return jsonify({"error": "Lesson을 찾을 수 없습니다."}), 400
        lesson_name = row[0]
    else:
        cursor.execute("SELECT id FROM Lessons WHERE name=?", (lesson_name,))
        row = cursor.fetchone()
        if row:
            lesson_id = row[0]
        else:
            cursor.execute("""
                INSERT INTO Lessons (name, sort_order)
                OUTPUT INSERTED.id
                VALUES (?, (SELECT ISNULL(MAX(sort_order), 0) + 1 FROM Lessons))
            """, (lesson_name,))
            lesson_id = cursor.fetchone()[0]

    cursor.execute("SELECT LOWER(word) FROM Words")
    existing_words = {row[0] for row in cursor.fetchall()}

    added = 0
    skipped = 0
    for entry in entries:
        word = (entry.get("word") or "").strip()
        if not word or word.lower() in existing_words:
            skipped += 1
            continue
        meaning = (entry.get("meaning") or "").strip() or "(뜻을 찾을 수 없음)"
        example = (entry.get("example") or "").strip()
        cursor.execute("""
            INSERT INTO Words (word, meaning, example_sentence, lesson_id)
            VALUES (?, ?, ?, ?)
        """, (word, meaning, example or None, lesson_id))
        existing_words.add(word.lower())
        added += 1

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"lesson_name": lesson_name, "added": added, "skipped": skipped})


# ── Lesson 관리 ───────────────────────────────────────────────────────────
@app.route("/lessons")
def lessons():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.id, l.name, COUNT(w.id) as word_count
        FROM Lessons l
        LEFT JOIN Words w ON l.id = w.lesson_id
        GROUP BY l.id, l.name, l.sort_order
        ORDER BY l.sort_order, l.id
    """)
    lesson_list = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("lessons.html", lessons=lesson_list)


@app.route("/lessons/add", methods=["POST"])
def add_lesson():
    name = request.form.get("name", "").strip()

    conn = get_connection()
    cursor = conn.cursor()
    if name:
        try:
            cursor.execute("""
                INSERT INTO Lessons (name, sort_order)
                VALUES (?, (SELECT ISNULL(MAX(sort_order), 0) + 1 FROM Lessons))
            """, (name,))
            conn.commit()
            flash(f"'{name}' 추가되었습니다!", "success")
        except Exception:
            flash("이미 존재하는 Lesson입니다.", "error")
    else:
        flash("Lesson 이름을 입력하세요.", "error")
    cursor.close()
    conn.close()

    return redirect(url_for("lessons"))


@app.route("/lessons/delete/<int:lesson_id>", methods=["POST"])
def delete_lesson(lesson_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Words SET lesson_id=NULL WHERE lesson_id=?", (lesson_id,))
    cursor.execute("DELETE FROM Lessons WHERE id=?", (lesson_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash("Lesson이 삭제되었습니다.", "success")
    return redirect(url_for("lessons"))


@app.route("/lessons/<int:lesson_id>/move/<direction>", methods=["POST"])
def move_lesson(lesson_id, direction):
    """Lesson 순서를 위/아래로 한 칸 이동 (인접 Lesson과 sort_order 교체)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, sort_order FROM Lessons ORDER BY sort_order, id")
    rows = cursor.fetchall()
    ids = [r[0] for r in rows]
    orders = [r[1] for r in rows]

    if lesson_id in ids:
        idx = ids.index(lesson_id)
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if 0 <= swap_idx < len(ids):
            cursor.execute("UPDATE Lessons SET sort_order=? WHERE id=?", (orders[swap_idx], ids[idx]))
            cursor.execute("UPDATE Lessons SET sort_order=? WHERE id=?", (orders[idx], ids[swap_idx]))
            conn.commit()

    cursor.close()
    conn.close()
    return redirect(url_for("lessons"))


@app.route("/lessons/<int:lesson_id>")
def lesson_detail(lesson_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM Lessons WHERE id=?", (lesson_id,))
    lesson = cursor.fetchone()

    if not lesson:
        cursor.close()
        conn.close()
        flash("Lesson을 찾을 수 없습니다.", "error")
        return redirect(url_for("lessons"))

    cursor.execute("""
        SELECT id, word, meaning, example_sentence
        FROM Words WHERE lesson_id=?
        ORDER BY created_at DESC
    """, (lesson_id,))
    words = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("lesson_detail.html", lesson=lesson, words=words)


init_db()

if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "1") == "1"
    port = int(os.getenv("PORT", "5000"))
    app.run(debug=debug_mode, host="0.0.0.0", port=port)
