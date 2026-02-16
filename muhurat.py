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
from PIL import Image, ImageOps, ImageEnhance
import hashlib
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.lib.units import inch
import os
from reportlab.lib.colors import HexColor
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pdf2image import convert_from_bytes
import imagehash
from PIL import ImageOps, ImageEnhance
ORANGE = HexColor("#F57C00")   # Hindu orange
LIGHT_ORANGE = HexColor("#FFF3E0")
import uuid
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
load_dotenv()


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("muhurat")

swe.set_ephe_path(r"D:\python\astro-py\ephe")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment")
OPENAI_URL = os.getenv("OPENAI_URL")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not set")

headers = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}
# OPENAI_MODEL = "gpt-4.1-mini"

PALM_CACHE = {}

def get_image_hash(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    phash = imagehash.phash(img)
    return str(phash)
IST = pytz.timezone("Asia/Kolkata")

app = FastAPI()
# app.mount("/static", StaticFiles(directory="static"), name="static")
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
# -------------------------------------------------
# PALMISTRY KNOWLEDGE BASE
# -------------------------------------------------
PALMISTRY_KNOWLEDGE = {
    "heart_line": {
        "clear": "indicating strong emotional intelligence, stable relationships, empathy, and a caring personality",
        "faint": "may suggest emotional sensitivity, cautious approach to relationships, or hidden feelings",
        "long": "shows deep emotional connections and the ability to love deeply",
        "short": "may indicate self-focus in relationships or practical approach to love",
        "curved": "indicating warmth, compassion, and adaptability in emotional matters",
        "straight": "suggesting control over emotions and logical approach to relationships"
    },
    "head_line": {
        "clear": "reflecting strong intellect, focus, and clarity of thought",
        "faint": "may indicate indecision or scattered thinking",
        "long": "shows thorough thinking, persistence, and strong memory",
        "short": "may suggest practical thinking or preference for quick decisions",
        "curved": "indicating creativity, imagination, and flexible thinking",
        "straight": "suggesting analytical mind, logical reasoning, and focus on facts"
    },
    "life_line": {
        "clear": "reflecting vitality, stability, and zest for life",
        "faint": "may indicate sensitivity, cautious approach to health, or low physical energy",
        "long": "suggesting robust health and endurance",
        "short": "may indicate vulnerability or reliance on careful lifestyle choices",
        "deep": "shows strong life energy and determination",
        "broken": "can suggest periods of major change or obstacles in life",
        "curved": "indicating adaptability and adventurous nature"
    },
    "fate_line": {
        "clear": "indicating strong career path, life direction, and personal responsibility",
        "faint": "may suggest uncertainties or changes in career or life path",
        "long": "shows consistent work and dedication over time",
        "short": "may suggest a more flexible or varied life path",
        "straight": "reflecting focus on goals and perseverance",
        "broken": "can indicate unexpected changes or life transitions"
    },
    "marriage_line": {
        "clear": "suggesting stable relationships, potential for marriage, and meaningful partnerships",
        "faint": "may indicate delayed or cautious approach to commitment",
        "single": "reflecting single or independent nature",
        "multiple": "may suggest multiple significant relationships or experiences",
        "short": "practical approach to relationships",
        "long": "deep emotional connection with partners"
    },
    "answers": "Overall, this palm shows a combination of emotional stability, intellectual clarity, life energy, and potential for meaningful relationships. Each line gives insights into personality traits, career tendencies, and relationship patterns based on classical palmistry."
}

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

# PROMPT SIZE LOG

def log_prompt_size(prompt: str, count: int):
    chars = len(prompt)
    tokens = chars // 4
    logger.info(
        "PROMPT | muhurats=%d | chars=%d | tokens≈%d",
        count, chars, tokens
    )

def call_openai(muhurats, user_request):
    if not muhurats:
        return [], {"prompt_tokens":0, "completion_tokens":0, "total_tokens":0, "cost_inr":0}
    
    if len(muhurats) > MAX_MUHURATS:
        muhurats = muhurats[:MAX_MUHURATS]

    slots_str = "\n".join(
        f"{m['start']} → {m['end']} | {m['nakshatra']}"
        for m in muhurats
    )
    logger.info("Formatted slots string (first 500 chars):\n%s", slots_str[:500])
     
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
[{{ "start": "2025-11-01 06:00 AM", "end": "2025-11-01 10:00 AM", "nakshatra": "Rohini", "explanation": "Good for marriage..." }}]

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
    response_json = r.json()

    # ---- Extract tokens & cost ----
       # ---- Extract tokens & cost ----
    usage = response_json.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    # ---- GPT-4.1-mini pricing ----
    INPUT_COST_PER_1K = 0.00015
    OUTPUT_COST_PER_1K = 0.0006
    USD_TO_INR = 83

    cost_usd = (
        (prompt_tokens / 1000) * INPUT_COST_PER_1K +
        (completion_tokens / 1000) * OUTPUT_COST_PER_1K
    )

    cost_inr = round(cost_usd * USD_TO_INR, 4)


    # ---- Parse AI output ----
    text = response_json["choices"][0]["message"]["content"]
    match = re.search(r"\[.*\]", text, re.DOTALL)
    ai_output = json.loads(match.group(0)) if match else []

    return ai_output, {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_inr": cost_inr
    }


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
def ai_muhurat_range(start_date: str, end_date: str, user_request: str = "general"):
    try:
        sdt = datetime.strptime(start_date, "%Y-%m-%d").date()
        edt = datetime.strptime(end_date, "%Y-%m-%d").date()

        raw = generate_muhurats(sdt, edt, user_request)
        ai_raw, token_info = call_openai(raw, user_request)
        final = format_muhurats_response(ai_raw, user_request)["recommended_muhurats"]

        pdf_path = generate_muhurat_pdf(
            muhurats=final,
            request_type=user_request,
            start_date=start_date,
            end_date=end_date
        )
        pdf_filename = os.path.basename(pdf_path)
        pdf_url = f"https://astro-kundali-wn41.onrender.com/static/{pdf_filename}"

        return {
            "status": "success",
            "request_type": user_request,
            "recommended_muhurats": final,
            "pdf_url": pdf_url,
            "tokens_used": token_info  # <-- NEW FIELD
        }

    except Exception as e:
        logger.error("Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ai-palm-reading-lite
# def optimize_palm_image(image_bytes: bytes) -> bytes:
#     logger.info("IMAGE INPUT SIZE (bytes): %d", len(image_bytes))

#     img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

#     # keep details of palm lines
#     img.thumbnail((1024, 1024))

#     buf = io.BytesIO()
#     img.save(buf, format="JPEG", quality=85)

#     optimized = buf.getvalue()
#     logger.info("IMAGE OPTIMIZED SIZE (bytes): %d", len(optimized))

#     return optimized
def optimize_palm_image(image_bytes: bytes) -> bytes:
    logger.info("IMAGE INPUT SIZE (bytes): %d", len(image_bytes))

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Auto rotate
    img = ImageOps.exif_transpose(img)

    # Standard size
    img.thumbnail((1024, 1024))

    # Normalize brightness & contrast
    img = ImageEnhance.Brightness(img).enhance(1.1)
    img = ImageEnhance.Contrast(img).enhance(1.2)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)

    optimized = buf.getvalue()
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

# validation
def validate_palm_image_with_ai(base64_image: str):
    """
    Industry-grade validation using Vision AI.
    Checks:
    - Real human hand
    - Palm facing camera
    - Close-up
    - Lines visible
    """

    prompt = """
You are an image validation system.

Check the image and return ONLY JSON:

{
  "is_palm": true/false,
  "confidence": 0-100,
  "reason": "short reason"
}

Validation rules:
Return is_palm = false if:
- Not a human hand
- Back of hand
- Side view
- Object, face, document, etc.
- Palm is far away
- Palm lines not visible
- Blurry or low quality

Return is_palm = true only if:
- Clear human palm
- Palm facing camera
- Close-up
- Major palm lines visible
"""

    try:
        r = requests.post(
            OPENAI_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0
            },
            timeout=20
        )

        r.raise_for_status()
        result = r.json()["choices"][0]["message"]["content"]
        return json.loads(result)

    except Exception as e:
        logger.error("Palm validation AI error: %s", e)
        return {
            "is_palm": False,
            "confidence": 0,
            "reason": "Image validation failed"
        }
    # ///////////////////////////

