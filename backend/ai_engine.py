import os
import re
import json
import base64
from openai import OpenAI
from dotenv import load_dotenv
import json, re, ast
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# IMAGE -> DATA URL
def _image_to_data_url(image_path: str) -> str:
    ext = os.path.splitext(image_path)[1].lower().replace(".", "")
    if ext not in ["png", "jpg", "jpeg", "webp"]:
        ext = "png"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    mime = "image/jpeg" if ext in ["jpg", "jpeg"] else f"image/{ext}"
    return f"data:{mime};base64,{b64}"


# VISION: image -> question text
def extract_question_from_image(image_path: str) -> str:
    data_url = _image_to_data_url(image_path)
    prompt = (
        "Bu görseldeki soruyu Türkçe olarak aynen yazıya dök. "
        "Sadece soru metnini ver, ekstra açıklama yazma."
    )

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

def extract_questions_from_exam_image(image_path: str) -> list[str]:
    """
    Sınav kağıdı görselinden tüm soruları sırayla JSON liste olarak çıkarır.
    """
    data_url = _image_to_data_url(image_path)

    prompt = """
Bu görsel bir sınav kağıdı. İçindeki TÜM soruları sırayla çıkar.

KURALLAR:
- Çıktı SADECE JSON array olsun.
- Her eleman bir soru metni olsun.
- Ek açıklama yazma.

ÖRNEK:
[
  "1) ...?",
  "2) ...?"
]
""".strip()

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        temperature=0.2,
    )

    raw = resp.choices[0].message.content.strip()
    items = _safe_json_list(raw)

    cleaned = []
    if isinstance(items, list):
        for s in items:
            if isinstance(s, str) and s.strip():
                cleaned.append(s.strip())
    return cleaned



# Helpers
def _extract_numbers(text: str):
    nums = re.findall(r"\d+(?:[.,]\d+)?", text)
    return [n.replace(",", ".") for n in nums]




def _safe_json_list(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)

    try:
        return json.loads(t)
    except json.JSONDecodeError:
        # 2. deneme: Python list gibi döndüyse
        try:
            return ast.literal_eval(t)
        except Exception:
            # 3. deneme: tüm backslash'leri escape et
            t2 = t.replace("\\", "\\\\")
            return json.loads(t2)


def generate_variations(question_text: str, count: int, image_path: str = None) -> list[str]:
    """
    Tek API çağrısıyla `count` adet varyasyon üretmeyi dener.
    Yetmezse otomatik 2-3 küçük ek çağrı ile tamamlar.
    Yine de tamamlanamazsa crash etmez, elindeki kadarını döndürür.
    """
    base_question = (question_text or "").strip()

    if not base_question and image_path:
        base_question = extract_question_from_image(image_path)

    if not base_question:
        raise ValueError("Ne soru metni var ne de görselden soru çıkarılabildi.")

    def _dedupe_pack(items, cleaned, seen_text, seen_num_sets, target_count):
        for s in items:
            if not isinstance(s, str):
                continue
            q = s.strip().strip('"').strip()
            if not q:
                continue

            nums = tuple(_extract_numbers(q))
            if q in seen_text:
                continue

            # Aynı sayı setiyle birebir tekrarları ele
            if nums and nums in seen_num_sets:
                continue

            seen_text.add(q)
            if nums:
                seen_num_sets.add(nums)
            cleaned.append(q)

            if len(cleaned) >= target_count:
                break

    cleaned = []
    seen_text = set()
    seen_num_sets = set()

# --------------- İlk ana çağrı (KESİN VERİ KORUMA) ---------------
    prompt = f"""
Sana verilen sorunun hikayesini, teknik detaylarını ve mantıksal kurgusunu %100 koruyarak sadece sayısal değerlerini değiştir. 

HATA ÖRNEĞİ (BUNU YAPMA):
Orijinal Soru: "15 kişinin katıldığı bir yarışta ilk 5 kişi madalya alıyor. Ali'nin madalya alma olasılığı nedir?"
Hatalı Çıktı: "Ali'nin madalya alma olasılığı nedir?" (HATA: Tüm sayısal veriler ve hikaye silinmiş!)

DOĞRU ÖRNEK (BUNU YAP):
Orijinal Soru: "15 kişinin katıldığı bir yarışta ilk 5 kişi madalya alıyor. Ali'nin madalya alma olasılığı nedir?"
Doğru Çıktı: "20 kişinin katıldığı bir yarışta ilk 4 kişi madalya alıyor. Ali'nin madalya alma olasılığı nedir?" (BAŞARI: Hikaye ve sayısal yapı korundu, sadece rakamlar değişti.)

KURALLAR:
1. Soru içindeki "X kişinin katıldığı", "Y/Z olasılığı", "N kez atılıyor", "kart sayısı" gibi TÜM sayısal ve tanımlayıcı verileri yeni sayılarla mutlaka metin içinde belirt.
2. Metni asla kısaltma, özetleme veya sadece soru kökünü ("nedir?") bırakarak bitirme. Orijinal metin kaç cümleyse, senin çıktın da o kadar detaylı olmalı.
3. Fizik, Kimya veya Matematik fark etmeksizin tüm teknik öncüller yeni soruda yer almalıdır.
4. Çıktı SADECE JSON array (liste) olsun.

ORİJİNAL SORU:
{base_question}
""".strip()

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )

    raw = resp.choices[0].message.content.strip()
    items = _safe_json_list(raw)
    _dedupe_pack(items, cleaned, seen_text, seen_num_sets, count)

    # --------------- Eksik kaldıysa: 2-3 kez tamamla ---------------
    max_attempts = 3
    attempt = 0

    while len(cleaned) < count and attempt < max_attempts:
        attempt += 1
        missing = count - len(cleaned)

        used_nums = sorted({n for q in cleaned for n in _extract_numbers(q)})
        prev = cleaned[-3:]  # son 3'ü ver, yönlendirme için yeter

        prompt2 = f"""
Aşağıdaki sorunun sadece sayısal değerlerini değiştirerek {missing} adet EK soru üret.

KURALLAR:
- SADECE sayıları değiştir.
- Aşağıdaki "KULLANILMIŞ SAYILAR" içindeki sayıları KULLANMA.
- Aşağıdaki "ÖNCEKİ SORULAR" ile birebir aynı cümleyi yazma.
- JSON array döndür, başka bir şey yazma.

ORİJİNAL SORU:
{base_question}

KULLANILMIŞ SAYILAR (KULLANMA):
{used_nums}

ÖNCEKİ SORULAR:
{prev}
""".strip()

        resp2 = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt2}],
            temperature=0.95,
        )

        extra_raw = resp2.choices[0].message.content.strip()
        extra_items = _safe_json_list(extra_raw)
        _dedupe_pack(extra_items, cleaned, seen_text, seen_num_sets, count)

    # --------------- Hâlâ eksikse crash etme ---------------
    return cleaned


