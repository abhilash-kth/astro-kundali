from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from datetime import datetime, timedelta
import pytz
import swisseph as swe
import requests
import json
import logging
import re
import io
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
import base64
from PIL import Image

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.lib.units import inch
import os
from reportlab.lib.colors import HexColor
from fastapi.middleware.cors import CORSMiddleware


ORANGE = HexColor("#F57C00")   # Hindu orange
LIGHT_ORANGE = HexColor("#FFF3E0")
import uuid
from fastapi.staticfiles import StaticFiles


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("muhurat")

swe.set_ephe_path(r"D:\python\astro-py\ephe")

OPENAI_API_KEY = "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"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o"

IST = pytz.timezone("Asia/Kolkata")

app = FastAPI(title="Generic Muhurat Range API")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -------------------------------------------------
# CONSTANTS
# -------------------------------------------------
NAKSHATRA_NAMES = [
    "Ashvini","Bharani","Krittika","Rohini","Mrigashirsha","Ardra",
    "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni",
    "Uttara Phalguni","Hasta","Chitra","Swati","Vishakha","Anuradha",
    "Jyeshta","Mula","Purva Ashadha","Uttara Ashadha","Shravana",
    "Dhanishta","Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati"
]

# -------------------------------------------------
# EVENT BASED RULES (GENERIC ENGINE)
# -------------------------------------------------
EVENT_RULES = {
    "marriage": {
        "allow": {"Rohini","Mrigashirsha","Magha","Uttara Phalguni",
                  "Hasta","Swati","Anuradha","Uttara Ashadha",
                  "Uttara Bhadrapada","Revati"},
        "block": {"Bharani","Ardra","Ashlesha","Jyeshta","Mula"}
    },
    "griha_pravesh": {
        "allow": {"Rohini","Mrigashirsha","Uttara Phalguni",
                  "Hasta","Anuradha","Revati"},
        "block": {"Ardra","Ashlesha","Jyeshta"}
    },
    "business": {
        "allow": set(NAKSHATRA_NAMES),
        "block": {"Bharani","Ashlesha"}
    },
    "mundan": {
        "allow": {"Ashvini","Punarvasu","Pushya","Hasta","Swati","Anuradha","Shravana"},
        "block": {"Bharani","Krittika","Ardra","Ashlesha","Jyeshta","Mula"}
    },
    "naamkaran": {
        "allow": {"Rohini","Mrigashirsha","Hasta","Swati","Anuradha","Shravana","Revati"},
        "block": {"Bharani","Ardra","Ashlesha","Jyeshta"}
    },
    "upanayan": {
        "allow": {"Ashvini","Rohini","Hasta","Swati","Anuradha"},
        "block": {"Bharani","Ardra","Ashlesha","Jyeshta"}
    },
    "satyanarayan": {
        "allow": {"Pushya","Punarvasu","Ashvini","Hasta","Swati"},
        "block": {"Ashlesha","Mula"}
    },
    "engagement": {
        "allow": {"Rohini","Mrigashirsha","Magha","Uttara Phalguni","Swati","Anuradha"},
        "block": {"Bharani","Ardra","Ashlesha","Jyeshta"}
    },
    # "general": {
    #     "allow": set(NAKSHATRA_NAMES),
    #     "block": set()
    # }
}

ABHUJ_MUHURAT_DATES = {
    "Akshaya Tritiya": "2025-04-30",
    "Vasant Panchami": "2025-02-02",
    "Phulera Dooj": "2025-03-01",
    "DevUthani Ekadashi": "2025-11-01",
    "Vijayadashami": "2025-10-02"
}

KHARMAAS_RANGES = [
    ("2025-12-15", "2026-01-15")
]

def approx_tokens(text: str) -> int:
    return len(text)

MAX_MUHURATS = 20

def is_kharmaas(dt):
    for start, end in KHARMAAS_RANGES:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        if s <= dt.date() <= e:
            return True
    return False

# -------------------------------------------------
# ASTRO HELPERS
# -------------------------------------------------
def dt_to_jd(dt):
    dt_utc = dt.astimezone(pytz.UTC)
    t = dt_utc.hour + dt_utc.minute / 60
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, t)

def get_moon_longitude(dt):
    jd = dt_to_jd(dt)
    res = swe.calc_ut(jd, swe.MOON)
    return res[0][0] % 360