KNOWLEDGE_BASE = """
You are an expert palm reader with 20 years of experience.

Analyze the palm image carefully and provide a personalized reading.

Rules:
- Base interpretation only on visible palm lines.
- Avoid generic statements.
- Do not say "may suggest", "typically", or "generally".
- Write in a confident but realistic tone.
- Focus on customer insights:
    - Personality traits
    - Career tendencies
    - Relationship behavior
    - Life outlook
- Each line must contain specific interpretation.
- Return JSON format:

{
  "status": "success",
  "heart_line": "...",
  "head_line": "...",
  "life_line": "...",
  "fate_line": "...",
  "marriage_line": "...",
  "answers": "Overall personalized summary"
}
"""


# //////////////////////////////////////////////
# Palm prompt
def build_palm_prompt(user_question: str):
    """
    Build a prompt that instructs the AI to read visible palm lines
    and give palmistry-based interpretations for each major line.
    """
    prompt = f"""
You are an expert palmist with deep knowledge of traditional palmistry.

STEP 1 — Validate image:
- Only proceed if the palm is clear and all major lines are visible.
- If not, return ONLY:
{{
  "status": "invalid_image",
  "message": "Palm lines are not clearly visible"
}}

STEP 2 — Analyze palm lines:
- For each major line (heart, head, life, fate, marriage):
  1. Mention if it is visible and clear.
  2. Provide a palmistry interpretation based on traditional knowledge.
- Avoid any assumptions about unseen lines.
- Do NOT leave fields empty.
- Keep it realistic, positive, and professional.

Return ONLY JSON with this schema:

{{
  "status": "success",
  "heart_line": "",
  "head_line": "",
  "life_line": "",
  "fate_line": "",
  "marriage_line": "",
  "answers": "Summary of all line insights"
}}

User question:
{user_question}
"""
    return prompt


