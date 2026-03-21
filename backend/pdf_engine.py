import os
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

#  DOSYA/KLASÖR AYARLARI

BASE_DIR = os.path.dirname(__file__)               # .../backend
OUT_DIR = os.path.join(BASE_DIR, "outputs")        # .../backend/outputs
os.makedirs(OUT_DIR, exist_ok=True)


#  FONT (TÜRKÇE KARAKTERLER İÇİN)
#  backend/DejaVuSans.ttf  veya backend/fonts/DejaVuSans.ttf

FONT_PATH = os.path.join(BASE_DIR, "DejaVuSans.ttf")
if not os.path.exists(FONT_PATH):
    FONT_PATH = os.path.join(BASE_DIR, "fonts", "DejaVuSans.ttf")

DEFAULT_FONT = "Helvetica"
if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("DejaVu", FONT_PATH))
    DEFAULT_FONT = "DejaVu"


#  YARDIMCI: UZUN METNİ SATIR SATIR YAZDIRMA (WRAP)

def draw_wrapped_text(c, text, x, y, max_width, line_height, font_name=None, font_size=11):
    if font_name is None:
        font_name = DEFAULT_FONT

    c.setFont(font_name, font_size)

    words = str(text).split()
    line = ""

    for w in words:
        test = (line + " " + w).strip()
        if stringWidth(test, font_name, font_size) <= max_width:
            line = test
        else:
            if line:
                c.drawString(x, y, line)
                y -= line_height
            line = w

    if line:
        c.drawString(x, y, line)
        y -= line_height

    return y


#  YARDIMCI: GÖRSELİ SAYFAYA SIĞDIRARAK ÇİZ

def draw_question_image(c, image_path, x, y, max_width, max_height=220, gap_after=14):
    """
    Görseli sayfaya sığacak şekilde çizer.
    Geriye yeni y değerini döndürür.
    """
    if not image_path or not os.path.exists(image_path):
        return y

    try:
        img = ImageReader(image_path)
        iw, ih = img.getSize()

        scale = min(max_width / iw, max_height / ih, 1.0)
        w = iw * scale
        h = ih * scale

        # yer aç
        y = y - h
        c.drawImage(img, x, y, width=w, height=h, preserveAspectRatio=True, mask="auto")

        y -= gap_after
        return y
    except Exception:
        return y


#  SINAV PDF

def create_exam_pdf(questions, exam_code=None, image_path=None):
    """
    Sorulardan sınav PDF'i üretir.
    questions: [str]
    exam_code: "UNIT-XXXX"
    image_path: verilirse aynı görseli HER SORUDAN ÖNCE basar
    """
    filename = f"sinav_{exam_code}.pdf" if exam_code else "exam_output.pdf"
    pdf_path = os.path.join(OUT_DIR, filename)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    left = 50
    right = 50
    max_width = width - left - right

    y = height - 50

    # Başlık
    y = draw_wrapped_text(
        c,
        f"UniTest - Sınav | Sınav Kodu: {exam_code}" if exam_code else "UniTest - Sınav",
        left, y, max_width, 20, DEFAULT_FONT, 16
    )
    y -= 6

    # Tarih
    c.setFont(DEFAULT_FONT, 9)
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    c.drawString(left, y, f"Tarih: {now}")
    y -= 25

    c.setFont(DEFAULT_FONT, 11)

    for i, q in enumerate(questions, 1):

        # yeni sayfa kontrol
        if y < 140:
            c.showPage()
            y = height - 50
            c.setFont(DEFAULT_FONT, 11)

        # her sorudan önce görsel bas
        if image_path:
            if y < 320:
                c.showPage()
                y = height - 50
                c.setFont(DEFAULT_FONT, 11)
            y = draw_question_image(c, image_path, left, y, max_width, max_height=220)

        # soru metni
        y = draw_wrapped_text(c, f"{i}) {q}", left, y, max_width, 16, DEFAULT_FONT, 11)
        y -= 10

    c.save()
    return pdf_path


#  CEVAP ANAHTARI PDF

def create_answer_key_pdf(
    questions,
    answers,
    exam_code=None,
    question_image_path=None,       # sorunun görseli (istersen her sorudan önce bas)
    solution_text=None,             # öğretmenin çözüm metni
    solution_image_path=None        # öğretmenin çözüm görseli
):
    """
    Sorular ve cevaplardan cevap anahtarı PDF'i üretir.

    - question_image_path: her sorudan önce soru görselini basmak için (opsiyonel)
    - solution_text / solution_image_path: başlık kısmının altında öğretmen çözümünü göstermek için
    """
    filename = f"answer_{exam_code}.pdf" if exam_code else "answer_key.pdf"
    pdf_path = os.path.join(OUT_DIR, filename)

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    left = 50
    right = 50
    max_width = width - left - right

    y = height - 50

    # Başlık
    y = draw_wrapped_text(
        c,
        f"UniTest - Cevap Anahtarı | Sınav Kodu: {exam_code}" if exam_code else "UniTest - Cevap Anahtarı",
        left, y, max_width, 20, DEFAULT_FONT, 16
    )
    y -= 6

    # Tarih
    c.setFont(DEFAULT_FONT, 9)
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    c.drawString(left, y, f"Oluşturma Tarihi: {now}")
    y -= 20

    #Öğretmen çözümü (sayfanın başında)
    c.setFont(DEFAULT_FONT, 11)

    if solution_text:
        y -= 6
        y = draw_wrapped_text(c, "Öğretmen Çözüm Metni:", left, y, max_width, 16, DEFAULT_FONT, 11)
        y = draw_wrapped_text(c, solution_text, left, y, max_width, 15, DEFAULT_FONT, 10)
        y -= 6

    if solution_image_path and os.path.exists(solution_image_path):
        # yer yoksa sayfa
        if y < 320:
            c.showPage()
            y = height - 50
            c.setFont(DEFAULT_FONT, 11)
        y = draw_wrapped_text(c, "Öğretmen Çözüm Görseli:", left, y, max_width, 16, DEFAULT_FONT, 11)
        y = draw_question_image(c, solution_image_path, left, y, max_width, max_height=260)
        y -= 6

    # ayraç
    y -= 8
    c.setFont(DEFAULT_FONT, 11)

    # Sorular + cevaplar
    for i, (q, ans) in enumerate(zip(questions, answers), 1):

        if y < 160:
            c.showPage()
            y = height - 50
            c.setFont(DEFAULT_FONT, 11)

        # (opsiyonel) her sorudan önce soru görseli
        if question_image_path:
            if y < 320:
                c.showPage()
                y = height - 50
                c.setFont(DEFAULT_FONT, 11)
            y = draw_question_image(c, question_image_path, left, y, max_width, max_height=220)

        y = draw_wrapped_text(c, f"{i}) {q}", left, y, max_width, 16, DEFAULT_FONT, 11)
        y = draw_wrapped_text(c, f"Cevap: {ans}", left + 20, y, max_width - 20, 16, DEFAULT_FONT, 11)
        y -= 12

    c.save()
    return pdf_path
