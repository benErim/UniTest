import os
import sqlite3
import datetime
import random
import string

# database.db yolunu dosyanın yanına ayarla
DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Tabloları yoksa oluştur."""
    with get_connection() as conn:
        c = conn.cursor()

        # Orijinal soru tablosu
        c.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        # Sınavlar tablosu
        c.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """)

        # Her sınava ait varyasyon sorular
        c.execute("""
        CREATE TABLE IF NOT EXISTS exam_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            order_no INTEGER NOT NULL,
            variation_text TEXT NOT NULL,
            FOREIGN KEY (exam_id) REFERENCES exams(id)
        )
        """)

                # Bundle tablosu (birden fazla sınavı tek kod altında toplamak için)
        c.execute("""
        CREATE TABLE IF NOT EXISTS bundles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bundle_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """)

                # Eski veritabanlarında exams tablosuna bundle_id ekle (varsa hata vermesin)
        try:
            c.execute("ALTER TABLE exams ADD COLUMN bundle_id INTEGER")
        except Exception:
            pass

        conn.commit()


def generate_exam_code(length: int = 6) -> str:
    """Rastgele sınav kodu üret, ör: UNIT-AB3K9Q"""
    letters = string.ascii_uppercase + string.digits
    token = "".join(random.choice(letters) for _ in range(length))
    return f"UNIT-{token}"


def save_exam(original_question: str, variations: list[str], bundle_id: int | None = None):
    """
    Orijinal soruyu ve üretilen varyasyonları veritabanına kaydet.
    Geriye (exam_id, exam_code) döner.
    """
    now = datetime.datetime.utcnow().isoformat()

    with get_connection() as conn:
        c = conn.cursor()

        # Orijinal soru kaydı
        c.execute(
            "INSERT INTO questions (original_text, created_at) VALUES (?, ?)",
            (original_question, now),
        )
        # question_id = c.lastrowid  # gerekirse kullanırız

        # Sınav kaydı
        exam_code = generate_exam_code()
        c.execute(
            "INSERT INTO exams (exam_code, created_at, bundle_id) VALUES (?, ?, ?)",
            (exam_code, now, bundle_id),
        )
        exam_id = c.lastrowid

        # Sınav soruları
        for i, v in enumerate(variations, start=1):
            c.execute(
                """
                INSERT INTO exam_questions (exam_id, order_no, variation_text)
                VALUES (?, ?, ?)
                """,
                (exam_id, i, v),
            )

        conn.commit()

    return exam_id, exam_code


def list_questions(limit: int = 50):
    """En son eklenen soruları listele."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, original_text, created_at
            FROM questions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = c.fetchall()
    return rows


def get_question_by_id(question_id: int):
    """ID'ye göre tek bir orijinal soruyu getir."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, original_text, created_at FROM questions WHERE id = ?",
            (question_id,),
        )
        row = c.fetchone()
    return row

def get_exam_by_code(exam_code: str):
    """Sınav koduna göre sınav kaydını getir."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, exam_code, created_at FROM exams WHERE exam_code = ?",
            (exam_code,),
        )
        row = c.fetchone()
    return row


def get_exam_questions(exam_id: int):
    """Bir sınava ait tüm varyasyon soruları (sırasıyla)"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, exam_id, order_no, variation_text
            FROM exam_questions
            WHERE exam_id = ?
            ORDER BY order_no ASC
            """,
            (exam_id,),
        )
        rows = c.fetchall()
    return rows


def list_exams(limit=50):
    """Son oluşturulan sınavları listeler."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT e.id,
                   e.exam_code,
                   e.created_at,
                   COUNT(eq.id) AS question_count
            FROM exams e
            LEFT JOIN exam_questions eq ON eq.exam_id = e.id
            GROUP BY e.id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = c.fetchall()
    return rows

def get_exam_by_id(exam_id: int):
    """ID ile tek bir sınavı döndürür (orijinal_text almıyoruz artık)."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, exam_code, created_at FROM exams WHERE id = ?",
            (exam_id,),
        )
        row = c.fetchone()
    return row


def get_exam_questions(exam_id: int):
    """Bir sınava ait tüm soru varyasyonlarını sırayla getirir."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, exam_id, order_no, variation_text
            FROM exam_questions
            WHERE exam_id = ?
            ORDER BY order_no ASC
            """,
            (exam_id,),
        )
        rows = c.fetchall()
    return rows
import uuid
import datetime


# Yeni bundle oluşturur
def create_bundle():
    bundle_code = f"BND-{uuid.uuid4().hex[:6].upper()}"
    now = datetime.datetime.utcnow().isoformat()

    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO bundles (bundle_code, created_at) VALUES (?, ?)",
            (bundle_code, now)
        )
        bundle_id = c.lastrowid
        conn.commit()

    return bundle_id, bundle_code


# Bundle koduna göre bundle getirir
def get_bundle_by_code(bundle_code: str):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, bundle_code, created_at FROM bundles WHERE bundle_code=?",
            (bundle_code,)
        )
        row = c.fetchone()
        if not row:
            return None
        return dict(row)


# Bundle içindeki tüm sınavları getirir
def get_exams_by_bundle_id(bundle_id: int):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "SELECT id, exam_code, created_at FROM exams WHERE bundle_id=? ORDER BY id ASC",
            (bundle_id,)
        )
        rows = c.fetchall()
        return [dict(r) for r in rows]


