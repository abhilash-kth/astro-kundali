from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
from skyfield.api import load, Topos
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pytz
from math import degrees
import swisseph as swe

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def format_final_degree(deg: float) -> str:
    """
    Convert a decimal degree value (e.g., 23.62) to D° M' S" string (e.g., 23° 37' 12").
    """
    whole_degrees = int(deg)
    minutes_float = (deg - whole_degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60)
    if seconds == 60:
        seconds = 0
        minutes += 1
    if minutes == 60:
        minutes = 0
        whole_degrees += 1
    return f"{whole_degrees}° {minutes}' {seconds}"

# Dasha order and years
DASHA_ORDER = ['Ketu', 'Venus', 'Sun', 'Moon', 'Mars', 'Rahu', 'Jupiter', 'Saturn', 'Mercury']
DASHA_YEARS = {
    'Ketu': 7,
    'Venus': 20,
    'Sun': 6,
    'Moon': 10,
    'Mars': 7,
    'Rahu': 18,
    'Jupiter': 16,
    'Saturn': 19,
    'Mercury': 17
}

# Load planetary data
eph = load('de421.bsp')
planets = {
    'Sun': eph['sun'],
    'Moon': eph['moon'],
    'Mercury': eph['mercury'],
    'Venus': eph['venus'],
    'Mars': eph['mars'],
    'Jupiter': eph['jupiter barycenter'],
    'Saturn': eph['saturn barycenter']
}

# Mapping of Sanskrit Rashis to English names
RASHI_TRANSLATION = {
    'Mesha': 'Aries',
    'Vrishabha': 'Taurus',
    'Mithuna': 'Gemini',
    'Karka': 'Cancer',
    'Simha': 'Leo',
    'Kanya': 'Virgo',
    'Tula': 'Libra',
    'Vrishchika': 'Scorpio',
    'Dhanu': 'Sagittarius',
    'Makara': 'Capricorn',
    'Kumbha': 'Aquarius',
    'Meena': 'Pisces'
}

# Mapping of Rashis to their numbers
ZODIAC_TO_NUMBER = {
    'Aries': 1,
    'Taurus': 2,
    'Gemini': 3,
    'Cancer': 4,
    'Leo': 5,
    'Virgo': 6,
    'Libra': 7,
    'Scorpio': 8,
    'Sagittarius': 9,
    'Capricorn': 10,
    'Aquarius': 11,
    'Pisces': 12
}

# Mapping of Rashis and their lords (using English names)
rashis = {
    'Aries': {'lord': 'Mars'},
    'Taurus': {'lord': 'Venus'},
    'Gemini': {'lord': 'Mercury'},
    'Cancer': {'lord': 'Moon'},
    'Leo': {'lord': 'Sun'},
    'Virgo': {'lord': 'Mercury'},
    'Libra': {'lord': 'Venus'},
    'Scorpio': {'lord': 'Mars'},
    'Sagittarius': {'lord': 'Jupiter'},
    'Capricorn': {'lord': 'Saturn'},
    'Aquarius': {'lord': 'Saturn'},
    'Pisces': {'lord': 'Jupiter'}
}

# Nakshatras and their Lords
nakshatras = [
    ('Ashwini', 'Ketu', 0), ('Bharani', 'Venus', 13.20), ('Krittika', 'Sun', 26.40),
    ('Rohini', 'Moon', 40), ('Mrigashira', 'Mars', 53.20), ('Ardra', 'Rahu', 66.40),
    ('Punarvasu', 'Jupiter', 80), ('Pushya', 'Saturn', 93.20), ('Ashlesha', 'Mercury', 106.40),
    ('Magha', 'Ketu', 120), ('Purva Phalguni', 'Venus', 133.20), ('Uttara Phalguni', 'Sun', 146.40),
    ('Hasta', 'Moon', 160), ('Chitra', 'Mars', 173.20), ('Swati', 'Rahu', 186.40),
    ('Vishakha', 'Jupiter', 200), ('Anuradha', 'Saturn', 213.20), ('Jyeshtha', 'Mercury', 226.40),
    ('Mula', 'Ketu', 240), ('Purva Ashadha', 'Venus', 253.20), ('Uttara Ashadha', 'Sun', 266.40),
    ('Shravana', 'Moon', 280), ('Dhanishta', 'Mars', 293.20), ('Shatabhisha', 'Rahu', 306.40),
    ('Purva Bhadrapada', 'Jupiter', 320), ('Uttara Bhadrapada', 'Saturn', 333.20), ('Revati', 'Mercury', 346.40)
]

def convert_divisional_charts_to_numbers(charts):
    """
    Convert zodiac signs in divisional charts to their corresponding numbers
    """
    return {
        chart_type: ZODIAC_TO_NUMBER[sign]
        for chart_type, sign in charts.items()
    }

def get_nakshatra(longitude):
    nak_span = 13.333333333333334  # 360/27
    nakshatra_index = int(longitude / nak_span)
    return nakshatras[nakshatra_index]

def get_house_from_rashi(rashi, lagna_rashi):
    fixed_rashi_order = [
        'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
        'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces'
    ]
    return fixed_rashi_order.index(rashi) + 1

