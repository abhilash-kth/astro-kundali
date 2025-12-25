from flask import Flask, request, jsonify
import swisseph as swe
from datetime import datetime, timedelta
import math

app = Flask(__name__)
swe.set_ephe_path(r'D:\python\astro-py\ephe')
swe.set_sid_mode(swe.SIDM_LAHIRI)  # Set Lahiri Ayanamsa

# Planet constants used by swisseph
PLANETS = {
    'Sun': swe.SUN,
    'Moon': swe.MOON,
    'Mercury': swe.MERCURY,
    'Venus': swe.VENUS,
    'Mars': swe.MARS,
    'Jupiter': swe.JUPITER,
    'Saturn': swe.SATURN,
    'Rahu': swe.MEAN_NODE,
    'Ketu': swe.TRUE_NODE  # Use TRUE_NODE for Ketu
}

# Short names, full names, and abbreviation mapping
PLANET_META = {
    'Sun': ('Su', 'Sun'),
    'Moon': ('Mo', 'Moon'),
    'Mercury': ('Me', 'Mercury'),
    'Venus': ('Ve', 'Venus'),
    'Mars': ('Ma', 'Mars'),
    'Jupiter': ('Ju', 'Jupiter'),
    'Saturn': ('Sa', 'Saturn'),
    'Rahu': ('Ra', 'Rahu'),
    'Ketu': ('Ke', 'Ketu'),
    'Asc': ('As', 'Ascendant')
}

ZODIAC = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

# Rasi lords (Vedic)
ZODIAC_LORD = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter"
}

# Nakshatra names and their lords
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]

# Nakshatra lords
NAKSHATRA_LORDS = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu",
    "Jupiter", "Saturn", "Mercury", "Ketu", "Venus", "Sun",
    "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu",
    "Jupiter", "Saturn", "Mercury"
]

# Vimshottari dasa order and durations (years)
VIM_DASA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
VIM_DASA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17}

# Helper utilities
def normalize_angle(a):
    a = a % 360.0
    if a < 0:
        a += 360.0
    return a

def angle_diff(a, b):
    d = abs((a - b + 180) % 360 - 180)
    return d

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
    return idx + 1, name, pada, lord

def get_house_for_rasi(rasi_planet, asc_deg):
    asc_rasi = sign_index_from_degree(asc_deg) + 1
    house = ((rasi_planet - asc_rasi) % 12) + 1
    return house

def compute_vimshottari_dasa(moon_nak_index, birth_dt):
    start_dasa = NAKSHATRA_LORDS[moon_nak_index - 1]
    order = VIM_DASA_ORDER
    if start_dasa in order:
        i = order.index(start_dasa)
        seq = order[i:] + order[:i]
    else:
        seq = order[:]
    return ">".join(seq[:3])

def compute_current_dasa(birth_dt):
    # Placeholder for current dasa calculation
    return "Ra>Ra>Ra"

