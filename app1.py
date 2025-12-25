# ai_astrologer.py
from flask import Flask, request, jsonify
import swisseph as swe
from datetime import datetime, timedelta
import math
import uuid
import os
from groq import Groq   # pip install groq
import traceback

app = Flask(__name__)

# ----------------------------
# Configuration
# ----------------------------
swe.set_ephe_path(r'D:\python\astro-py\ephe')   # your ephemeris folder

# server-side session store (in-memory)
# session_id -> { "kundali": {...}, "chats": [ {user,bot,ts} ], "created_at": dt }
SESSION_STORE = {}

# Planet codes mapping
PLANETS = {
    'Sun': swe.SUN,
    'Moon': swe.MOON,
    'Mercury': swe.MERCURY,
    'Venus': swe.VENUS,
    'Mars': swe.MARS,
    'Jupiter': swe.JUPITER,
    'Saturn': swe.SATURN,
    'Rahu': swe.MEAN_NODE,
    'Ketu': swe.MEAN_NODE
}

# Nakshatra names and lords
NAKSHATRAS = [
 "Ashwini","Bharani","Krittika","Rohini","Mrigashira","Ardra",
 "Punarvasu","Pushya","Ashlesha","Magha","Purva Phalguni","Uttara Phalguni",
 "Hasta","Chitra","Swati","Vishakha","Anuradha","Jyeshtha",
 "Mula","Purva Ashadha","Uttara Ashadha","Shravana","Dhanishta",
 "Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati"
]

NAKSHATRA_LORDS = [
    "Ketu","Venus","Sun","Moon","Mars","Rahu",
    "Jupiter","Saturn","Mercury","Ketu","Venus","Sun",
    "Moon","Mars","Rahu","Jupiter","Saturn","Mercury",
    "Ketu","Venus","Sun","Moon","Mars","Rahu",
    "Jupiter","Saturn","Mercury"
]

# Vimshottari order & durations (years)
VIM_ORDER = ["Ketu","Venus","Sun","Moon","Mars","Rahu","Jupiter","Saturn","Mercury"]
VIM_YEARS = {"Ketu":7,"Venus":20,"Sun":6,"Moon":10,"Mars":7,"Rahu":18,"Jupiter":16,"Saturn":19,"Mercury":17}
TOTAL_VIM_YEARS = sum(VIM_YEARS.values())  # 120

# ----------------------------
# Utilities
# ----------------------------
def normalize_angle(a):
    a = a % 360.0
    if a < 0:
        a += 360.0
    return a