def build_customer_summary(enriched):
    insights = []

    # Personality
    if "emotional intelligence" in enriched["heart_line"].lower():
        insights.append("You are emotionally balanced, caring, and value deep relationships.")

    if "clarity of thought" in enriched["head_line"].lower() or "intellect" in enriched["head_line"].lower():
        insights.append("You have a practical and intelligent mindset, and you make thoughtful decisions.")

    # Life Energy
    if "life energy" in enriched["life_line"].lower() or "vitality" in enriched["life_line"].lower():
        insights.append("You possess strong inner strength and the ability to handle challenges in life.")

    # Career
    if "uncertainties" in enriched["fate_line"].lower() or "changes" in enriched["fate_line"].lower():
        insights.append("Your career path may include changes, but adaptability will bring growth and success.")
    else:
        insights.append("Your career path shows stability and steady progress through your efforts.")

    # Relationships
    if "stable relationships" in enriched["marriage_line"].lower() or "deep emotional connection" in enriched["marriage_line"].lower():
        insights.append("You are loyal in relationships and likely to build long-term meaningful partnerships.")

    # Final overall message
    insights.append(
        "Overall, your palm reflects a balanced personality with strong potential for personal growth, career success, and stable relationships."
    )

    return " ".join(insights)


def build_platinum_palm_reading(data):
    personality = []
    career = []
    love = []
    health = []
    life_path = []
    lucky_traits = []
    recommendations = []

    # ---------------- Personality ----------------
    if "curved" in data["heart_line"].lower():
        personality.append(
            "You possess a warm and compassionate nature, expressing emotions sincerely and connecting deeply with others. "
            "Empathy is your guiding strength."
        )
        lucky_traits.append("Empathy, Charisma, Emotional Intelligence")
    if "straight" in data["head_line"].lower():
        personality.append(
            "You have a practical and logical mindset, approaching challenges with clarity, reason, and well-structured planning."
        )
        lucky_traits.append("Analytical Skills, Discipline")
    if "curved" in data["head_line"].lower():
        personality.append(
            "Creativity and adaptability define your thinking, allowing you to find innovative solutions in complex situations."
        )
        lucky_traits.append("Creativity, Innovation, Versatility")
    if not personality:
        personality.append(
            "You possess a balanced personality harmonizing emotional insight with practical intelligence."
        )

    # ---------------- Career ----------------
    if "clear" in data["fate_line"].lower() or "long" in data["fate_line"].lower():
        career.append(
            "Your professional journey reflects stability and focused growth. Strategic planning and consistent effort will yield high achievements."
        )
        recommendations.append(
            "Engage in leadership roles, mentorship, or strategic planning to maximize career potential."
        )
    if "broken" in data["fate_line"].lower():
        career.append(
            "Your career may involve significant transitions, requiring resilience and adaptability. Each change is an opportunity for growth."
        )
        recommendations.append(
            "Be open to learning new skills and exploring diverse roles."
        )
    if "faint" in data["fate_line"].lower():
        career.append(
            "Your career success depends largely on self-driven effort, innovation, and perseverance."
        )
        recommendations.append(
            "Invest in skill development, networking, and personal projects to strengthen professional growth."
        )
    if "long" in data["head_line"].lower():
        career.append(
            "Analytical, technical, and managerial roles align naturally with your abilities. You thrive in structured and challenging environments."
        )
    if "curved" in data["head_line"].lower():
        career.append(
            "Creative, communication-oriented, and business leadership roles are highly suitable. You excel where innovation is valued."
        )
    if not career:
        career.append(
            "Career growth is influenced by determination, adaptability, and informed decision-making."
        )

    # ---------------- Love / Relationships ----------------
    if "multiple" in data["marriage_line"].lower():
        love.append(
            "Your life may feature several significant relationships, each providing unique lessons in emotional growth and understanding."
        )
        recommendations.append(
            "Embrace experiences with openness and learn from past relationship patterns."
        )
    if "clear" in data["marriage_line"].lower():
        love.append(
            "You are capable of long-lasting, loyal, and emotionally fulfilling relationships."
        )
        lucky_traits.append("Commitment, Trustworthiness")
    if "faint" in data["marriage_line"].lower():
        love.append(
            "You may take time before committing, seeking emotional alignment and mutual understanding."
        )
        recommendations.append(
            "Focus on clear communication and self-awareness to nurture strong partnerships."
        )
    if "long" in data["heart_line"].lower():
        love.append(
            "Deep emotional connection and sincerity are core to your relationships. You value trust and heartfelt communication."
        )
        lucky_traits.append("Emotional Depth, Loyalty")

    if not love:
        love.append(
            "You seek meaningful, balanced, and emotionally fulfilling relationships."
        )

    # ---------------- Health / Vitality ----------------
    if "deep" in data["life_line"].lower() or "long" in data["life_line"].lower():
        health.append(
            "Strong vitality and physical endurance mark your constitution. Regular exercise and mindful nutrition will enhance longevity."
        )
        recommendations.append(
            "Incorporate holistic practices like yoga, meditation, and balanced diet."
        )
    if "faint" in data["life_line"].lower():
        health.append(
            "Maintaining energy and wellness requires conscious effort. Lifestyle balance is essential."
        )
        recommendations.append(
            "Focus on structured routines, rest, and stress management."
        )
    if "broken" in data["life_line"].lower():
        health.append(
            "Life may include periods of stress or major lifestyle changes. Adaptability and health monitoring are key."
        )
        recommendations.append(
            "Prioritize preventive care and regular health check-ups."
        )
    if not health:
        health.append(
            "A disciplined lifestyle and awareness of well-being will support long-term vitality."
        )

    # ---------------- Life Path ----------------
    if "clear" in data["life_line"].lower() and "clear" in data["fate_line"].lower():
        life_path.append(
            "Your life path shows stability, clarity, and consistent progress. Steady effort and perseverance lead to personal fulfillment."
        )
        lucky_traits.append("Stability, Determination")
    else:
        life_path.append(
            "Your journey may involve changes and adaptations. Flexibility, resilience, and learning from experiences will bring success."
        )
        recommendations.append(
            "Embrace change with a positive mindset and continuous learning."
        )

    # ---------------- Elemental Influence ----------------
    elements = []
    if "curved" in data["heart_line"].lower():
        elements.append("Water - Emotional depth and intuition guide your life choices.")
    if "straight" in data["head_line"].lower():
        elements.append("Air - Logic, intellect, and strategic thinking define your path.")
    if "curved" in data["head_line"].lower():
        elements.append("Fire - Creativity, passion, and initiative fuel your ambitions.")

    return {
        "personality": " ".join(personality),
        "career": " ".join(career),
        "love": " ".join(love),
        "health": " ".join(health),
        "life_path": " ".join(life_path),
        "lucky_traits": ", ".join(lucky_traits) if lucky_traits else "Adaptability, Awareness",
        "elemental_influence": " ".join(elements) if elements else "Earth - Stability and grounding shape your life.",
        "recommendations": " ".join(recommendations) if recommendations else "Maintain balance across personal, professional, and health aspects for a fulfilled life."
    }



