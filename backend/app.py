import os
import sqlite3
import uuid
import zipfile
import json
from werkzeug.utils import secure_filename

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

# Çıktı klasörü kontrolü
os.makedirs(os.path.join(os.path.dirname(__file__), "outputs"), exist_ok=True)

from question_parser import extract_numbers
from ai_engine import (
    generate_variations,
    solve_question,
    extract_question_from_image,
    extract_questions_from_exam_image,
)
from pdf_engine import create_exam_pdf, create_answer_key_pdf
from models import (
    init_db,
    save_exam,
    list_questions,
    get_question_by_id,
    get_exam_by_code,
    get_exam_questions,
    list_exams,
    get_exam_by_id,
    create_bundle,
    get_bundle_by_code,
    get_exams_by_bundle_id,
)

# ---------- AYARLAR ----------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app)
init_db()

# ---------- UI ROUTE’LARI ----------
@app.route("/")
def ui_index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/bank")
def ui_bank():
    return send_from_directory(FRONTEND_DIR, "bank.html")

@app.route("/exams")
def ui_exams():
    return send_from_directory(FRONTEND_DIR, "exams.html")

@app.route("/answers")
def ui_answers():
    return send_from_directory(FRONTEND_DIR, "answers.html")

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"message": "UniTest Backend Çalışıyor!"})

# ---------- SORU ALMA (ANALİZ) ----------
@app.route("/api/upload_question", methods=["POST"])
def upload_question():
    data = request.json or {}
    question_text = data.get("question", "")
    numbers = extract_numbers(question_text)
    return jsonify({"status": "ok", "numbers_found": numbers})

# ---------- VARYASYON VE PDF ÜRETİMİ ----------
@app.route("/api/generate", methods=["POST"])
def generate_exam():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or request.form.get("question") or "").strip()
    count_raw = data.get("count") or request.form.get("count", 1)

    try:
        count = int(count_raw)
    except (TypeError, ValueError):
        count = 1

    file = request.files.get("image")
    image_path = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        image_path = os.path.join(UPLOAD_DIR, filename)
        file.save(image_path)

    base_question = question
    if not base_question and image_path:
        base_question = extract_question_from_image(image_path)

    if not base_question:
        return jsonify({"status": "error", "message": "Soru metni veya görsel bulunamadı."}), 400

    variations = generate_variations(question_text=question, count=count, image_path=image_path)
    if not variations:
        return "Varyasyon üretilemedi.", 400

    pdf_path = create_exam_pdf(variations)
    return jsonify({"status": "ok", "questions": variations, "pdf": pdf_path})

@app.route("/download_exam", methods=["POST"])
def download_exam():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or request.form.get("question") or "").strip()
    count_raw = data.get("count") or request.form.get("count", 1)

    try:
        count = int(count_raw)
    except (TypeError, ValueError):
        count = 1

    file = request.files.get("image")
    image_path = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        image_path = os.path.join(UPLOAD_DIR, filename)
        file.save(image_path)

    base_question = question
    if not base_question and image_path:
        base_question = extract_question_from_image(image_path)

    if not base_question:
        return "Soru metni veya görsel yüklenmedi.", 400

    variations = generate_variations(question_text=question, count=count, image_path=image_path)
    exam_id, exam_code = save_exam(base_question, variations)
    pdf_path = create_exam_pdf(variations, exam_code=exam_code, image_path=image_path)

    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True, download_name=f"sinav_{exam_code}.pdf")