def calculate_planetary_states(planet, rashi, degrees_in_rashi, speed, sun_position=None):
    retro = False
    combust = False
    status = "Neutral"

    if speed < 0:
        retro = True

    if sun_position is not None and planet != 'Sun':
        if abs(degrees_in_rashi - sun_position) < 8:
            combust = True

    # Exaltation and Debilitation states
    if planet == 'Sun':
        status = "Exalted" if rashi == "Aries" else "Neutral"
    elif planet == 'Moon':
        status = "Exalted" if rashi == "Taurus" else "Debilitated" if rashi == "Scorpio" else "Neutral"
    elif planet == 'Mars':
        status = "Exalted" if rashi == "Capricorn" else "Debilitated" if rashi == "Cancer" else "Neutral"
    elif planet == 'Mercury':
        status = "Exalted" if rashi == "Virgo" else "Debilitated" if rashi == "Pisces" else "Neutral"
    elif planet == 'Jupiter':
        status = "Exalted" if rashi == "Cancer" else "Debilitated" if rashi == "Capricorn" else "Neutral"
    elif planet == 'Venus':
        status = "Exalted" if rashi == "Pisces" else "Debilitated" if rashi == "Virgo" else "Neutral"
    elif planet == 'Saturn':
        status = "Exalted" if rashi == "Libra" else "Debilitated" if rashi == "Aries" else "Neutral"
    # Add rules for new planets
    elif planet == 'Neptune':
        status = "Exalted" if rashi == "Pisces" else "Debilitated" if rashi == "Virgo" else "Neutral"
    elif planet == 'Uranus':
        status = "Exalted" if rashi == "Aquarius" else "Debilitated" if rashi == "Leo" else "Neutral"
    elif planet == 'Pluto':
        status = "Exalted" if rashi == "Scorpio" else "Debilitated" if rashi == "Taurus" else "Neutral"

    return {'retro': retro, 'combust': combust, 'status': status}

def calculate_house_positions(jd, lat, lon):
    flags = swe.FLG_SWIEPH
    hsys = b'W'  # Whole Sign system
    cusps, asc_mc = swe.houses_ex(jd, lat, lon, hsys, flags)
    return list(cusps), asc_mc[0]

def calculate_d2(total_degrees, planet=None):
    """
    Classical Parashara D2 (Hora) chart:
    - Odd Rashis: 0-15° = Leo, 15-30° = Cancer
    - Even Rashis: 0-15° = Cancer, 15-30° = Leo
    """
    base_rashi = int(total_degrees / 30)  # 0-based index
    degree_in_rashi = total_degrees % 30
    is_odd_rashi = (base_rashi % 2 == 0)  # 0-based index, so even index means odd rashi

    # Leo = 4, Cancer = 3 (0-based: Aries=0, Taurus=1, Gemini=2, Cancer=3, Leo=4, ...)
    if is_odd_rashi:
        # Odd: 0-15° Leo, 15-30° Cancer
        final_rashi = 4 if degree_in_rashi < 15 else 3
    else:
        # Even: 0-15° Cancer, 15-30° Leo
        final_rashi = 3 if degree_in_rashi < 15 else 4

    fixed_rashi_order = [
        'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
        'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces'
    ]
    return fixed_rashi_order[final_rashi]

def calculate_d4(total_degrees):
    base_rashi = int(total_degrees / 30)
    degree_in_rashi = total_degrees % 30
    quarter = int(degree_in_rashi / 7.5)

    final_rashi_num = (base_rashi + (quarter * 3)) % 12

    fixed_rashi_order = [
        'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
        'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces'
    ]

    return fixed_rashi_order[final_rashi_num]

def calculate_d9(total_degrees, is_ascendant=False):
    """
    Calculate D9 (Navamsa) chart position
    For odd signs: Start from same sign
    For even signs: Start from 9th sign
    Then count forward by navamsa number
    """
    base_rashi = int(total_degrees / 30)
    degree_in_rashi = total_degrees % 30
    navamsa = int(degree_in_rashi / 3.333333)  # 30/9 = 3.333333

    is_odd_sign = (base_rashi % 2 == 0)  # 0-based index, so even index means odd sign

    if is_odd_sign:
        start_rashi = base_rashi
    else:
        start_rashi = (base_rashi + 8) % 12  # 9th sign (8 in 0-based index)

    final_rashi = (start_rashi + navamsa) % 12

    fixed_rashi_order = [
        'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
        'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces'
    ]

    return fixed_rashi_order[final_rashi]

def calculate_d10(total_degrees):
    base_rashi = int(total_degrees / 30)
    degree_in_rashi = total_degrees % 30
    division = int(degree_in_rashi / 3)

    is_odd_sign = (base_rashi % 2 == 0)

    if is_odd_sign:
        start_rashi = base_rashi
    else:
        start_rashi = (base_rashi + 8) % 12

    final_rashi_num = (start_rashi + division) % 12

    fixed_rashi_order = [
        'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
        'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces'
    ]

    return fixed_rashi_order[final_rashi_num]

def calculate_d60(total_degrees, planet=None):
    """
    Calculate D60 (Shashtiamsa) chart position
    For movable signs (Aries, Cancer, Libra, Capricorn): Start from same sign
    For fixed signs (Taurus, Leo, Scorpio, Aquarius): Start from 5th sign
    For dual signs (Gemini, Virgo, Sagittarius, Pisces): Start from 9th sign
    Then count forward by shashtiamsa number
    """
    base_rashi = int(total_degrees / 30)
    degree_in_rashi = total_degrees % 30
    shashtiamsa = int(degree_in_rashi / 0.5)  # 30/60 = 0.5

    rashi_type = base_rashi % 3  # 0: movable, 1: fixed, 2: dual

    if rashi_type == 0:  # Movable signs
        start_rashi = base_rashi
    elif rashi_type == 1:  # Fixed signs
        start_rashi = (base_rashi + 4) % 12  # 5th sign
    else:  # Dual signs
        start_rashi = (base_rashi + 8) % 12  # 9th sign

    # Calculate zodiac rounds and remaining divisions
    zodiac_rounds = shashtiamsa // 5
    remaining_divisions = shashtiamsa % 5

    final_rashi = (start_rashi + zodiac_rounds + remaining_divisions) % 12

    fixed_rashi_order = [
        'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
        'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces'
    ]

    return fixed_rashi_order[final_rashi]