# Helper: enrich raw AI response using PALMISTRY_KNOWLEDGE
def enrich_with_knowledge(palm_data):
    """
    Enrich palm_data with detailed knowledge and premium insights.
    """
    enriched = {}

    # ---------------- Detailed line meanings ----------------
    for line in ["heart_line", "head_line", "life_line", "fate_line", "marriage_line"]:
        ai_text = palm_data.get(line, "").strip()
        key = "clear"  # default

        # Detect first matching keyword in text
        for keyword in ["faint", "curved", "straight", "deep", "broken", "long", "short", "single", "multiple"]:
            if keyword in ai_text.lower():
                key = keyword
                break

        # Attach knowledge from PALMISTRY_KNOWLEDGE if available
        knowledge_text = PALMISTRY_KNOWLEDGE.get(line, {}).get(key, "")
        if knowledge_text:
            enriched[line] = f"{ai_text} ({knowledge_text})"
        else:
            enriched[line] = ai_text

    # ---------------- Premium / Platinum insights ----------------
    # Use upgraded platinum reading for detailed analysis
    premium = build_platinum_palm_reading(enriched)

    # Merge premium insights
    for field in ["personality", "career", "love", "health", "life_path",
                  "lucky_traits", "elemental_influence", "recommendations"]:
        enriched[field] = premium.get(field, "")

    # Combine main answers into one summary
    enriched["answers"] = " ".join([
        premium.get("personality", ""),
        premium.get("career", ""),
        premium.get("love", ""),
        premium.get("health", ""),
        premium.get("life_path", "")
    ])

    enriched["status"] = "success"
    return enriched