@app.route("/download_exam_bundle", methods=["POST"])
def download_exam_bundle():
    count_raw = request.form.get("student_count", 1)
    try:
        K = int(count_raw)
    except (TypeError, ValueError):
        K = 1
    K = max(1, min(K, 50))

    exam_text = (request.form.get("exam_text") or "").strip()
    file = request.files.get("exam_file")
    image_path = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        image_path = os.path.join(UPLOAD_DIR, filename)
        file.save(image_path)

    if (not exam_text) and (not image_path):
        return "Soru metni veya görsel yüklenmedi.", 400

    bundle_id, bundle_code = create_bundle()

    if exam_text:
        base_questions = [line.strip() for line in exam_text.split("\n") if line.strip()]
    else:
        base_questions = extract_questions_from_exam_image(image_path)

    if not base_questions:
        return "Soru çıkarılamadı.", 400

    variants_matrix = []
    for q in base_questions:
        variants = generate_variations(question_text=q, count=K, image_path=None)
        if len(variants) < K:
            variants += [q] * (K - len(variants))
        variants_matrix.append(variants)

    zip_name = f"sinavlar_{uuid.uuid4().hex[:8]}.zip"
    zip_path = os.path.join(os.path.dirname(__file__), "outputs", zip_name)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for k in range(K):
            version_questions = [variants_matrix[i][k] for i in range(len(base_questions))]
            original_payload = json.dumps(base_questions, ensure_ascii=False)
            exam_id, exam_code = save_exam(original_payload, version_questions, bundle_id=bundle_id)
            pdf_path = create_exam_pdf(version_questions, exam_code=exam_code, image_path=None)
            zf.write(pdf_path, arcname=f"exams/sinav_{exam_code}.pdf")
        zf.writestr("BUNDLE_CODE.txt", bundle_code)

    return send_file(zip_path, mimetype="application/zip", as_attachment=True, download_name="sinavlar.zip")

# ---------- CEVAP ANAHTARI ÜRETİMİ ----------

@app.route("/download_answer_keys_bundle", methods=["POST"])
def download_answer_keys_bundle():
    bundle_code = (request.form.get("bundle_code") or "").strip()
    if not bundle_code:
        return "Bundle kodu girilmedi.", 400

    # Formdan gelen dinamik puanı al
    u_point = request.form.get("total_point", 10)
    try:
        u_point = int(u_point)
    except:
        u_point = 10

    bundle = get_bundle_by_code(bundle_code)
    if not bundle:
        return "Bundle bulunamadı.", 404

    exams = get_exams_by_bundle_id(bundle["id"])
    if not exams:
        return "Bu bundle içinde sınav yok.", 404

    solution_text = (request.form.get("solution_text") or "").strip()
    solution_file = request.files.get("solution_image")
    solution_image_path = None
    if solution_file and solution_file.filename:
        filename = secure_filename(solution_file.filename)
        solution_image_path = os.path.join(UPLOAD_DIR, filename)
        solution_file.save(solution_image_path)

    out_dir = os.path.join(os.path.dirname(__file__), "outputs")
    os.makedirs(out_dir, exist_ok=True)
    zip_name = f"cevaplar_{bundle_code}.zip"
    zip_path = os.path.join(out_dir, zip_name)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for exam in exams:
            rows = get_exam_questions(exam["id"])
            questions = [r["variation_text"] for r in rows]
            answers = []
            for q in questions:
                # total_point parametresi gönderiliyor
                ans = solve_question(
                    question_text=q,
                    teacher_solution_text=solution_text,
                    teacher_solution_image_path=solution_image_path,
                    total_point=u_point
                )
                answers.append(ans)

            pdf_path = create_answer_key_pdf(
                questions, answers, exam_code=exam["exam_code"],
                question_image_path=None, solution_text=solution_text,
                solution_image_path=solution_image_path
            )
            zf.write(pdf_path, arcname=f"answers/cevap_{exam['exam_code']}.pdf")
        zf.writestr("BUNDLE_CODE.txt", bundle_code)

    return send_file(zip_path, mimetype="application/zip", as_attachment=True, download_name="cevap_anahtarlari.zip")