def get_nakshatra(moon_lon):
    idx = int(moon_lon // (360 / 27))
    return NAKSHATRA_NAMES[idx]

# -------------------------------------------------
# CORE MUHURAT LOGIC (NO SLOT SPAM)
# -------------------------------------------------
def generate_muhurats(start_date, end_date, user_request="general"):
    # Allowed nakshatra according to event type
    allowed_nak = EVENT_RULES.get(user_request, {}).get("allow", set(NAKSHATRA_NAMES))

    muhurats = []
    dt = IST.localize(datetime.combine(start_date, datetime.min.time()))
    end_dt = IST.localize(datetime.combine(end_date, datetime.max.time()))

    last_nak = None
    window_start = None

    while dt <= end_dt:
        today_str = dt.strftime("%Y-%m-%d")
        if today_str in ABHUJ_MUHURAT_DATES.values():
            muhurats.append({
                "start": dt.strftime("%Y-%m-%d 06:00 AM"),
                "end": dt.strftime("%Y-%m-%d 11:59 PM"),
                "nakshatra": "Siddh Muhurat",
                "event": "All Events",
                "explanation": f"{[name for name,date in ABHUJ_MUHURAT_DATES.items() if date==today_str][0]} is an Abhuj Muhurat. Any auspicious work can be done today without calculation."
            })
            dt += timedelta(days=1)
            continue
        #  Skip kharmaas period
        if is_kharmaas(dt):
            dt += timedelta(minutes=30)
            continue

        moon = get_moon_longitude(dt)
        nak = get_nakshatra(moon)

        if nak in allowed_nak:
            # Start new window if nakshatra changed
            if nak != last_nak:
                if last_nak and window_start:
                    muhurats.append({
                        "start": window_start.strftime("%Y-%m-%d %I:%M %p"),
                        "end": dt.strftime("%Y-%m-%d %I:%M %p"),
                        "nakshatra": last_nak
                    })
                window_start = dt
                last_nak = nak
        else:
            # Non-allowed nakshatra → close previous window
            if last_nak and window_start:
                muhurats.append({
                    "start": window_start.strftime("%Y-%m-%d %I:%M %p"),
                    "end": dt.strftime("%Y-%m-%d %I:%M %p"),
                    "nakshatra": last_nak
                })
            last_nak = None
            window_start = None

        dt += timedelta(minutes=30)

    # Add last open window if exists
    if last_nak and window_start:
        muhurats.append({
            "start": window_start.strftime("%Y-%m-%d %I:%M %p"),
            "end": end_dt.strftime("%Y-%m-%d %I:%M %p"),
            "nakshatra": last_nak
        })

    return muhurats


# -------------------------------------------------
# PROMPT SIZE LOG
# -------------------------------------------------
def log_prompt_size(prompt: str, count: int):
    chars = len(prompt)
    tokens = chars // 4
    logger.info(
        "PROMPT | muhurats=%d | chars=%d | tokens≈%d",
        count, chars, tokens
    )

# -------------------------------------------------
# AI CALL (EXPLANATION ONLY)
# -------------------------------------------------
def call_openai(muhurats, user_request):
    if not muhurats:
        return []
    
    if len(muhurats) > MAX_MUHURATS:
     muhurats = muhurats[:MAX_MUHURATS]

    slots_str = "\n".join(
        f"{m['start']} → {m['end']} | {m['nakshatra']}"
        for m in muhurats
    )
    logger.info("Formatted slots string (first 500 chars):\n%s", slots_str[:500])
     
    # breakpoint()  # STEP 2: Check slots_str formatting
    prompt = f"""
You are a Vedic Panchang expert and a Hindu astrology specialist.
Below are already-validated muhurat windows for "{user_request}".
Follow Hindu calendar rules (Tithi, Nakshatra, Karana, Yoga, Abhuj Muhurat, Rahu Kalam, Gulika) to provide explanations.
Do NOT reject or add new slots.
For each slot, give a short explanation why it is auspicious for this event according to Panchang.
Do NOT reject or add any slot.
Only add a short explanation for each.

Return ONLY valid JSON array.
Each item MUST be an object with keys:
start, end, nakshatra, explanation

Example:
[
  {{
    "start": "2025-11-01 06:00 AM",
    "end": "2025-11-01 10:00 AM",
    "nakshatra": "Rohini",
    "explanation": "Good for marriage..."
  }}
]

Muhurats:
{slots_str}
"""

    log_prompt_size(prompt, len(muhurats))

    r = requests.post(
        OPENAI_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        },
        timeout=30
    )

    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]

    match = re.search(r"\[.*\]", text, re.DOTALL)
    return json.loads(match.group(0)) if match else []