def solar_longitude(jd):
    """Solar longitude at given instant (julian day) jd"""
    data = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)
    return data[0][0]   # Access the longitude value from the tuple

def lunar_longitude(jd):
    """Lunar longitude at given instant (julian day) jd"""
    data = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)
    return data[0][0]   # Access the longitude value from the tuple

def calculate_tithi_yog_karan(sun_longitude, moon_longitude, julian_day, lat, lon, tz):
    """
    Calculate Tithi, Yog, and Karan based on Sun and Moon longitudes using drik-panchanga logic
    """
    # Calculate lunar phase (moon - sun)
    moon_phase = (moon_longitude - sun_longitude) % 360

    # Calculate Tithi (1/30th of lunar month)
    tithi = moon_phase / 12
    tithi_number = int(tithi) + 1  # Adding 1 because tithi starts from 1

    # Calculate Yog (combination of Sun and Moon longitudes)
    yog = (sun_longitude + moon_longitude) % 360
    yog_number = int(yog / 13.333333) + 1  # 360/27 = 13.333333

    # Calculate Karan (half of a tithi)
    # Each tithi is divided into two karanas
    # First 7 karanas repeat 8 times, last 4 karanas appear once
    karan_degrees = moon_phase / 6  # Each karana is 6 degrees
    karan_number = int(karan_degrees) % 11 + 1  # 11 karanas in total

    # Tithi names
    tithi_names = [
        "Shukla Pratipada", "Shukla Dwitiya", "Shukla Tritiya", "Shukla Chaturthi", "Shukla Panchami",
        "Shukla Shashthi", "Shukla Saptami", "Shukla Ashtami", "Shukla Navami", "Shukla Dashami",
        "Shukla Ekadashi", "Shukla Dwadashi", "Shukla Trayodashi", "Shukla Chaturdashi", "Purnima",
        "Krishna Pratipada", "Krishna Dwitiya", "Krishna Tritiya", "Krishna Chaturthi", "Krishna Panchami",
        "Krishna Shashthi", "Krishna Saptami", "Krishna Ashtami", "Krishna Navami", "Krishna Dashami",
        "Krishna Ekadashi", "Krishna Dwadashi", "Krishna Trayodashi", "Krishna Chaturdashi", "Amavasya"
    ]

    # Yog names
    yog_names = [
        "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana",
        "Atiganda", "Sukarma", "Dhriti", "Shula", "Ganda",
        "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra",
        "Siddhi", "Vyatipata", "Variyan", "Parigha", "Shiva",
        "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma",
        "Indra", "Vaidhriti"
    ]

    # Karan names - First 7 repeat 8 times, last 4 appear once
    karan_names = [
        "Bava", "Balava", "Kaulava", "Taitila", "Garija",
        "Vanija", "Visti", "Shakuni", "Chatushpada", "Naga",
        "Kimstughna"
    ]

    # Calculate end times using Swiss Ephemeris
    def calculate_end_time(start_jd, target_angle, is_tithi=True):
        offsets = [0.25, 0.5, 0.75, 1.0]
        if is_tithi:
            # For tithi, we track moon-sun difference
            angles = [(lunar_longitude(start_jd + t) - solar_longitude(start_jd + t)) % 360 for t in offsets]
        else:
            # For yoga, we track moon+sun sum
            angles = [(lunar_longitude(start_jd + t) + solar_longitude(start_jd + t)) % 360 for t in offsets]

        # Use inverse Lagrange interpolation to find end time
        x = offsets
        y = angles
        approx_end = inverse_lagrange(x, y, target_angle)
        return (start_jd + approx_end - julian_day) * 24 + tz

    # Calculate tithi end time
    tithi_end_angle = tithi_number * 12
    tithi_end_time = calculate_end_time(julian_day, tithi_end_angle, True)

    # Calculate yoga end time
    yoga_end_angle = yog_number * 13.333333
    yoga_end_time = calculate_end_time(julian_day, yoga_end_angle, False)

    # Calculate karana end time
    karana_end_angle = karan_number * 6
    karana_end_time = calculate_end_time(julian_day, karana_end_angle, True)

    return {
        "tithi": {
            "number": tithi_number,
            "name": tithi_names[tithi_number - 1],
            "degrees": round(tithi % 1 * 12, 2),  # Remaining degrees in current tithi
            "end_time": round(tithi_end_time, 2)  # End time in hours from midnight
        },
        "yog": {
            "number": yog_number,
            "name": yog_names[yog_number - 1],
            "degrees": round(yog % 13.333333, 2),  # Remaining degrees in current yog
            "end_time": round(yoga_end_time, 2)  # End time in hours from midnight
        },
        "karan": {
            "number": karan_number,
            "name": karan_names[karan_number - 1],  # 11 karans repeat
            "degrees": round(karan_degrees % 1 * 6, 2),  # Remaining degrees in current karan
            "end_time": round(karana_end_time, 2)  # End time in hours from midnight
        }
    }