@app.route("/download_answer_key", methods=["POST"])
def download_answer_key():
    data = request.get_json(silent=True) or {}
    exam_code = (data.get("exam_code") or request.form.get("exam_code") or "").strip()
    
    # Formdan gelen dinamik puanı al
    u_point = request.form.get("total_point", 10)
    try:
        u_point = int(u_point)
    except:
        u_point = 10

    if not exam_code:
        return "Sınav kodu belirtilmedi.", 400

    exam = get_exam_by_code(exam_code)
    if exam is None:
        return f"{exam_code} kodlu sınav bulunamadı.", 404

    rows = get_exam_questions(exam["id"])
    questions = [r["variation_text"] for r in rows]

    solution_text = (data.get("solution_text") or request.form.get("solution_text") or "").strip()
    solution_file = request.files.get("solution_image")
    solution_image_path = None
    if solution_file and solution_file.filename:
        filename = secure_filename(solution_file.filename)
        solution_image_path = os.path.join(UPLOAD_DIR, filename)
        solution_file.save(solution_image_path)

    question_file = request.files.get("question_image")
    question_image_path = None
    if question_file and question_file.filename:
        filename = secure_filename(question_file.filename)
        question_image_path = os.path.join(UPLOAD_DIR, filename)
        question_file.save(question_image_path)

    answers = []
    for q in questions:
        # total_point parametresi gönderiliyor
        ans = solve_question(
            question_text=q,
            teacher_solution_text=solution_text,
            teacher_solution_image_path=solution_image_path,
            total_point=u_point
        )
        answers.append(ans)

    pdf_path = create_answer_key_pdf(
        questions, answers, exam_code=exam_code,
        question_image_path=question_image_path,
        solution_text=solution_text,
        solution_image_path=solution_image_path
    )

    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True, download_name=f"cevap_{exam_code}.pdf")

# ---------- SORU BANKASI VE DİĞER API’LAR ----------
@app.route("/api/questions", methods=["GET"])
def api_list_questions():
    rows = list_questions(limit=100)
    result = [{"id": r["id"], "original_text": r["original_text"], "created_at": r["created_at"]} for r in rows]
    return jsonify(result)

@app.route("/api/exams", methods=["GET"])
def api_list_exams():
    rows = list_exams(limit=100)
    result = [{"id": r["id"], "exam_code": r["exam_code"], "created_at": r["created_at"], "question_count": r["question_count"]} for r in rows]
    return jsonify(result)

@app.route("/download_exam_from_question", methods=["POST"])
def download_exam_from_question():
    data = request.get_json(silent=True) or {}
    qid_raw = data.get("question_id") or request.form.get("question_id")
    count_raw = data.get("count") or request.form.get("count", 1)
    try:
        question_id = int(qid_raw)
        count = int(count_raw)
    except:
        return "Geçersiz parametre", 400

    row = get_question_by_id(question_id)
    if not row: return "Soru bulunamadı.", 404

    variations = generate_variations(question_text=row["original_text"], count=count, image_path=None)
    exam_id, exam_code = save_exam(row["original_text"], variations)
    pdf_path = create_exam_pdf(variations, exam_code=exam_code)
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True, download_name=f"sinav_{exam_code}.pdf")

@app.route("/download_existing_exam", methods=["POST"])
def download_existing_exam():
    data = request.get_json(silent=True) or {}
    exam_id_raw = data.get("exam_id") or request.form.get("exam_id")
    try:
        exam_id = int(exam_id_raw)
    except:
        return "Geçersiz exam_id", 400

    exam = get_exam_by_id(exam_id)
    if not exam: return "Sınav bulunamadı.", 404

    rows = get_exam_questions(exam_id)
    questions = [r["variation_text"] for r in rows]
    pdf_path = create_exam_pdf(questions, exam_code=exam["exam_code"])
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True, download_name=f"sinav_{exam['exam_code']}.pdf")

@app.route("/regenerate_exam", methods=["POST"])
def regenerate_exam():
    data = request.get_json(silent=True) or {}
    exam_id_raw = data.get("exam_id") or request.form.get("exam_id")
    try:
        exam_id = int(exam_id_raw)
    except:
        return "Geçersiz exam_id", 400

    exam = get_exam_by_id(exam_id)
    if not exam: return "Sınav bulunamadı.", 404

    old_questions = get_exam_questions(exam_id)
    base_question = old_questions[0]["variation_text"]
    variations = generate_variations(question_text=base_question, count=len(old_questions), image_path=None)
    new_exam_id, new_exam_code = save_exam(base_question, variations)
    pdf_path = create_exam_pdf(variations, exam_code=new_exam_code)
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True, download_name=f"sinav_{new_exam_code}.pdf")

if __name__ == "__main__":
    app.run(debug=True)