# -------------------------------------------------
# API ENDPOINT
# -------------------------------------------------
def format_muhurats_response(ai_output, event_type="marriage"):
    """
    Convert raw AI output into structured API response.
    
    ai_output: list of strings from AI like
       "2025-11-01 12:00 AM → 2025-11-01 11:00 PM | Uttara Bhadrapada: explanation"
    event_type: type of the event (marriage, business, etc.)
    """
    formatted = []

    for item in ai_output:
        try:
            if not all(k in item for k in ("start","end","nakshatra","explanation")):
              continue

            formatted.append({
                "start": item["start"],
                "end": item["end"],
                "nakshatra": item["nakshatra"],
                "explanation": item["explanation"]
            })
        except Exception as e:
            # Log or ignore malformed entries
            import logging
            logging.warning("Failed to parse AI output: %s | Error: %s", item, e)

    return {
        "status": "success",
        "request_type": event_type,
        "recommended_muhurats": formatted
    }


def generate_muhurat_pdf(muhurats, request_type, start_date, end_date):
    os.makedirs("static", exist_ok=True)

    file_name = f"{request_type}_muhurat_{uuid.uuid4().hex}.pdf"
    file_path = os.path.join("static", file_name)

    ORANGE = colors.HexColor("#FF6F00")
    LIGHT_ORANGE = colors.HexColor("#FFF3E0")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=ORANGE,
        fontSize=22,
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=11,
        spaceAfter=16
    )

    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=9,
        leading=12
    )

    header_style = ParagraphStyle(
        "Header",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.white,
        alignment=TA_CENTER
    )

    elements = []

    # 🕉 HEADER
    elements.append(Paragraph("🕉 SHUBH MUHURAT REPORT 🕉", title_style))
    elements.append(
        Paragraph(
            f"<b>Event:</b> {request_type.title()}<br/>"
            f"<b>Date Range:</b> {start_date} to {end_date}<br/>"
            f"<b>Based on:</b> Vedic Panchang",
            subtitle_style
        )
    )

    # ---------------- TABLE ----------------
    table_data = [[
        Paragraph("#", header_style),
        Paragraph("Start Time", header_style),
        Paragraph("End Time", header_style),
        Paragraph("Nakshatra", header_style),
        Paragraph("Explanation", header_style),
    ]]

    for idx, item in enumerate(muhurats, start=1):
        try:
            table_data.append([
                Paragraph(str(idx), cell_style),
                Paragraph(item["start"], cell_style),
                Paragraph(item["end"], cell_style),
                Paragraph(item["nakshatra"], cell_style),
                Paragraph(item["explanation"], cell_style),
            ])
        except Exception as e:
            logger.warning("PDF parse failed: %s", e)


    table = Table(
        table_data,
        colWidths=[30, 90, 90, 90, 170],
        repeatRows=1
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.6, ORANGE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, -1), LIGHT_ORANGE),
    ]))

    elements.append(table)

    elements.append(Spacer(1, 14))
    elements.append(
        Paragraph(
            "<b>Important Notes:</b><br/>"
            "• Avoid Rahu Kalam, Yamagandam & Gulika timings<br/>"
            "• Calculated using Vedic Astrology principles",
            cell_style
        )
    )

    elements.append(Spacer(1, 16))
    elements.append(
        Paragraph(
            "■ Generated by AI Vedic Astrology■",
            ParagraphStyle(
                "Footer",
                parent=styles["Italic"],
                alignment=TA_CENTER,
                textColor=ORANGE
            )
        )
    )

    doc.build(elements)
    return file_path



# ai-muhurat generator

@app.get("/ai-muhurat-range")
def ai_muhurat_range(
    start_date: str,
    end_date: str,
    user_request: str = "general"
):
    try:
        sdt = datetime.strptime(start_date, "%Y-%m-%d").date()
        edt = datetime.strptime(end_date, "%Y-%m-%d").date()

        raw = generate_muhurats(sdt, edt, user_request)
        ai_raw = call_openai(raw, user_request)
        final = format_muhurats_response(ai_raw, user_request)["recommended_muhurats"]
        pdf_path = generate_muhurat_pdf(
            muhurats=final,
            request_type=user_request,
            start_date=start_date,
            end_date=end_date
        )
        pdf_url = f"http://127.0.0.1:8000/{pdf_path}"
        return {
            "status": "success",
            "request_type": user_request,
            "recommended_muhurats": final,
            "pdf_url": pdf_url   # ONLY addition
        }

    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# ai-palm-reading-lite
def optimize_palm_image(image_bytes: bytes) -> bytes:
    logger.info("IMAGE INPUT SIZE (bytes): %d", len(image_bytes))
    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    img.thumbnail((512, 512))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=55, optimize=True)
    optimized=buf.getvalue()
    logger.info("IMAGE OPTIMIZED SIZE (bytes): %d", len(optimized))
    return optimized

def safe_json_from_ai(text: str):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found")

        return json.loads(match.group(0))

    except Exception:
        logger.warning("AI JSON parsing failed, falling back to text")
        return {
            "answers": text.strip()
        }
def build_palm_prompt(q: str):
    prompt = f"""
You are an expert palmist and experienced astrologer with deep knowledge of traditional palmistry.
Your analysis should feel natural, genuine, and based on real palm-reading principles.

STRICT OUTPUT RULES:
- Return ONLY valid JSON
- No markdown
- No text outside JSON
- Never mention that you are an AI

ANALYSIS GUIDELINES:
- If palm lines are clear:
    - Describe them in a calm, professional tone
    - Use phrases like "often indicates", "commonly associated with"
- If palm lines are faint or unclear:
    - Still give meaningful analysis
    - Use general palmistry tendencies
    - Use soft language like:
        "may suggest", "generally points toward", "can indicate"
- NEVER leave any field empty
- NEVER say only "Not clearly visible"
- Do NOT give exact dates, ages, or guarantees
- Do NOT exaggerate or make dramatic claims
- Keep answers balanced, positive, and realistic

RESPONSE STYLE:
- Sound like a real palm reader explaining observations
- Avoid absolute statements
- Focus on possibilities and tendencies
- Favor the user gently, without false promises

JSON SCHEMA:
{{
  "heart_line": "",
  "head_line": "",
  "life_line": "",
  "fate_line": "",
  "marriage_line": "",
  "answers": ""
}}

User question:
{q}
"""
    return prompt



def call_openai_palm_reader(base64_image: str, user_questions: str):
    logger.info("BASE64 IMAGE CHARS: %d", len(base64_image))
    logger.info("BASE64 IMAGE TOKENS (approx): %d", approx_tokens(base64_image))

    prompt = build_palm_prompt(user_questions)

    logger.info("CALLING OPENAI MODEL: %s", OPENAI_MODEL)

    r = requests.post(
        OPENAI_URL,
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": OPENAI_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }}
                ]
            }],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 180
        },
        timeout=30
    )

    r.raise_for_status()

    content = r.json()["choices"][0]["message"]["content"]
    logger.info("OPENAI RAW RESPONSE TEXT: %s", content)

    try:
        parsed = json.loads(content)
        logger.info("PARSED JSON KEYS: %s", list(parsed.keys()))
        return parsed
    except Exception:
        logger.warning("Invalid JSON from AI, fallback applied")
        return {"answers": content.strip()}




@app.post("/ai-palm-reading-lite")
async def ai_palm_reading_lite(
    palm_image: UploadFile = File(...),
    user_questions: str = Form("")
):
    try:
        logger.info("API HIT: /ai-palm-reading-lite")
        logger.info("USER QUESTION: %s", user_questions)

        raw = await palm_image.read()
        optimized = optimize_palm_image(raw)
        img_base64 = base64.b64encode(optimized).decode()

        result = call_openai_palm_reader(img_base64, user_questions)

        logger.info("FINAL RESPONSE READY")
        return {"status": "success", "data": result}

    except Exception:
        logger.exception("PALM READING ERROR")
        raise HTTPException(status_code=500, detail="Palm reading failed")