def inverse_lagrange(x, y, ya):
    """Given two lists x and y, find the value of x = xa when y = ya, i.e., f(xa) = ya"""
    assert(len(x) == len(y))
    total = 0
    for i in range(len(x)):
        numer = 1
        denom = 1
        for j in range(len(x)):
            if j != i:
                numer *= (ya - y[j])
                denom *= (y[i] - y[j])
        total += numer * x[i] / denom
    return total

def unwrap_angles(angles):
    """Add 360 to those elements in the input list so that all elements are sorted in ascending order."""
    result = angles.copy()
    for i in range(1, len(angles)):
        if result[i] < result[i-1]:
            result[i] += 360
    return result

def calculate_avakhada_details(moon_longitude, nakshatra):
    """
    Calculate Avakhada details based on Moon's position and Nakshatra
    """
    # Get moon sign (rashi)
    moon_sign_index = int(moon_longitude / 30)
    moon_sign_sanskrit = list(RASHI_TRANSLATION.keys())[moon_sign_index]
    moon_sign_english = RASHI_TRANSLATION[moon_sign_sanskrit]

    # Varna (Class / Caste Logic) - Based on Rashi (Moon Sign)
    varna_rashi_map = {
        'Mesha': 'Kshatriya', 'Simha': 'Kshatriya', 'Dhanu': 'Kshatriya',
        'Vrishabha': 'Vaishya', 'Kanya': 'Vaishya', 'Makara': 'Vaishya',
        'Mithuna': 'Shudra', 'Tula': 'Shudra', 'Kumbha': 'Shudra',
        'Karka': 'Brahmin', 'Vrishchika': 'Brahmin', 'Meena': 'Brahmin'
    }

    # Vashya (Controllability / Influence) - Based on Rashi (Moon Sign)
    vashya_rashi_map = {
        'Mesha': 'Chatushpad', 'Vrishabha': 'Chatushpad', 'Dhanu': 'Manav',
        'Mithuna': 'Dwi-swabhav', 'Kanya': 'Dwi-swabhav',
        'Karka': 'Jalchar', 'Makara': 'Jalchar', 'Meena': 'Jalchar',
        'Simha': 'Vanachari',
        'Tula': 'Manav', 'Kumbha': 'Manav',
        'Vrishchika': 'Keet'
    }

    # Yoni (Animal nature)
    yoni_map = {
        'Ashwini': 'Horse', 'Bharani': 'Elephant', 'Krittika': 'Goat',
        'Rohini': 'Serpent', 'Mrigashira': 'Serpent', 'Ardra': 'Dog',
        'Punarvasu': 'Cat', 'Pushya': 'Goat', 'Ashlesha': 'Cat',
        'Magha': 'Rat', 'Purva Phalguni': 'Rat', 'Uttara Phalguni': 'Cow',
        'Hasta': 'Buffalo', 'Chitra': 'Tiger', 'Swati': 'Buffalo',
        'Vishakha': 'Tiger', 'Anuradha': 'Deer', 'Jyeshtha': 'Hare',
        'Mula': 'Dog', 'Purva Ashadha': 'Monkey', 'Uttara Ashadha': 'Mongoose',
        'Shravana': 'Monkey', 'Dhanishta': 'Lion', 'Shatabhisha': 'Horse',
        'Purva Bhadrapada': 'Lion', 'Uttara Bhadrapada': 'Cow', 'Revati': 'Elephant'
    }

    # Yoni to Yunja mapping
    yoni_to_yunja = {
        'Horse': 'Ugra', 'Elephant': 'Mridu', 'Goat': 'Mridu',
        'Serpent': 'Ugra', 'Dog': 'Ugra', 'Cat': 'Mridu',
        'Rat': 'Madhya', 'Cow': 'Mridu', 'Buffalo': 'Madhya',
        'Tiger': 'Madhya', 'Deer': 'Mridu', 'Hare': 'Mridu',
        'Monkey': 'Ugra', 'Mongoose': 'Mridu', 'Lion': 'Ugra'
    }

    # Gan (Deva, Manushya, Rakshasa)
    gan_map = {
        'Ashwini': 'Deva', 'Bharani': 'Manushya', 'Krittika': 'Rakshasa',
        'Rohini': 'Manushya', 'Mrigashira': 'Deva', 'Ardra': 'Manushya',
        'Punarvasu': 'Deva', 'Pushya': 'Deva', 'Ashlesha': 'Rakshasa',
        'Magha': 'Rakshasa', 'Purva Phalguni': 'Manushya', 'Uttara Phalguni': 'Manushya',
        'Hasta': 'Deva', 'Chitra': 'Rakshasa', 'Swati': 'Deva',
        'Vishakha': 'Rakshasa', 'Anuradha': 'Deva', 'Jyeshtha': 'Rakshasa',
        'Mula': 'Rakshasa', 'Purva Ashadha': 'Manushya', 'Uttara Ashadha': 'Manushya',
        'Shravana': 'Deva', 'Dhanishta': 'Rakshasa', 'Shatabhisha': 'Rakshasa',
        'Purva Bhadrapada': 'Manushya', 'Uttara Bhadrapada': 'Manushya', 'Revati': 'Deva'
    }

    # Nadi (Adi, Madhya, Antya)
    nadi_map = {
    'Ashwini': 'Adi', 'Ardra': 'Adi', 'Uttara Phalguni': 'Adi', 'Hasta': 'Adi', 'Mula': 'Adi',
    'Punarvasu': 'Adi', 'Jyeshtha': 'Adi', 'Purva Bhadrapada': 'Adi', 'Shatabhisha': 'Adi',

    'Bharani': 'Madhya', 'Pushya': 'Madhya', 'Mrigashira': 'Madhya', 'Chitra': 'Madhya', 'Purva Phalguni': 'Madhya',
    'Purva Ashadha': 'Madhya', 'Anuradha': 'Madhya', 'Uttara Bhadrapada': 'Madhya', 'Dhanishta': 'Madhya',

    'Rohini': 'Antya', 'Ashlesha': 'Antya', 'Krittika': 'Antya', 'Swati': 'Antya', 'Uttara Ashadha': 'Antya',
    'Vishakha': 'Antya', 'Revati': 'Antya', 'Magha': 'Antya', 'Shravana': 'Antya'
}

    # Calculate charan (quarter)
    charan = int((moon_longitude % 13.333333) / 3.333333) + 1

    # Calculate yunja based on yoni (animal nature)
    yoni = yoni_map[nakshatra]
    yunja = yoni_to_yunja.get(yoni, 'Madhya')  # Default to Madhya if mapping not found

    # Calculate tatva (element)
    tatva_map = {
        'Ashwini': 'Earth', 'Bharani': 'Water', 'Krittika': 'Fire',
        'Rohini': 'Earth', 'Mrigashira': 'Water', 'Ardra': 'Fire',
        'Punarvasu': 'Earth', 'Pushya': 'Water', 'Ashlesha': 'Fire',
        'Magha': 'Earth', 'Purva Phalguni': 'Water', 'Uttara Phalguni': 'Fire',
        'Hasta': 'Earth', 'Chitra': 'Water', 'Swati': 'Fire',
        'Vishakha': 'Air',
        'Anuradha': 'Water', 'Jyeshtha': 'Fire',
        'Mula': 'Earth', 'Purva Ashadha': 'Water', 'Uttara Ashadha': 'Fire',
        'Shravana': 'Earth', 'Dhanishta': 'Water', 'Shatabhisha': 'Fire',
        'Purva Bhadrapada': 'Earth', 'Uttara Bhadrapada': 'Water', 'Revati': 'Fire'
    }

    # Name alphabet
    name_alphabet_map = {
        'Ashwini': 'Chu', 'Bharani': 'Lee', 'Krittika': 'Lu',
        'Rohini': 'Lo', 'Mrigashira': 'Se', 'Ardra': 'Su',
        'Punarvasu': 'De', 'Pushya': 'Du', 'Ashlesha': 'Tha',
        'Magha': 'Ma', 'Purva Phalguni': 'Mo', 'Uttara Phalguni': 'Ta',
        'Hasta': 'Ti', 'Chitra': 'Tu', 'Swati': 'Te',
        'Vishakha': 'To', 'Anuradha': 'Na', 'Jyeshtha': 'Ni',
        'Mula': 'Nu', 'Purva Ashadha': 'Ne', 'Uttara Ashadha': 'No',
        'Shravana': 'Ya', 'Dhanishta': 'Yi', 'Shatabhisha': 'Yu',
        'Purva Bhadrapada': 'Ye', 'Uttara Bhadrapada': 'Yo', 'Revati': 'Ba'
    }

    # Calculate paya (metal)
    paya_map = {
        'Ashwini': 'Gold', 'Bharani': 'Silver', 'Krittika': 'Copper',
        'Rohini': 'Gold', 'Mrigashira': 'Silver', 'Ardra': 'Copper',
        'Punarvasu': 'Gold', 'Pushya': 'Silver', 'Ashlesha': 'Copper',
        'Magha': 'Gold', 'Purva Phalguni': 'Silver', 'Uttara Phalguni': 'Copper',
        'Hasta': 'Gold', 'Chitra': 'Silver', 'Swati': 'Copper',
        'Vishakha': 'Silver',
        'Anuradha': 'Silver', 'Jyeshtha': 'Copper',
        'Mula': 'Gold', 'Purva Ashadha': 'Silver', 'Uttara Ashadha': 'Copper',
        'Shravana': 'Gold', 'Dhanishta': 'Silver', 'Shatabhisha': 'Copper',
        'Purva Bhadrapada': 'Gold', 'Uttara Bhadrapada': 'Silver', 'Revati': 'Copper'
    }

    return {
        "varna": varna_rashi_map.get(moon_sign_sanskrit, "Unknown"),
        "vashya": vashya_rashi_map.get(moon_sign_sanskrit, "Unknown"),
        "yoni": yoni_map[nakshatra],
        "gan": gan_map[nakshatra],
        "nadi": nadi_map[nakshatra],
        "sign": moon_sign_sanskrit,
        "sign_lord": rashis[moon_sign_english]['lord'],
        "nakshatra_lord": nakshatras[int(moon_longitude / 13.333333)][1],
        "charan": charan,
        "yunja": yunja,
        "tatva": tatva_map[nakshatra],
        "name_alphabet": name_alphabet_map[nakshatra],
        "paya": paya_map[nakshatra]
    }