# ------------------------------- Main AI palm reading call -------------------------------

def call_openai_palm_reader(base64_image: str, user_questions: str, return_tokens: bool = False):
    """
    Main AI palm reading function.
    Always returns a dictionary.
    If return_tokens=True → returns (result_dict, token_dict)
    """

    prompt = build_palm_prompt(user_questions)
    token_info = {}

    try:
        r = requests.post(
            OPENAI_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a professional palmist. Return ONLY JSON."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "top_p": 1,
                "max_tokens": 700
            },
            timeout=40
        )

        r.raise_for_status()
        content = r.json()

        # ---------------- Safe JSON Parse ----------------
        try:
            parsed = json.loads(content["choices"][0]["message"]["content"])
        except Exception:
            logger.error("AI returned invalid JSON")
            parsed = {
                "status": "failed",
                "error": "AI returned invalid format"
            }

        # ---------------- Token Usage ----------------
        if return_tokens and "usage" in content:
            usage = content["usage"]
            total_tokens = usage.get("total_tokens", 0)

            # Example pricing (adjust if needed)
            cost_inr = (total_tokens / 1000) * 0.002 * 83

            token_info = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": total_tokens,
                "cost_inr": round(cost_inr, 2)
            }

    except Exception as e:
        logger.error("OpenAI palm reader error: %s", str(e))
        error_response = {
            "status": "failed",
            "error": "AI processing failed"
        }
        if return_tokens:
            return error_response, {}
        return error_response

    # ---------------- Ensure parsed is dict ----------------
    if not isinstance(parsed, dict):
        parsed = {
            "status": "failed",
            "error": "Invalid AI response"
        }

    # ---------------- Handle invalid image ----------------
    if parsed.get("status") == "invalid_image":
        error_response = {
            "status": "failed",
            "error": parsed.get("message", "Palm lines are not clearly visible")
        }
        if return_tokens:
            return error_response, token_info
        return error_response

    # ---------------- Required fields fallback ----------------
    required_fields = [
        "heart_line",
        "head_line",
        "life_line",
        "fate_line",
        "marriage_line",
        "answers"
    ]

    for field in required_fields:
        if field not in parsed or not isinstance(parsed.get(field), str) or len(parsed[field].strip()) < 10:
            parsed[field] = f"{field.replace('_', ' ').title()} details are limited"

    # ---------------- Enrich Data ----------------
    try:
        enriched = enrich_with_knowledge(parsed)
    except Exception:
        enriched = parsed

    if return_tokens:
        return enriched, token_info

    return enriched

# ------------------------------- Helper for invalid image -------------------------------
def invalid_response(message: str):
    return {"status": "invalid_image", "message": message}

# Main PDF Generator
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak, KeepInFrame
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
import os, uuid, io
from PIL import Image

# COLORS
BG_COLOR = HexColor("#f5f5e7")
BORDER_COLOR = HexColor("#eb8552")
HEADER_BG = HexColor("#eb8552")
HEADER_TEXT = colors.white
TEXT_COLOR = colors.black
GREEN_HIGHLIGHT = HexColor("#1b8f3a")
INSIGHT_BOX_BG = colors.white
BRAND_COLOR = colors.red
FOOTER_COLOR = HexColor("#ff6600")  # Orange
RECOMMENDATION_COLOR = HexColor("#ff3300")  # Red/Orange for recommendation text

# BRAND
BRAND_NAME = "KAstrofy"
LOCATION = "Agarwal Bhavan"
MOBILE = "9999999999"
EMAIL = "astrofy@gmail.com"