def sign_index_from_degree(deg):
    return int(deg // 30)  # 0..11

def degree_in_sign(deg):
    return deg % 30.0

def get_nakshatra_info(deg):
    span = 360.0 / 27.0
    idx = int(deg // span)
    name = NAKSHATRAS[idx]
    offset_in_nak = deg - idx * span
    pada = int(offset_in_nak // (span / 4.0)) + 1
    lord = NAKSHATRA_LORDS[idx]
    return idx + 1, name, pada, lord  # 1-based index

def round2(v):
    try:
        return round(float(v), 6)
    except:
        return v

# ----------------------------
# Vimshottari calculation (approximate practical implementation)
# ----------------------------
def compute_vimshottari_for_birth(birth_dt, moon_global_deg):
    """
    Returns:
      - mahadasha_sequence: list of dicts {lord, start_dt, end_dt, years_duration}
      - current info: {current_maha, maha_index, days_into_maha, remaining_days, current_antar (approx)}
    """
    # moon nakshatra index and fraction within nakshatra
    span = 360.0 / 27.0
    nak_index = int(moon_global_deg // span)  # 0-based
    pos_in_nak = (moon_global_deg % span) / span  # 0..1 (fraction inside nakshatra)
    # start dasa lord
    start_lord = NAKSHATRA_LORDS[nak_index]  # string like "Ketu"
    # rotate VIM_ORDER so it starts from start_lord
    if start_lord in VIM_ORDER:
        si = VIM_ORDER.index(start_lord)
        seq = VIM_ORDER[si:] + VIM_ORDER[:si]
    else:
        seq = VIM_ORDER[:]  # fallback

    # Remaining fraction of the starting dasha at birth:
    remaining_fraction = 1.0 - pos_in_nak  # portion of that dasha left
    # Compute mahadasha durations and start/end datetimes
    mahadashas = []
    cur_start = birth_dt
    # first dasa remaining duration = remaining_fraction * VIM_YEARS[start_lord]
    first_years = remaining_fraction * VIM_YEARS[start_lord]
    first_days = first_years * 365.25
    cur_end = cur_start + timedelta(days=first_days)
    mahadashas.append({
        "lord": start_lord,
        "start": cur_start,
        "end": cur_end,
        "years": first_years
    })
    # subsequent full dashas
    for lord in seq[1:]:
        years = VIM_YEARS[lord]
        days = years * 365.25
        s = cur_end
        e = s + timedelta(days=days)
        mahadashas.append({"lord": lord, "start": s, "end": e, "years": years})
        cur_end = e
    # then continue looping full cycles until coverage up to, say, birth + 130 years
    # find how many cycles needed to cover now
    now = datetime.utcnow()
    while mahadashas[-1]["end"] < now:
        for lord in seq:
            years = VIM_YEARS[lord]
            days = years * 365.25
            s = mahadashas[-1]["end"]
            e = s + timedelta(days=days)
            mahadashas.append({"lord": lord, "start": s, "end": e, "years": years})
            if mahadashas[-1]["end"] >= now:
                break

    # find current mahadasha index
    current = None
    for idx, m in enumerate(mahadashas):
        if m["start"] <= now < m["end"]:
            current = {"index": idx, "maha": m}
            break
    if current is None:
        current = {"index": len(mahadashas)-1, "maha": mahadashas[-1]}

    # compute antar (sub-dasa) within current mahadasha (approx)
    # Antar proportions use the full sequence order and durations scaled to maha years.
    maha_lord = current["maha"]["lord"]
    maha_years = current["maha"]["years"]
    # antar sequence ALWAYS starts from maha_lord in normal order
    # find order index in VIM_ORDER
    base_order = VIM_ORDER[:]
    start_idx = base_order.index(maha_lord) if maha_lord in base_order else 0
    antar_seq = base_order[start_idx:] + base_order[:start_idx]
    # antar durations (years) = (planet_years / 120) * maha_total_years
    antar_list = []
    maha_start = current["maha"]["start"]
    for p in antar_seq:
        fraction = VIM_YEARS[p] / TOTAL_VIM_YEARS
        p_years = fraction * maha_years
        p_days = p_years * 365.25
        s = maha_start
        e = s + timedelta(days=p_days)
        antar_list.append({"lord": p, "start": s, "end": e, "years": p_years})
        maha_start = e
        if maha_start > current["maha"]["end"]:
            break

    # find current antar
    current_antar = None
    for a in antar_list:
        if a["start"] <= datetime.utcnow() < a["end"]:
            current_antar = a
            break

    # simplify outputs: convert datetimes to ISO strings
    def iso(dt): return dt.isoformat()

    mahadashas_simple = [
        {"lord": m["lord"], "start": iso(m["start"]), "end": iso(m["end"]), "years": round(m["years"], 6)}
        for m in mahadashas
    ]

    antar_simple = [
        {"lord": a["lord"], "start": iso(a["start"]), "end": iso(a["end"]), "years": round(a["years"],6)}
        for a in antar_list
    ]

    result = {
        "mahadashas": mahadashas_simple,
        "antar_sequence": antar_simple,
        "current_maha_index": current["index"],
        "current_maha": {
            "lord": current["maha"]["lord"],
            "start": iso(current["maha"]["start"]),
            "end": iso(current["maha"]["end"]),
            "years": round(current["maha"]["years"],6)
        },
        "current_antar": ({"lord": current_antar["lord"], "start": iso(current_antar["start"]), "end": iso(current_antar["end"]), "years": round(current_antar["years"],6)} if current_antar else None)
    }
    return result

# ----------------------------
# Kundali generation (detailed)
# ----------------------------
def generate_kundali(dob, time_str, lat, lon):
    """
    dob: 'YYYY-MM-DD' ; time_str: 'HH:MM' ; lat, lon floats
    returns dict with kundali details and dasha info
    """
    dt = datetime.strptime(f"{dob} {time_str}", "%Y-%m-%d %H:%M")
    jd = swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute/60.0)

    kundali = {}
    planet_positions = {}
    speeds = {}

    # planets positions and speed estimate (1 hour)
    jd2 = jd + (1.0/24.0)
    for pname, pcode in PLANETS.items():
        pos1, flags1 = swe.calc_ut(jd, pcode)
        pos2, flags2 = swe.calc_ut(jd2, pcode)

        lon1 = float(pos1[0])
        lon2 = float(pos2[0])

        # compute delta deg/day properly (handle wrap)
        diff = (lon2 - lon1)
        if diff > 180: diff -= 360
        if diff < -180: diff += 360
        deg_per_day = diff / (1.0/24.0)  # since diff over 1 hour
        rad_per_day = deg_per_day * math.pi / 180.0
        retro = deg_per_day < 0

        # Ketu opposite Rahu for representation: compute Rahu as mean node, Ketu as opposite
        if pname == 'Ketu':
            lon = normalize_angle(planet_positions.get('Rahu', lon1) + 180.0)
        else:
            lon = normalize_angle(lon1)

        planet_positions[pname] = lon
        speeds[pname] = {"deg_per_day": deg_per_day, "rad_per_day": rad_per_day, "retro": retro}

    # houses & ascendant
    cusps, ascmc = swe.houses(jd, lat, lon, b'P')
    ascendant = float(ascmc[0])

    # build planet detailed entries (matching your desired advanced format)
    response = {}
    idx = 0
    # Ascendant entry
    asc_rasi_idx = sign_index_from_degree(ascendant)
    asc_local_deg = degree_in_sign(ascendant)
    asc_info = {
        "name": "As",
        "full_name": "Ascendant",
        "local_degree": round2(asc_local_deg),
        "global_degree": round2(ascendant),
        "progress_in_percentage": round2((asc_local_deg/30.0)*100.0),
        "rasi_no": asc_rasi_idx + 1,
        "zodiac": ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"][asc_rasi_idx],
        "house": 1,
        "nakshatra": get_nakshatra_info(ascendant)[1],
        "nakshatra_lord": get_nakshatra_info(ascendant)[3],
        "nakshatra_pada": get_nakshatra_info(ascendant)[2],
        "nakshatra_no": get_nakshatra_info(ascendant)[0],
        "is_planet_set": False,
        "lord_status": "-"
    }
    response[str(idx)] = asc_info
    idx += 1

    # Planet entries in standard order
    order = ["Sun","Moon","Mars","Mercury","Jupiter","Venus","Saturn","Rahu","Ketu"]
    for p in order:
        gdeg = planet_positions[p]
        local_deg = degree_in_sign(gdeg)
        rasi_idx = sign_index_from_degree(gdeg)
        nak_info = get_nakshatra_info(gdeg)
        sp = speeds[p]
        entry = {
            "name": p[:2],
            "full_name": p,
            "local_degree": round2(local_deg),
            "global_degree": round2(gdeg),
            "progress_in_percentage": round2((local_deg/30.0)*100.0),
            "rasi_no": rasi_idx + 1,
            "zodiac": ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"][rasi_idx],
            "house": None,  # we will fill by finding which house cusp contains this degree
            "speed_radians_per_day": round2(sp["rad_per_day"]),
            "retro": bool(sp["retro"]),
            "nakshatra": nak_info[1],
            "nakshatra_lord": nak_info[3],
            "nakshatra_pada": nak_info[2],
            "nakshatra_no": nak_info[0],
            "is_planet_set": False,
            "basic_avastha": "-",   # placeholder heuristics, can be improved
            "lord_status": "-"
        }
        # determine house by checking cusps: house i spans cusp[i-1]..cusp[i] (Placidus has cusps list)
        # We'll use simple logic: find first cusp > degree, house number = that index
        hno = None
        for i in range(12):
            c = cusps[i]
            nxt = cusps[(i+1) % 12]
            # handle wrap
            if c <= nxt:
                if c <= gdeg < nxt:
                    hno = i+1
                    break
            else:
                # wrap around 360
                if gdeg >= c or gdeg < nxt:
                    hno = i+1
                    break
        entry["house"] = hno if hno else 12
        response[str(idx)] = entry
        idx += 1

    # dasha (vimshottari)
    moon_deg = planet_positions["Moon"]
    dasha_info = compute_vimshottari_for_birth(dt, moon_deg)

    # panchang basics
    ayan = swe.get_ayanamsa(jd)
    weekday = dt.strftime("%A")
    panchang = {
        "ayanamsa": ayan,
        "ayanamsa_name": "Lahiri",
        "day_of_birth": weekday,
        "day_lord": asc_info["zodiac"],
        "hora_lord": asc_info["zodiac"],
        "sunrise_at_birth": "-",
        "sunset_at_birth": "-",
        "tithi": "-",
        "yoga": "-",
        "karana": "-"
    }

    # top-level metadata
    final = {
        "response": response,
        "status": 200,
        "dasha": dasha_info,
        "panchang": panchang,
        "rasi": asc_info["zodiac"],
        "nakshatra": asc_info["nakshatra"],
        "nakshatra_pada": asc_info["nakshatra_pada"],
        "generated_at": datetime.utcnow().isoformat()
    }

    return final

# ----------------------------
# Build fact list from the stored kundali (compact)
# ----------------------------
def build_fact_list_from_stored(kundali_full):
    # kundali_full is the 'final' returned by generate_kundali
    facts = []
    planet_positions = {}
    # Ascendant
    asc_entry = kundali_full["response"]["0"]
    asc_deg = asc_entry["global_degree"]
    facts.append(f"Ascendant: {asc_deg:.2f}° ({asc_entry['zodiac']})")

    # planets
    for key in sorted(kundali_full["response"].keys()):
        if key == "0": continue
        p = kundali_full["response"][key]
        pname = p["full_name"]
        gdeg = float(p["global_degree"])
        planet_positions[pname] = gdeg
        local = float(p["local_degree"])
        facts.append(f"{pname}: {gdeg:.2f}° ({p['zodiac']} {local:.2f}°) - House {p['house']} - Nakshatra {p['nakshatra']}({p['nakshatra_pada']})")

    # aspects
    # detect aspects using planet_positions
    aspects = []
    names = list(planet_positions.keys())
    for i in range(len(names)):
        for j in range(i+1, len(names)):
            a = planet_positions[names[i]]
            b = planet_positions[names[j]]
            diff = abs((a - b + 180) % 360 - 180)
            if diff <= 8:
                aspects.append(f"{names[i]}-{names[j]} conjunction (orb {diff:.2f})")
            elif abs(diff-180) <= 8:
                aspects.append(f"{names[i]}-{names[j]} opposition (orb {diff:.2f})")
            elif abs(diff-120) <= 6:
                aspects.append(f"{names[i]}-{names[j]} trine (orb {diff:.2f})")
            elif abs(diff-90) <= 6:
                aspects.append(f"{names[i]}-{names[j]} square (orb {diff:.2f})")
            elif abs(diff-60) <= 5:
                aspects.append(f"{names[i]}-{names[j]} sextile (orb {diff:.2f})")
    facts.append("Aspects: " + (", ".join(aspects) if aspects else "None"))

    # dasha summary
    d = kundali_full.get("dasha", {})
    current_maha = d.get("current_maha", {})
    current_antar = d.get("current_antar", None)
    facts.append(f"Current Mahadasha: {current_maha.get('lord','-')} ({current_maha.get('start','-')} to {current_maha.get('end','-')})")
    if current_antar:
        facts.append(f"Current Antar: {current_antar['lord']} ({current_antar['start']} to {current_antar['end']})")

    return "\n".join(facts), planet_positions, asc_deg

# ----------------------------
# /kundali endpoint - creates session & stores kundali
# ----------------------------
@app.route('/kundali', methods=['POST'])
def kundali_endpoint():
    try:
        payload = request.json
        dob = payload.get("dob")
        time_str = payload.get("time") or payload.get("tob") or payload.get("time_str")
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))
        if not (dob and time_str and lat is not None and lon is not None):
            return jsonify({"error": "Fields required: dob (YYYY-MM-DD), time (HH:MM), lat, lon"}), 400

        kundali = generate_kundali(dob, time_str, lat, lon)

        # create session id and store
        session_id = str(uuid.uuid4())
        SESSION_STORE[session_id] = {
            "kundali": kundali,
            "chats": [],
            "created_at": datetime.utcnow().isoformat()
        }

        # return only session_id + some safe message (NOT kundali unless desired)
        return jsonify({
            "status": "success",
            "session_id": session_id,
            "message": "Kundali generated and stored in session. Use this session_id for ai-ask."
        }) 
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "kundali generation failed", "detail": str(e)}), 500