@app.route('/kundali', methods=['POST'])
def generate_kundali():
    data = request.json
    try:
        dob_str = data['dob']
        time_str = data.get('time', '00:00')
        lat = float(data['lat'])
        lon = float(data['lon'])
        tz = float(data.get('tz', 5.5))
        dt = datetime.strptime(f"{dob_str} {time_str}", "%Y-%m-%d %H:%M")
        jd = swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60.0 - tz)
        cusps, ascmc = swe.houses(jd, lat, lon, b'P')
        ascendant_deg = ascmc[0]
        planet_results = {}

        for pname, pcode in PLANETS.items():
            pos1, flags1 = swe.calc_ut(jd, pcode)
            pos2, flags2 = swe.calc_ut(jd + 1.0 / 24.0, pcode)
            lon1 = float(pos1[0])
            lon2 = float(pos2[0])
            diff = (lon2 - lon1)
            if diff > 180:
                diff -= 360
            if diff < -180:
                diff += 360
            deg_per_day = diff / (1.0 / 24.0)
            retro = deg_per_day < 0
            gdeg = normalize_angle(lon1)
            rasi_idx = sign_index_from_degree(gdeg)
            rasi_no = rasi_idx + 1
            zodiac = ZODIAC[rasi_idx]
            local_deg = degree_in_sign(gdeg)
            progress_pct = (local_deg / 30.0) * 100.0
            nak_no, nak_name, nak_pada, nak_lord = get_nakshatra_info(gdeg)

            OWN_SIGNS = {
                'Sun': ['Leo'],
                'Moon': ['Cancer'],
                'Mars': ['Aries', 'Scorpio'],
                'Mercury': ['Gemini', 'Virgo'],
                'Jupiter': ['Sagittarius', 'Pisces'],
                'Venus': ['Taurus', 'Libra'],
                'Saturn': ['Capricorn', 'Aquarius'],
                'Rahu': [], 'Ketu': []
            }
            own = pname in OWN_SIGNS and zodiac in OWN_SIGNS[pname]

            is_combust = False
            if pname not in ('Rahu', 'Ketu', 'Moon'):
                if 'Sun' not in planet_results:
                    sun_pos, _ = swe.calc_ut(jd, swe.SUN)
                    sun_deg_tmp = float(sun_pos[0])
                else:
                    sun_deg_tmp = planet_results['Sun']['global_degree']
                if angle_diff(gdeg, sun_deg_tmp) < 8.5:
                    is_combust = True

            if local_deg < 6:
                basic_avastha = "Bala"
            elif local_deg < 12:
                basic_avastha = "Kumara"
            elif local_deg < 18:
                basic_avastha = "Yuva"
            elif local_deg < 24:
                basic_avastha = "Vriddha"
            else:
                basic_avastha = "Mritya"

            ENEMIES = {
                'Sun': ['Saturn'], 'Moon': ['Saturn'], 'Mars': ['Venus'],
                'Mercury': [], 'Jupiter': [], 'Venus': ['Mars'], 'Saturn': ['Sun']
            }
            lord_status = "Neutral"
            if own:
                lord_status = "Benefic"
            if retro:
                lord_status = "Malefic" if not own else "Benefic"

            house_no = get_house_for_rasi(rasi_no, ascendant_deg)
            planet_results[pname] = {
                "name": PLANET_META[pname][0],
                "full_name": PLANET_META[pname][1],
                "local_degree": local_deg,
                "global_degree": gdeg,
                "progress_in_percentage": progress_pct,
                "rasi_no": rasi_no,
                "zodiac": zodiac,
                "house": house_no,
                "speed_radians_per_day": deg_per_day * math.pi / 180.0,
                "retro": retro,
                "nakshatra": nak_name,
                "nakshatra_lord": nak_lord,
                "nakshatra_pada": nak_pada,
                "nakshatra_no": nak_no,
                "zodiac_lord": ZODIAC_LORD.get(zodiac, "-"),
                "is_planet_set": own,
                "basic_avastha": basic_avastha,
                "is_combust": is_combust,
                "lord_status": lord_status
            }

        out = {}
        idx = 0
        asc_rasi_idx = sign_index_from_degree(ascendant_deg)
        asc_local_deg = degree_in_sign(ascendant_deg)
        asc_zodiac = ZODIAC[asc_rasi_idx]
        asc_info = {
            "name": "As",
            "full_name": "Ascendant",
            "local_degree": asc_local_deg,
            "global_degree": ascendant_deg,
            "progress_in_percentage": (asc_local_deg / 30.0) * 100.0,
            "rasi_no": asc_rasi_idx + 1,
            "zodiac": asc_zodiac,
            "house": 1,
            "nakshatra": get_nakshatra_info(ascendant_deg)[1],
            "nakshatra_lord": get_nakshatra_info(ascendant_deg)[3],
            "nakshatra_pada": get_nakshatra_info(ascendant_deg)[2],
            "nakshatra_no": get_nakshatra_info(ascendant_deg)[0],
            "zodiac_lord": ZODIAC_LORD.get(asc_zodiac, "-"),
            "is_planet_set": False,
            "lord_status": "-"
        }
        out[str(idx)] = asc_info
        idx += 1

        order = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]
        for p in order:
            pr = planet_results[p]
            entry = {
                "name": pr["name"],
                "full_name": pr["full_name"],
                "local_degree": pr["local_degree"],
                "global_degree": pr["global_degree"],
                "progress_in_percentage": pr["progress_in_percentage"],
                "rasi_no": pr["rasi_no"],
                "zodiac": pr["zodiac"],
                "house": pr["house"],
                "speed_radians_per_day": pr["speed_radians_per_day"],
                "retro": pr["retro"],
                "nakshatra": pr["nakshatra"],
                "nakshatra_lord": pr["nakshatra_lord"],
                "nakshatra_pada": pr["nakshatra_pada"],
                "nakshatra_no": pr["nakshatra_no"],
                "zodiac_lord": pr["zodiac_lord"],
                "is_planet_set": pr["is_planet_set"],
                "lord_status": pr["lord_status"],
                "basic_avastha": pr["basic_avastha"],
                "is_combust": pr["is_combust"]
            }
            out[str(idx)] = entry
            idx += 1

        moon_nak_idx = get_nakshatra_info(planet_results['Moon']['global_degree'])[0]
        birth_dasa = compute_vimshottari_dasa(moon_nak_idx, dt)
        current_dasa = compute_current_dasa(dt)

        lucky_gems = ["ruby"] if "Sun" in birth_dasa else ["emerald"]
        lucky_nums = [1] if "Sun" in birth_dasa else [3]
        lucky_colors = ["copper"] if "Sun" in birth_dasa else ["blue"]
        lucky_letters = ["B", "G"] if "Sun" in birth_dasa else ["C", "L"]

        ayan = swe.get_ayanamsa(jd)
        weekday = dt.strftime("%A")
        panchang = {
            "ayanamsa": ayan,
            "ayanamsa_name": "Lahiri",
            "day_of_birth": weekday,
            "day_lord": "Sun",
            "hora_lord": "Venus",
            "sunrise_at_birth": "-",
            "sunset_at_birth": "-",
            "tithi": "Dwitiya",
            "yoga": "Vyaghata",
            "karana": "Balava"
        }

        final_response = {
            "status": 200,
            "response": out
        }
        final_response["response"]["birth_dasa"] = birth_dasa
        final_response["response"]["current_dasa"] = current_dasa
        final_response["response"]["birth_dasa_time"] = dob_str
        final_response["response"]["current_dasa_time"] = datetime.utcnow().strftime("%d/%m/%Y")
        final_response["response"]["lucky_gem"] = lucky_gems
        final_response["response"]["lucky_num"] = lucky_nums
        final_response["response"]["lucky_colors"] = lucky_colors
        final_response["response"]["lucky_letters"] = lucky_letters
        final_response["response"]["lucky_name_start"] = ["Be", "Bo", "Ja", "Ji"] if "Sun" in birth_dasa else ["chu", "chae", "cho", "ia"]
        final_response["response"]["rasi"] = asc_info["zodiac"]
        final_response["response"]["nakshatra"] = asc_info["nakshatra"]
        final_response["response"]["nakshatra_pada"] = asc_info["nakshatra_pada"]
        final_response["response"]["panchang"] = panchang
        final_response["response"]["ghatka_chakra"] = {
            "rasi": "Leo",
            "tithi": ["4 (chaturthi)", "9 (navami)", "14 (chaturthi)"],
            "day": "Tuesday",
            "nakshatra": "Rohini",
            "tatva": "Vayu (Air)",
            "lord": "Saturn",
            "same_sex_lagna": "Aquarius",
            "opposite_sex_lagna": "Leo"
        }

        return jsonify(final_response)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