def calculate_extended_planetary_info(julian_day, lat, lon, tz):
    swe.set_sid_mode(swe.SIDM_KRISHNAMURTI)
    ayanamsa = swe.get_ayanamsa(julian_day)

    # Calculate sunrise and sunset times
    sun_times = calculate_sunrise_sunset(julian_day, lat, lon, tz)

    houses, ascendant = calculate_house_positions(julian_day, lat, lon)
    ascendant = (ascendant - ayanamsa) % 360
    houses = [(h - ayanamsa) % 360 for h in houses]

    sanskrit_lagna_rashi = list(RASHI_TRANSLATION.keys())[int(ascendant / 30)]
    lagna_rashi = RASHI_TRANSLATION[sanskrit_lagna_rashi]

    planetary_info = {}

    sun_flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    sun_info = swe.calc_ut(julian_day, swe.SUN, sun_flags)
    sun_longitude = (sun_info[0][0] - ayanamsa) % 360
    sun_position = sun_longitude % 30

    # Calculate Moon's position for Tithi, Yog, Karan
    moon_flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    moon_info = swe.calc_ut(julian_day, swe.MOON, moon_flags)
    moon_longitude = (moon_info[0][0] - ayanamsa) % 360

    # Calculate Tithi, Yog, Karan
    panchang_details = calculate_tithi_yog_karan(sun_longitude, moon_longitude, julian_day, lat, lon, tz)

    # Calculate Avakhada details
    moon_nakshatra = get_nakshatra(moon_longitude)[0]
    avakhada_details = calculate_avakhada_details(moon_longitude, moon_nakshatra)

    def get_planet_info(planet_num, planet, julian_day, ayanamsa):
        flags = swe.FLG_SWIEPH | swe.FLG_SPEED
        planet_info = swe.calc_ut(julian_day, planet_num, flags)

        longitude = (planet_info[0][0] - ayanamsa) % 360
        speed = planet_info[0][3]

        rashi_index = int(longitude / 30)
        sanskrit_rashi = list(RASHI_TRANSLATION.keys())[rashi_index]
        rashi = RASHI_TRANSLATION[sanskrit_rashi]
        degrees_in_rashi = longitude % 30

        nakshatra_info = get_nakshatra(longitude)
        states = calculate_planetary_states(planet, rashi, degrees_in_rashi, speed, sun_position)

        return {
            'longitude': longitude,
            'rashi': rashi,
            'rashi_lord': rashis[rashi]['lord'],
            'nakshatra': nakshatra_info[0],
            'nakshatra_lord': nakshatra_info[1],
            'degrees': round(degrees_in_rashi, 2),
            'total_degrees': round(longitude, 2),
            'retro': states['retro'],
            'combust': states['combust'],
            'status': states['status']

        }

    planet_mappings = [
        ('Sun', swe.SUN), ('Moon', swe.MOON), ('Mars', swe.MARS),
        ('Mercury', swe.MERCURY), ('Venus', swe.VENUS),
        ('Jupiter', swe.JUPITER), ('Saturn', swe.SATURN),
        # Add these new planets
        ('Neptune', swe.NEPTUNE),
        ('Uranus', swe.URANUS),
        ('Pluto', swe.PLUTO)
    ]

    for planet, planet_num in planet_mappings:
        planet_info = get_planet_info(planet_num, planet, julian_day, ayanamsa)
        rashi = planet_info['rashi']
        house_position = get_house_from_rashi(rashi, lagna_rashi)

        total_degrees = planet_info['total_degrees']
        divisional_charts = {
            'D2': calculate_d2(total_degrees, planet),
            'D4': calculate_d4(total_degrees),
            'D9': calculate_d9(total_degrees),
            'D10': calculate_d10(total_degrees),
            'D60': calculate_d60(total_degrees, planet)
        }

        # Convert divisional charts to numbers
        divisional_charts = convert_divisional_charts_to_numbers(divisional_charts)

        planetary_info[planet] = {
            'rashi': rashi,
            'rashi_lord': planet_info['rashi_lord'],
            'nakshatra': planet_info['nakshatra'],
            'nakshatra_lord': planet_info['nakshatra_lord'],
            'degrees': planet_info['degrees'],
            'finaldegree': format_final_degree(planet_info['degrees']),
            'total_degrees': planet_info['total_degrees'],
            'retro': planet_info['retro'],
            'combust': planet_info['combust'],
            'status': planet_info['status'],
            'house': house_position,
            'divisional_charts': divisional_charts
        }

    # Calculate Rahu and Ketu
    rahu_info = get_planet_info(swe.MEAN_NODE, 'Rahu', julian_day, ayanamsa)
    rahu_house = get_house_from_rashi(rahu_info['rashi'], lagna_rashi)

    # Calculate divisional charts for Rahu
    rahu_divisional_charts = {
        'D2': calculate_d2(rahu_info['total_degrees'], 'Rahu'),
        'D4': calculate_d4(rahu_info['total_degrees']),
        'D9': calculate_d9(rahu_info['total_degrees']),
        'D10': calculate_d10(rahu_info['total_degrees']),
        'D60': calculate_d60(rahu_info['total_degrees'], 'Rahu')
    }

    # Convert Rahu's divisional charts to numbers
    rahu_divisional_charts = convert_divisional_charts_to_numbers(rahu_divisional_charts)

    planetary_info['Rahu'] = {
        'rashi': rahu_info['rashi'],
        'rashi_lord': rashis[rahu_info['rashi']]['lord'],
        'nakshatra': rahu_info['nakshatra'],
        'nakshatra_lord': rahu_info['nakshatra_lord'],
        'degrees': rahu_info['degrees'],
        'finaldegree': format_final_degree(rahu_info['degrees']),
        'total_degrees': rahu_info['total_degrees'],
        'retro': True,
        'combust': False,
        'status': 'Neutral',
        'house': rahu_house,
        'divisional_charts': rahu_divisional_charts
    }

    # Calculate Ketu position
    ketu_longitude = (rahu_info['total_degrees'] + 180) % 360
    ketu_rashi_index = int(ketu_longitude / 30)
    sanskrit_ketu_rashi = list(RASHI_TRANSLATION.keys())[ketu_rashi_index]
    ketu_rashi = RASHI_TRANSLATION[sanskrit_ketu_rashi]
    ketu_house = get_house_from_rashi(ketu_rashi, lagna_rashi)
    ketu_degrees = ketu_longitude % 30
    ketu_nakshatra = get_nakshatra(ketu_longitude)

    # Calculate divisional charts for Ketu
    ketu_divisional_charts = {
        'D2': calculate_d2(ketu_longitude, 'Ketu'),
        'D4': calculate_d4(ketu_longitude),
        'D9': calculate_d9(ketu_longitude),
        'D10': calculate_d10(ketu_longitude),
        'D60': calculate_d60(ketu_longitude, 'Ketu')
    }

    # Convert Ketu's divisional charts to numbers
    ketu_divisional_charts = convert_divisional_charts_to_numbers(ketu_divisional_charts)

    planetary_info['Ketu'] = {
        'rashi': ketu_rashi,
        'rashi_lord': rashis[ketu_rashi]['lord'],
        'nakshatra': ketu_nakshatra[0],
        'nakshatra_lord': ketu_nakshatra[1],
        'degrees': round(ketu_degrees, 2),
        'finaldegree': format_final_degree(ketu_degrees),
        'total_degrees': round(ketu_longitude, 2),
        'retro': True,
        'combust': False,
        'status': 'Neutral',
        'house': ketu_house,
        'divisional_charts': ketu_divisional_charts
    }

    # Ascendant Details
    sanskrit_ascendant_rashi = list(RASHI_TRANSLATION.keys())[int(ascendant / 30)]
    ascendant_rashi = RASHI_TRANSLATION[sanskrit_ascendant_rashi]
    ascendant_nakshatra = get_nakshatra(ascendant)

    # Calculate divisional charts for Ascendant
    ascendant_divisional_charts = {
        'D2': calculate_d2(ascendant, 'Ascendant'),
        'D4': calculate_d4(ascendant),
        'D9': calculate_d9(ascendant, is_ascendant=True),
        'D10': calculate_d10(ascendant),
        'D60': calculate_d60(ascendant, 'Ascendant')
    }

    # Convert Ascendant's divisional charts to numbers
    ascendant_divisional_charts = convert_divisional_charts_to_numbers(ascendant_divisional_charts)

    planetary_info['Ascendant'] = {
        'rashi': ascendant_rashi,
        'rashi_lord': rashis[ascendant_rashi]['lord'],
        'degrees': round(ascendant % 30, 2),
        'finaldegree': format_final_degree(ascendant % 30),
        'total_degrees': round(ascendant, 2),
        'nakshatra': ascendant_nakshatra[0],
        'nakshatra_lord': ascendant_nakshatra[1],
        'house': get_house_from_rashi(ascendant_rashi, lagna_rashi),
        'divisional_charts': ascendant_divisional_charts
    }

    # After planetary_info is built and contains all planets including 'Ascendant'
    ascendant_house = planetary_info['Ascendant']['house']

    for planet, pdata in planetary_info.items():
        # Calculate relative house number
        # Ascendant is always 1
        if planet == 'Ascendant':
            pdata['houseNumber'] = 1
        else:
            planet_house = pdata['house']
            pdata['houseNumber'] = ((planet_house - ascendant_house + 12) % 12) + 1

    return planetary_info, panchang_details, avakhada_details, sun_times

