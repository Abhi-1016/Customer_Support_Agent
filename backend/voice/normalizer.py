import re
import datetime

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

ORDINAL_SUFFIXES = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth",
    16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth", 20: "twentieth",
    21: "twenty-first", 22: "twenty-second", 23: "twenty-third", 24: "twenty-fourth", 25: "twenty-fifth",
    26: "twenty-sixth", 27: "twenty-seventh", 28: "twenty-eighth", 29: "twenty-ninth", 30: "thirtieth",
    31: "thirty-first"
}

DIGIT_WORDS_EN = {
    '0': "zero", '1': "one", '2': "two", '3': "three", '4': "four",
    '5': "five", '6': "six", '7': "seven", '8': "eight", '9': "nine"
}

def _spell_id_digits(match: re.Match) -> str:
    prefix = match.group(1)
    dash = match.group(2) or " "
    digits = match.group(3)
    # Spell prefix letter by letter
    spelled_prefix = " ".join(list(prefix))
    # Spell digits one by one
    spelled_digits = " ".join(DIGIT_WORDS_EN.get(d, d) for d in digits)
    return f"{spelled_prefix}{dash}{spelled_digits}"

def _format_rupees(match: re.Match) -> str:
    raw_num = match.group(1).replace(",", "")
    try:
        val = int(raw_num)
        return f"{val} rupees"
    except ValueError:
        return f"{raw_num} rupees"

def _format_dollars(match: re.Match) -> str:
    raw_num = match.group(1).replace(",", "")
    try:
        val = int(raw_num)
        word = "dollar" if val == 1 else "dollars"
        return f"{val} {word}"
    except ValueError:
        return f"{raw_num} dollars"

def _format_iso_date(match: re.Match) -> str:
    year = int(match.group(1))
    month = int(match.group(2))
    day = int(match.group(3))
    try:
        dt = datetime.date(year, month, day)
        day_name = dt.strftime("%A")
        month_name = MONTH_NAMES[month - 1]
        day_ordinal = ORDINAL_SUFFIXES.get(day, f"{day}th")
        return f"{day_name}, {month_name} {day_ordinal}"
    except Exception:
        return match.group(0)

def tts_normalize(text: str, lang: str = "en-IN") -> str:
    """Normalizes text for Gnani TTS according to its input-formatting guide.

    - Order/Refund/Pickup/Ticket IDs (e.g. ORD-1001, REF-83921, PKP-A94B, TKT-9912) read letter-by-letter and digit-by-digit.
    - Currency symbols (₹, Rs, $) spoken naturally in words.
    - ISO dates (YYYY-MM-DD) converted to spoken dates like 'Friday, November fifteenth'.
    - Cleans extra spaces or technical formatting.
    """
    if not text:
        return ""

    normalized = text

    # Strip markdown markers
    normalized = re.sub(r'[*_`~#\[\]]', '', normalized)

    # Convert ISO dates (e.g. 2026-11-15)
    normalized = re.sub(r'\b(202\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b', _format_iso_date, normalized)

    # Convert Rupee amounts: ₹1,299 or Rs. 1299 or Rs 1299
    normalized = re.sub(r'(?:₹|Rs\.?\s*)([0-9,]+)', _format_rupees, normalized)

    # Convert Dollar amounts: $5 or $50
    normalized = re.sub(r'\$([0-9,]+)', _format_dollars, normalized)

    # Convert Order/Reference IDs: e.g. ORD-1001, REF-83921, PKP-9812, TKT-4412, SPHERE-ABCD-5
    normalized = re.sub(r'\b([A-Z]{2,6})(-| )([0-9A-Z]{3,8})\b', _spell_id_digits, normalized)

    # Clean double spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized

