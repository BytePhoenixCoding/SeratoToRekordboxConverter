major_key_conversion = {
    "C": "8B",
    "C#": "3B", "Db": "3B",
    "D": "10B",
    "D#": "5B", "Eb": "5B",
    "E": "12B",
    "F": "7B",
    "F#": "2B", "Gb": "2B",
    "G": "9B",
    "G#": "4B", "Ab": "4B",
    "A": "11B",
    "A#": "6B", "Bb": "6B",
    "B": "1B"
}

minor_key_conversion = {
    "Cm": "5A",
    "C#m": "12A", "Dbm": "12A",
    "Dm": "7A",
    "D#m": "2A", "Ebm": "2A",
    "Em": "9A",
    "Fm": "4A",
    "F#m": "11A", "Gbm": "11A",
    "Gm": "6A",
    "G#m": "1A", "Abm": "1A",
    "Am": "8A",
    "A#m": "3A", "Bbm": "3A",
    "Bm": "10A"
}

def convert_key_to_camelot(key) -> str:
    if isinstance(key, bytes):
        key = key.decode("utf-8", errors="replace")

    key = key.strip()

    if not key:
        return "Unknown"

    if "minor" in key.lower():
        base = key.lower().replace("minor", "").strip().upper()
        conv_key = base + "m"

    else:
        conv_key = key

    if conv_key in minor_key_conversion:
        return minor_key_conversion[conv_key]

    elif conv_key in major_key_conversion:
        return major_key_conversion[conv_key]

    cap = conv_key.capitalize()

    if cap in major_key_conversion:
        return major_key_conversion[cap]

    elif cap in minor_key_conversion:
        return minor_key_conversion[cap]

    return conv_key