def calculate_sunrise_sunset(julian_day, lat, lon, tz):
    """
    Calculate sunrise and sunset times using a simpler approach
    """
    # Convert degrees to float to ensure we're working with proper numbers
    lat_float = float(lat)
    lon_float = float(lon)

    # Create a day-long array of times to check for sunrise/sunset
    sunrise_hour = 6.0  # Approximate sunrise time
    sunset_hour = 18.0  # Approximate sunset time

    # Calculate approximate sunrise/sunset Julian days
    sunrise_jd = julian_day + (sunrise_hour - tz) / 24.0
    sunset_jd = julian_day + (sunset_hour - tz) / 24.0

    # Convert times to local time
    sunrise_time = sunrise_hour
    sunset_time = sunset_hour

    return {
        "sunrise": round(sunrise_time, 2),
        "sunset": round(sunset_time, 2)
    }

nakshatra_length = 13.333333  # 360 / 27

def get_nakshatra_by_longitude(moon_longitude):
    for i in range(len(nakshatras)):
        start_deg = nakshatras[i][2]
        end_deg = nakshatras[i + 1][2] if i + 1 < len(nakshatras) else 360
        if start_deg <= moon_longitude < end_deg:
            return nakshatras[i]
    return nakshatras[-1]  # fallback

def add_astrotalk_years(start_date, years_float):
    """
    Add (possibly fractional) years to a datetime based on actual days.

    - Converts years to days using 365.25 days per year (approx solar year)
    - Adds that many days to the given start_date
    """
    days_to_add = int(round(years_float * 365.25))
    return start_date + timedelta(days=days_to_add)

def generate_mahadasha(birth_date, start_lord, balance_years):
    timeline = []
    start_idx = DASHA_ORDER.index(start_lord)
    current_date = birth_date

    # Format dates as: DD-MMM-YYYY (e.g., 15-Dec-2002)
    def format_astrotalk_date(date):
        if date == birth_date:
            return "Birth"
        return date.strftime("%d-%b-%Y")

    # First partial dasha
    end_date = add_astrotalk_years(current_date, balance_years)

    timeline.append({
        "planet": start_lord,
        "start_date": format_astrotalk_date(current_date),
        "end_date": format_astrotalk_date(end_date),
        "years": round(balance_years, 2)
    })
    current_date = end_date

    # Next full dashas
    for i in range(1, len(DASHA_ORDER)):
        planet = DASHA_ORDER[(start_idx + i) % len(DASHA_ORDER)]
        duration = DASHA_YEARS[planet]
        end_date = add_astrotalk_years(current_date, duration)

        timeline.append({
            "planet": planet,
            "start_date": format_astrotalk_date(current_date),
            "end_date": format_astrotalk_date(end_date),
            "years": duration
        })
        current_date = end_date

    return timeline

def calculate_mahadasha_periods(birth_date, moon_longitude):
    """
    Calculate Vimshottari Mahadasha periods based on Moon total longitude.

    Logic (as per custom rules):
    1. Each Nakshatra span = 13.333°
    2. nakshatra_index = floor(moon_longitude / 13.333)
    3. Identify Nakshatra & Lord from `nakshatras` list using this index
    4. nakshatra_start = nakshatra_index × 13.333
    5. remaining_deg = 13.333 − (moon_longitude − nakshatra_start)
    6. balance_years = (remaining_deg / 13.333) × full_dasha_years_of_lord
    7. After balance completes, follow fixed Vimshottari order:
       Ketu → Venus → Sun → Moon → Mars → Mercury → Jupiter → Saturn → Rahu
    """
    # 1–2. Basic nakshatra span and index
    nak_span = 13.333
    nakshatra_index = int(moon_longitude / nak_span)

    # Ensure index is within bounds (0–26)
    if nakshatra_index < 0:
        nakshatra_index = 0
    elif nakshatra_index >= len(nakshatras):
        nakshatra_index = len(nakshatras) - 1

    # 3. Identify Nakshatra & Lord
    nakshatra_name, start_lord, _ = nakshatras[nakshatra_index]

    # 5–6. Remaining degrees in current nakshatra and balance years
    nakshatra_start = nakshatra_index * nak_span
    remaining_deg = nak_span - (moon_longitude - nakshatra_start)

    # Guard against any numerical edge issues
    if remaining_deg < 0:
        remaining_deg = 0
    elif remaining_deg > nak_span:
        remaining_deg = nak_span

    full_dasha_years = DASHA_YEARS[start_lord]
    balance_years = (remaining_deg / nak_span) * full_dasha_years

    # Debug logs for verification
    print(f"🌕 Moon Longitude: {moon_longitude}")
    print(f"📌 Nakshatra Index: {nakshatra_index}")
    print(f"📌 Nakshatra: {nakshatra_name}")
    print(f"🌟 Lord: {start_lord}")
    print(f"🔢 Nakshatra start degree: {nakshatra_start}")
    print(f"🔢 Remaining degrees in nakshatra: {remaining_deg}")
    print(f"⏳ Balance Mahadasha years at birth: {balance_years}")

    # Generate mahadasha timeline according to the fixed Vimshottari order
    return generate_mahadasha(birth_date, start_lord, balance_years)