# Highlight Keywords
def highlight_keywords(text):
    if not text:
        return ""
    keywords = [
        "strong", "stable", "positive", "success",
        "growth", "opportunity", "health",
        "career", "love", "energy", "vitality",
        "loyalty", "creativity", "resilience"
    ]
    for word in keywords:
        text = text.replace(word, f'<font color="{GREEN_HIGHLIGHT}"><b>{word}</b></font>')
        text = text.replace(word.capitalize(), f'<font color="{GREEN_HIGHLIGHT}"><b>{word.capitalize()}</b></font>')
    return text

# Background + Header + Footer
# def draw_page(canvas, doc):
#     # Background
#     canvas.setFillColor(BG_COLOR)
#     canvas.rect(0, 0, A4[0], A4[1], fill=1)

#     # Top Brand Name in BIG RED FONT
#     canvas.setFillColor(BRAND_COLOR)
#     canvas.setFont("Helvetica-Bold", 28)
#     canvas.drawCentredString(A4[0] / 2, A4[1] - 35, BRAND_NAME)

#     # Footer in Orange
#     canvas.setFont("Helvetica", 9)
#     canvas.setFillColor(FOOTER_COLOR)
#     canvas.drawCentredString(
#         A4[0] / 2,
#         20,
#         f"Location: {LOCATION} | Mobile: {MOBILE} | Email: {EMAIL}"
#     )
def draw_page(canvas, doc):
    # Background
    canvas.setFillColor(BG_COLOR)
    canvas.rect(0, 0, A4[0], A4[1], fill=1)

    # Top Brand Name
    canvas.setFillColor(BRAND_COLOR)
    canvas.setFont("Helvetica-Bold", 28)
    canvas.drawCentredString(A4[0] / 2, A4[1] - 35, BRAND_NAME)

    # Footer details
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(FOOTER_COLOR)
    canvas.drawCentredString(
        A4[0] / 2,
        20,
        f"Location: {LOCATION} | Mobile: {MOBILE} | Email: {EMAIL}"
    )

    # Page number (NEW)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(A4[0] - 40, 20, f"Page {doc.page}")

def generate_palm_pdf(palm_data, user_questions=None, palm_image_bytes=None):
    os.makedirs("static", exist_ok=True)
    file_name = f"astrofy_palm_{uuid.uuid4().hex}.pdf"
    file_path = os.path.join("static", file_name)

    CONTENT_WIDTH = 510
    side_margin = (A4[0] - CONTENT_WIDTH) / 2
    COLUMN_WIDTHS = [150, 360]

    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=side_margin,
        rightMargin=side_margin,
        topMargin=70,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    # Styles
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=18,
        alignment=TA_CENTER,
        textColor=TEXT_COLOR,
        spaceAfter=12
    )

    text_style = ParagraphStyle(
        "Text",
        parent=styles["Normal"],
        fontSize=10,
        leading=15,
        textColor=TEXT_COLOR
    )

    table_header = ParagraphStyle(
        "Header",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=HEADER_TEXT,
        alignment=TA_CENTER
    )

    bold_center_style = ParagraphStyle(
        "BoldCenter",
        parent=text_style,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER
    )

    insight_heading_style = ParagraphStyle(
        "InsightHeading",
        parent=text_style,
        fontSize=12,
        textColor=colors.red,
        alignment=TA_CENTER,
        spaceAfter=10,
        fontName="Helvetica-Bold"
    )

    insight_value_style = ParagraphStyle(
        "InsightValue",
        parent=text_style,
        fontSize=11,
        textColor=TEXT_COLOR,
        alignment=TA_LEFT,
        leading=16,
        backColor=INSIGHT_BOX_BG,
        borderPadding=10
    )

    recommendation_style = ParagraphStyle(
        "Recommendation",
        parent=text_style,
        fontSize=10,
        textColor=RECOMMENDATION_COLOR,
        alignment=TA_LEFT,
        leading=16
    )

    elements = []

    # ---------------- Page 1 ----------------
    elements.append(Paragraph("KAstrofy Palm Reading Report", title_style))

    # Palm Lines Table
    line_data = [
        [Paragraph("Palm Line", table_header), Paragraph("Detailed Meaning", table_header)],
        [Paragraph("Heart Line", bold_center_style), Paragraph(highlight_keywords(palm_data.get("heart_line", "")), text_style)],
        [Paragraph("Head Line", bold_center_style), Paragraph(highlight_keywords(palm_data.get("head_line", "")), text_style)],
        [Paragraph("Life Line", bold_center_style), Paragraph(highlight_keywords(palm_data.get("life_line", "")), text_style)],
        [Paragraph("Fate Line", bold_center_style), Paragraph(highlight_keywords(palm_data.get("fate_line", "")), text_style)],
        [Paragraph("Marriage Line", bold_center_style), Paragraph(highlight_keywords(palm_data.get("marriage_line", "")), text_style)],
    ]

    line_table = Table(line_data, colWidths=COLUMN_WIDTHS, repeatRows=1, hAlign='CENTER')
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
        ('GRID', (0, 0), (-1, -1), 1.2, BORDER_COLOR),
        ('BACKGROUND', (0, 1), (-1, -1), BG_COLOR),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('VALIGN', (0, 1), (0, -1), 'MIDDLE'),  # Vertical center
        ('VALIGN', (1, 1), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))

    elements.append(line_table)
    elements.append(Spacer(1, 12))

    # Category Table
    cat_data = [
        [Paragraph("Category", table_header), Paragraph("Analysis & Guidance", table_header)],
        [Paragraph("Personality", bold_center_style), Paragraph(highlight_keywords(palm_data.get("personality", "")), text_style)],
        [Paragraph("Career & Finance", bold_center_style), Paragraph(highlight_keywords(palm_data.get("career", "")), text_style)],
        [Paragraph("Love & Relationship", bold_center_style), Paragraph(highlight_keywords(palm_data.get("love", "")), text_style)],
        [Paragraph("Health & Energy", bold_center_style), Paragraph(highlight_keywords(palm_data.get("health", "")), text_style)],
        [Paragraph("Life Path", bold_center_style), Paragraph(highlight_keywords(palm_data.get("life_path", "")), text_style)],
        [Paragraph("Lucky Traits", bold_center_style), Paragraph(highlight_keywords(palm_data.get("lucky_traits", "")), text_style)],
        [Paragraph("Elemental Influence", bold_center_style), Paragraph(highlight_keywords(palm_data.get("elemental_influence", "")), text_style)],
        [Paragraph("Recommendations", bold_center_style), Paragraph(highlight_keywords(palm_data.get("recommendations", "")), recommendation_style)],
    ]

    cat_table = Table(cat_data, colWidths=COLUMN_WIDTHS, repeatRows=1, hAlign='CENTER')
    cat_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
        ('GRID', (0, 0), (-1, -1), 1.2, BORDER_COLOR),
        ('BACKGROUND', (0, 1), (-1, -1), BG_COLOR),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('VALIGN', (0, 1), (0, -1), 'MIDDLE'),
        ('VALIGN', (1, 1), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))

    elements.append(cat_table)

    # ---------------- Page 2 ----------------
    # ---------------- Page 2 ----------------
    elements.append(PageBreak())

    insight_text = highlight_keywords(palm_data.get("answers", ""))

    insight_box = KeepInFrame(
    CONTENT_WIDTH,
    120,  # Reduced height to avoid overflow
    [Paragraph(insight_text, insight_value_style)],
    mode="shrink"
    )

    page2_content = [
     Spacer(1, 20),
     Paragraph("🌟 Overall Insight", insight_heading_style),
     Spacer(1, 10),
     insight_box,
     Spacer(1, 15)
    ]

# Palm Image
    if palm_image_bytes:
       try:
        img = Image.open(io.BytesIO(palm_image_bytes)).convert("RGB")

        # Strict image size (important)
        max_w, max_h = 4.0 * inch, 3.2 * inch
        img.thumbnail((max_w, max_h), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        buf.seek(0)

        rl_img = RLImage(buf, width=max_w, height=max_h)
        rl_img.hAlign = "CENTER"

        image_table = Table([[rl_img]], colWidths=[CONTENT_WIDTH])
        image_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 2, BORDER_COLOR),
            ('BACKGROUND', (0, 0), (-1, -1), BG_COLOR),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))

        page2_content.append(image_table)

       except Exception as e:
        print("Image error:", e)

# -------- CENTER + FORCE SINGLE PAGE --------

    page2_frame = KeepInFrame(
         CONTENT_WIDTH,
         520,   # Strict total height to prevent page 3
         page2_content,
         mode="shrink"
     )

    page2_table = Table(
         [[page2_frame]],
         colWidths=[CONTENT_WIDTH],
         hAlign='CENTER'
     )

    page2_table.setStyle(TableStyle([
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ('TOPPADDING', (0, 0), (-1, -1), 0),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
   ]))

    elements.append(page2_table)



    # Build PDF
    doc.build(elements, onFirstPage=draw_page, onLaterPages=draw_page)
    return file_path