def generate_variation(question_text, image_path=None, used_numbers=None, previous_variations=None):
    # Eski kodlar bozulmasın diye tek varyasyon döndürür
    return generate_variations(question_text, 1, image_path=image_path)[0]


# SOLVER (text or image, Dinamik Puanlı ve Aşamalı)
def solve_question(
        question_text: str,
        image_path: str = None,
        teacher_solution_text: str = "",
        teacher_solution_image_path: str = None,
        total_point: int = 10  # Kullanıcının belirlediği toplam puan
) -> str:
    """
    Hibrit çözüm:
    - Çözümü aşamalara böler ve toplam puana göre dağıtır.
    - Her adımda puan yazılmasını garanti altına alır.
    """

    # --- SORU METNİ ---
    q = (question_text or "").strip()

    if not q and image_path:
        q = extract_question_from_image(image_path)

    if not q:
        raise ValueError("Çözülecek soru bulunamadı.")

    # --- ÖĞRETMEN ÇÖZÜM METNİ ---
    teacher_text = (teacher_solution_text or "").strip()

    # --- PROMPT OLUŞTUR (GÜÇLENDİRİLMİŞ TALİMATLAR) ---
    base_prompt = f"""
Aşağıdaki soruyu ADIM ADIM çöz.

PUANLAMA VE FORMAT KURALLARI (KRİTİK):
1. Sorunun toplam değeri tam olarak {total_point} puandır.
2. Çözümü mantıklı işlem aşamalarına böl (Örn: 3, 4 veya 5 aşama).
3. İSTİSNASIZ HER ADIMIN sonunda parantez içinde "(X. aşama, Y puan)" bilgisini yazmalısın. 
   Puan yazılmayan tek bir çözüm adımı bile kalmamalıdır.
4. Tüm aşamaların puanları toplamı tam olarak {total_point} olmalıdır.
5. Eğer öğretmen çözümü verilmişse, o yöntemi referans alarak bu aşamaları oluştur.
6. En son satırı "Sonuç: ..." şeklinde bitir.

Soru:
{q}
""".strip()

    messages = []

    if teacher_text:
        base_prompt += f"\n\nÖĞRETMENİN ÇÖZÜM YÖNTEMİ:\n{teacher_text}"
    
    messages.append({
        "role": "user",
        "content": base_prompt
    })

    if teacher_solution_image_path:
        data_url = _image_to_data_url(teacher_solution_image_path)
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "Görseldeki öğretmen çözüm yöntemini kullanarak yukarıdaki puanlı aşama kuralına göre soruyu çöz."},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]
        })

    # --- API ÇAĞRISI ---
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.1, # Daha stabil ve kuralcı çıktı için düşürdük
    )

    return resp.choices[0].message.content.strip()

def extract_questions_from_exam_image(image_path: str) -> list[str]:
    """
    Sınav kağıdı görselinden tüm soruları sırayla JSON liste olarak çıkarır.
    """
    data_url = _image_to_data_url(image_path)
    prompt = """
Bu görsel bir sınav kağıdı. İçindeki TÜM soruları sırayla çıkar.

KURALLAR:
- Çıktı SADECE JSON array olsun.
- Her eleman bir soru metni olsun.
- Soru numaralarını (1), 2., vb) metnin başında bırakabilirsin ama tutarlı ol.
- Ek açıklama yazma.

ÖRNEK:
[
  "1) ...?",
  "2) ...?"
]
""".strip()

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        temperature=0.2,
    )

    raw = resp.choices[0].message.content.strip()
    items = _safe_json_list(raw)

    # temizlik
    cleaned = []
    for s in items if isinstance(items, list) else []:
        if isinstance(s, str) and s.strip():
            cleaned.append(s.strip())
    return cleaned