# ----------------------------
# /ai-ask endpoint - use session_id and question
# ----------------------------
@app.route('/ai-ask', methods=['POST'])
def ai_ask_endpoint():
    try:
        payload = request.json
        session_id = payload.get("session_id")
        question = payload.get("question")
        if not session_id or not question:
            return jsonify({"error":"Fields required: session_id, question"}), 400

        if session_id not in SESSION_STORE:
            return jsonify({"error":"Invalid session_id"}), 404

        kundali_full = SESSION_STORE[session_id]["kundali"]

        # build compact facts (string), planet positions, asc
        facts_text, planet_positions, asc_deg = build_fact_list_from_stored(kundali_full)

        # build prompt
        system = "You are an experienced Vedic astrologer. Use only the facts provided. Be cautious, use probabilistic phrasing and do not give medical/legal/financial advice."
        user_prompt = f"Kundali facts:\n{facts_text}\n\nUser question:\n{question}\n\nAnswer in 3 parts: 1) Short summary 2) Reasoning citing chart facts 3) Practical guidance (timing if any)."

        # call Groq LLM (free) - requires GROQ_API_KEY env
        # groq_api_key = os.environ.get("GROQ_API_KEY")
        groq_api_key = "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"
        if not groq_api_key:
            return jsonify({"error":"GROQ_API_KEY not set in environment"}), 500

        client = Groq(api_key=groq_api_key)
        # create chat completion
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # change model if desired/available
            messages=[
                {"role":"system","content":system},
                {"role":"user","content":user_prompt}
            ],
            temperature=0.6,
            max_tokens=800
        )

        answer = resp.choices[0].message.content

        # store chat in session memory
        SESSION_STORE[session_id]["chats"].append({
            "ts": datetime.utcnow().isoformat(),
            "user": question,
            "bot": answer
        })

        # return only the answer
        return jsonify({
            "status": 200,
            "answer": answer,
            "disclaimer": "Astrological guidance only — not a substitute for professional advice."
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":"ai_ask failed","detail":str(e)}), 500

# ----------------------------
# get chat history for a session
# ----------------------------
@app.route('/chat-history', methods=['GET'])
def chat_history():
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"error":"session_id required"}), 400
    if session_id not in SESSION_STORE:
        return jsonify({"error":"invalid session_id"}), 404
    return jsonify({
        "session_id": session_id,
        "created_at": SESSION_STORE[session_id]["created_at"],
        "chats": SESSION_STORE[session_id]["chats"]
    })

# ----------------------------
# run
# ----------------------------
if __name__ == "__main__":
    app.run(port=5002, debug=True)