# Generate palm read Response
@app.post("/ai-palm-reading-lite")
async def ai_palm_reading_lite(
    palm_image: UploadFile = File(...),
    user_questions: str = Form("")
):
    try:
        logger.info("API HIT: /ai-palm-reading-lite")

        # FILE TYPE VALIDATION
        if palm_image.content_type not in ["image/jpeg","image/png","application/pdf"]:
            raise HTTPException(
                status_code=400,
                detail="Only JPG, PNG or PDF allowed"
            )

        raw = await palm_image.read()
        # FILE SIZE VALIDATION
        if len(raw) < 5000:
            raise HTTPException(
                status_code=400,
                detail="Image too small or invalid"
            )

        if len(raw) > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="Image too large (Max 5MB)"
            )
        # IMAGE OPTIMIZATION
        if palm_image.content_type == "application/pdf":
            pages = convert_from_bytes(raw, dpi=200)
            img = pages[0]
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            raw = buf.getvalue()

        optimized = optimize_palm_image(raw)
        img_base64 = base64.b64encode(optimized).decode()

        image_hash = get_image_hash(optimized)

        if image_hash in PALM_CACHE:
         logger.info("Returning cached palm result")
         cached_response = PALM_CACHE[image_hash]
         return cached_response

        # STRICT PALM VALIDATION
        validation = validate_palm_image_with_ai(img_base64)
        logger.info("Palm validation result: %s", validation)

        if not validation.get("is_palm") or validation.get("confidence", 0) < 70:
            logger.warning("Image rejected as non-palm")
            return {
                "status": "failed",
                "error_code": "INVALID_PALM",
                "message": validation.get(
                    "reason",
                    "Please upload a clear close-up photo of a human palm."
                )
            }

        # Modify your call_openai_palm_reader to return both result and token usage
        result, token_info = call_openai_palm_reader(img_base64, user_questions, return_tokens=True)

        if not result or len(result.keys()) < 3:
            logger.warning("AI returned incomplete data")
            return {
                "status": "failed",
                "error_code": "INCOMPLETE_ANALYSIS",
                "message": "Palm analysis could not be completed. Please upload a clearer image."
            }

        required_fields = ["heart_line", "head_line", "life_line"]
        for field in required_fields:
            if field not in result or len(result[field].strip()) < 25:
                logger.warning("Weak field detected: %s", field)
                result[field] = f"{field.replace('_',' ').title()} details are limited"

        # GENERATE PDF
        pdf_path = generate_palm_pdf(result, user_questions, raw)
        pdf_filename = os.path.basename(pdf_path)
        pdf_url = f"https://astro-kundali-wn41.onrender.com/static/{pdf_filename}"  # Or your server IP

        response_data = {
              "status": "success",
              "data": result,
              "pdf_url": pdf_url,
              "tokens_used": token_info
           }


        PALM_CACHE[image_hash] = response_data

        return response_data


    except HTTPException:
        raise

    except Exception as e:
        logger.exception("PALM READING ERROR: %s", str(e))
        raise HTTPException(
            status_code=500,
            detail="Palm reading failed"
        )




# ///////////////////////////////////////////////////////////
class MuhuratRequest(BaseModel):
    start_date: str
    end_date: str
    user_request: str = "general"

@app.post("/generate_muhurat")
def generate_muhurat_post(request: MuhuratRequest):
    try:
        start_date = request.start_date
        end_date = request.end_date
        user_request = request.user_request

        sdt = datetime.strptime(start_date, "%Y-%m-%d").date()
        edt = datetime.strptime(end_date, "%Y-%m-%d").date()

        # Existing logic (NO changes)
        raw = generate_muhurats(sdt, edt, user_request)

        # ---- Capture AI output + token usage safely ----
        ai_response = call_openai(raw, user_request)

        # Ensure unpacking safety
        if isinstance(ai_response, tuple):
            ai_raw, token_usage = ai_response
        else:
            ai_raw = ai_response
            token_usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "cost_inr": 0
            }

        # Validate AI output
        if not isinstance(ai_raw, list):
            logger.error("AI returned invalid format")
            raise HTTPException(status_code=500, detail="AI processing failed")

        final = format_muhurats_response(ai_raw, user_request)["recommended_muhurats"]

        pdf_path = generate_muhurat_pdf(
            muhurats=final,
            request_type=user_request,
            start_date=start_date,
            end_date=end_date
        )

        pdf_filename = os.path.basename(pdf_path)
        pdf_url = f"https://astro-kundali-wn41.onrender.com/static/{pdf_filename}"

        return {
            "status": "success",
            "request_type": user_request,
            "recommended_muhurats": final,
            "pdf_url": pdf_url,
            "token_usage": token_usage
        }

    except Exception as e:
        logger.error("POST Muhurat Error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
