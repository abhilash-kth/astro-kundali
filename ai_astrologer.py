# ai_astrologer.py
from flask import Flask, request, jsonify
import os
import swisseph as swe
from datetime import datetime
import math
import openai   # pip install openai

app = Flask(__name__)

# ---- reuse your ephe path and PLANETS config ---
swe.set_ephe_path(r'D:\python\astro-py\ephe')

PLANETS = {
    'Sun': swe.SUN, 'Moon': swe.MOON, 'Mercury': swe.MERCURY, 'Venus': swe.VENUS,
    'Mars': swe.MARS, 'Jupiter': swe.JUPITER, 'Saturn': swe.SATURN,
    'Rahu': swe.MEAN_NODE, 'Ketu': swe.MEAN_NODE
}

# Helper utilities (shortened)
def normalize_angle(a): return a % 360.0
def sign_index_from_degree(deg): return int(deg // 30)
def degree_in_sign(deg): return deg % 30.0
def get_house_for_rasi(rasi_planet, asc_deg):
    asc_rasi = sign_index_from_degree(asc_deg) + 1
    return ((rasi_planet - asc_rasi) % 12) + 1

def detect_aspects(planet_positions, orb_major=8):
    """planet_positions: dict name->global_degree"""
    aspects = []
    names = list(planet_positions.keys())
    for i in range(len(names)):
        for j in range(i+1, len(names)):
            a = planet_positions[names[i]]
            b = planet_positions[names[j]]
            diff = abs((a - b + 180) % 360 - 180)
            # basic aspects:
            if diff <= 8: aspects.append((names[i], names[j], 'conjunction', diff))
            if abs(diff - 180) <= 8: aspects.append((names[i], names[j], 'opposition', diff))
            if abs(diff - 120) <= 6: aspects.append((names[i], names[j], 'trine', diff))
            if abs(diff - 90) <= 6: aspects.append((names[i], names[j], 'square', diff))
            if abs(diff - 60) <= 5: aspects.append((names[i], names[j], 'sextile', diff))
    return aspects

# Build a compact "fact list" from kundali JSON
def build_fact_list(kundali_json):
    facts = []
    planet_positions = {}
    asc_deg = kundali_json['kundali']['Ascendant']
    for pname in ['Sun','Moon','Mars','Mercury','Jupiter','Venus','Saturn','Rahu','Ketu']:
        gdeg = float(kundali_json['kundali'].get(pname))
        planet_positions[pname] = gdeg
        rasi_no = sign_index_from_degree(gdeg) + 1
        local_deg = degree_in_sign(gdeg)
        facts.append(f"{pname}: {gdeg:.2f}° (sign #{rasi_no}, {local_deg:.2f}° in sign)")
    # Houses (optional): include asc and houses summary
    facts.append(f"Ascendant: {asc_deg:.2f}° (sign #{sign_index_from_degree(asc_deg)+1})")
    # aspects
    aspects = detect_aspects(planet_positions)
    facts.append("Aspects: " + ", ".join([f"{a}-{b} {typ} (orb {orb:.2f}°)" for a,b,typ,orb in aspects]) or "No major aspects")
    return "\n".join(facts), planet_positions, asc_deg

# LLM call builder
def build_prompt(user_question, facts_text, planet_positions, asc_deg):
    system = (
        "You are an experienced Vedic astrologer. Use only the facts provided. "
        "Be careful: use probabilistic phrasing, cite the chart features used, "
        "and never give medical/legal/financial advice. If asked such, refuse politely."
    )
    user = (
        "Chart facts:\n"
        f"{facts_text}\n\n"
        "User question:\n"
        f"{user_question}\n\n"
        "Answer structure:\n"
        "1) Short summary (1-2 lines)\n"
        "2) Reasoning: refer to exact facts (e.g., 'Mars in 7th house, square Saturn (orb 3°)')\n"
        "3) Practical suggestions and timing notes (mention dasa/transit if relevant). Keep tone compassionate.\n"
    )
    return system, user

# Endpoint: receives full kundali JSON or the same params to compute one
@app.route('/ai-ask', methods=['POST'])
def ai_ask():
    payload = request.json
    # Accept either: {"kundali": {...}, "question":"..."} OR the birth fields + question
    if 'kundali' in payload:
        kundali_json = payload['kundali_source'] if 'kundali_source' in payload else payload
        # if client passed nested structure, adapt accordingly
        kundali_json = payload
    else:
        return jsonify({"error":"Please POST a kundali json or use existing /kundali endpoint first."}), 400

    question = payload.get('question') or payload.get('q') or ""
    if not question:
        return jsonify({"error":"Please include field 'question'."}), 400

    # Build facts
    facts_text, planet_positions, asc_deg = build_fact_list(kundali_json)

    # Build prompts
    system, user_prompt = build_prompt(question, facts_text, planet_positions, asc_deg)

    # call LLM (OpenAI example)
    openai.api_key = os.environ.get("OPENAI_API_KEY")
    if not openai.api_key:
        return jsonify({"error":"OPENAI_API_KEY not set"}), 500

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # replace with chosen model
            messages=[
                {"role":"system","content":system},
                {"role":"user","content":user_prompt}
            ],
            temperature=0.6,
            max_tokens=700
        )
        answer = resp['choices'][0]['message']['content'].strip()
    except Exception as e:
        return jsonify({"error":"LLM call failed","detail":str(e)}), 500

    # Basic post-processing: prepend used facts snippet and a short disclaimer
    disclaimer = ("Note: This is astrological guidance for reflection only. "
                  "Not a substitute for professional advice.")
    return jsonify({
        "status":200,
        "answer": answer,
        "facts_sent": facts_text,
        "disclaimer": disclaimer
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)