# --- Request/Response Models ---
class KundliRequest(BaseModel):
    date_of_birth: str
    time_of_birth: str
    latitude: float
    longitude: float

# --- FastAPI Route ---
@app.post("/generate_kundli")
async def generate_kundli(request: KundliRequest):
    try:
        birth_date = request.date_of_birth
        birth_time = request.time_of_birth
        lat = request.latitude
        lon = request.longitude

        # Local time conversion to UTC
        ist = pytz.timezone('Asia/Kolkata')
        dt = datetime.strptime(f"{birth_date} {birth_time}", "%Y-%m-%d %H:%M")
        dt = ist.localize(dt)
        utc_time = dt.astimezone(pytz.UTC)

        julian_day = swe.julday(utc_time.year, utc_time.month, utc_time.day,
                               utc_time.hour + utc_time.minute/60.0)

        # Get timezone offset in hours
        tz_offset = dt.utcoffset().total_seconds() / 3600

        planetary_info, panchang_details, avakhada_details, sun_times = calculate_extended_planetary_info(julian_day, lat, lon, tz_offset)

        # Calculate Mahadasha periods
        moon_longitude = planetary_info['Moon']['total_degrees']
        mahadasha_periods = calculate_mahadasha_periods(dt, moon_longitude)

        # Build vedic4 section with Purusharthas; populate dharma using Ascendant's nakshatra lord
        vedic4 = {"dharma": {}, "artha": {}, "kama": {}, "moksha": {}}
        asc_nakshatra_lord = planetary_info.get('Ascendant', {}).get('nakshatra_lord')
        if asc_nakshatra_lord and asc_nakshatra_lord in planetary_info:
            lord_obj = planetary_info[asc_nakshatra_lord]
            vedic4["dharma"] = {
                "Asc_nakshatra_lord": asc_nakshatra_lord,
                "houseNumber": lord_obj.get("houseNumber"),
                "nakshatra": lord_obj.get("nakshatra")
            }

        return {
            "meta": {
                "status": "success",
                "message": "Kundli generated successfully",
                "ayanamsa": {
                    "value": swe.get_ayanamsa(julian_day),
                    "type": "Krishnamurti"
                }
            },
            "panchang": panchang_details,
            "avakhada": avakhada_details,
            "sun_times": sun_times,
            "kundli": planetary_info,
            "mahadasha": mahadasha_periods,
            "vedic4": vedic4
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- Run the app ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
