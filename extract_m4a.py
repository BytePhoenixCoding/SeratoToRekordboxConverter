import base64
import io
import logging
import re
import struct
from pathlib import Path

from mutagen.mp4 import MP4
from mutagen.id3 import ID3

import m4a_beatgrid

# --- Key Conversion Dictionaries and Function ---

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
    # Ensure key is a string.
    if isinstance(key, bytes):
        key = key.decode("utf-8", errors="replace")
    key = key.strip()
    if not key:
        return "Unknown"
    # Normalize: if the key contains "minor", remove it and append "m".
    if "minor" in key.lower():
        base = key.lower().replace("minor", "").strip().upper()
        conv_key = base + "m"
    else:
        conv_key = key
    if conv_key in minor_key_conversion:
        return minor_key_conversion[conv_key]
    elif conv_key in major_key_conversion:
        return major_key_conversion[conv_key]
    # Fallback: try capitalizing the key
    cap = conv_key.capitalize()
    if cap in major_key_conversion:
        return major_key_conversion[cap]
    elif cap in minor_key_conversion:
        return minor_key_conversion[cap]
    return conv_key

# --- Hot Cue Parsing Functions ---

def read_null_terminated(fp: io.BytesIO) -> bytes:
    chunks = []
    while True:
        b = fp.read(1)
        if not b or b == b'\x00':
            break
        chunks.append(b)
    return b"".join(chunks)

def parse_cue_entry(entry_data: bytes) -> dict:
    if len(entry_data) < 13 or entry_data[0] != 0 or entry_data[6] != 0:
        #logging.warning("CUE entry does not match expected format.")
        return None
    index = entry_data[1]
    position_ms = struct.unpack(">I", entry_data[2:6])[0]
    r, g, b = entry_data[7:10]
    color = "#{:02X}{:02X}{:02X}".format(r, g, b)
    if struct.unpack(">H", entry_data[10:12])[0] != 0:
        logging.warning("Unexpected bytes in cue entry at positions 10-11.")
        return None
    label = entry_data[12:].split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    return {"index": index, "position_ms": position_ms, "color": color, "name": label}

def parse_markers_with_header(data: bytes) -> list:
    fp = io.BytesIO(data)
    version = fp.read(2)
    if struct.unpack("BB", version) != (1, 1):
        logging.error("Unexpected version header: %s", version.hex())
        return []
    _ = read_null_terminated(fp)  # discard header
    cues = []
    while True:
        marker_name_bytes = read_null_terminated(fp)
        if not marker_name_bytes:
            break  # no more markers
        marker_name = marker_name_bytes.decode("utf-8", errors="replace")
        len_bytes = fp.read(4)
        if len(len_bytes) < 4:
            break
        rec_len = struct.unpack(">I", len_bytes)[0]
        record_data = fp.read(rec_len)
        if marker_name == "CUE":
            cue = parse_cue_entry(record_data)
            if cue:
                cues.append(cue)
    return cues

def simple_parse_hot_cues(data: bytes) -> list:
    cues = []
    idx = 0
    total = len(data)
    while idx < total:
        nxt = data[idx:].find(b"\x00")
        if nxt == -1:
            break
        marker_name = data[idx:idx+nxt].decode("utf-8", errors="replace")
        idx += nxt + 1
        if idx + 4 > total:
            break
        rec_len = struct.unpack(">I", data[idx:idx+4])[0]
        idx += 4
        if marker_name == "CUE" and idx + rec_len <= total:
            rec = data[idx:idx+rec_len]
            cue = parse_cue_entry(rec)
            if cue:
                cues.append(cue)
        idx += rec_len
    return cues

def strip_mime_and_descriptor(data: bytes) -> bytes:
    fp = io.BytesIO(data)
    _ = read_null_terminated(fp)  # MIME
    _ = read_null_terminated(fp)  # Descriptor
    remainder = fp.read()
    logging.debug("After MIME stripping, remainder length: %d bytes", len(remainder))
    return remainder

def parse_serato_hot_cues(tag_data) -> list:
    if isinstance(tag_data, str):
        tag_data = tag_data.encode("utf-8")
    clean = tag_data.replace(b"\n", b"")
    clean = re.sub(rb"[^a-zA-Z0-9+/=]", b"", clean)
    if len(clean) % 4 != 0:
        clean += b"=" * ((4 - len(clean) % 4))
    try:
        outer_decoded = base64.b64decode(clean)
    except Exception as e:
        logging.error("Failed to decode outer GEOB data: %s", e)
        return []
    if outer_decoded.startswith(b"application/octet-stream"):
        outer_decoded = strip_mime_and_descriptor(outer_decoded)
    if outer_decoded.startswith(b"Serato Markers2"):
        _, _, outer_decoded = outer_decoded.partition(b"\x00")
        outer_decoded = outer_decoded.lstrip(b"\x00")
    try:
        ascii_str = outer_decoded.decode("ascii", errors="replace").strip()
        ascii_str = re.sub(r"\s+", "", ascii_str)
    except Exception as e:
        logging.error("Failed to convert payload to ASCII: %s", e)
        return []
    if len(ascii_str) < 2:
        logging.error("ASCII payload too short.")
        return []
    trimmed = ascii_str[2:]  # Remove first two characters
    pad = (-len(trimmed)) % 4
    if pad:
        trimmed += "=" * pad
    inner = None
    attempt = trimmed
    while len(attempt) > 0:
        try:
            inner = base64.b64decode(attempt)
            break
        except Exception:
            attempt = attempt[:-1]
    if inner is None:
        logging.error("Second base64 decode failed.")
        return []
    if inner.startswith(b"\x01\x01"):
        cues = parse_markers_with_header(inner)
        if not cues:
            cues = simple_parse_hot_cues(inner)
    else:
        cues = simple_parse_hot_cues(inner)
    return cues

# --- Metadata Extraction for Audio Files ---

def _extract_metadata(file_path: str) -> dict:
    results = {"metadata": {}, "hot_cues": [], "beatgrid":[]}
    track = Path(file_path)
    if not track.exists():
        logging.error("File not found: %s", file_path)
        return results

    results["beatgrid"] = m4a_beatgrid.get_beatgrid(file_path)

    candidates = []
    if track.suffix.lower() == ".m4a":
        audio = MP4(str(track))
        results["metadata"]["title"] = audio.get("\xa9nam", ["Unknown Title"])[0]
        results["metadata"]["artist"] = audio.get("\xa9ART", ["Unknown Artist"])[0]
        results["metadata"]["bpm"] = float(audio.get("tmpo", [0])[0]) if audio.get("tmpo") else 0.0
        # Check for several key tags, including the Apple iTunes one.
        classical_key = (audio.get("\xa9key", [None])[0] or
                         audio.get("----:com.serato:initialkey", [None])[0] or
                         audio.get("----:com.mixedinkey:initialkey", [None])[0] or
                         audio.get("----:com.apple.iTunes:initialkey", [None])[0] or
                         "Unknown")
        camelot_key = convert_key_to_camelot(classical_key) if classical_key != "Unknown" else "Unknown"
        results["metadata"]["key"] = camelot_key
        results["metadata"]["duration_sec"] = round(audio.info.length)
        candidates = ["----:com.serato:Markers2", "----:com.serato:markers_", "----:com.serato.dj:markersv2", "SERATO_MARKERS_V2"]

    # Try to find a GEOB tag that contains Serato marker data.
    for tag_key in candidates:
        tag_data = None
        if track.suffix.lower() == ".m4a":
            tag_data = audio.get(tag_key, [None])[0]
        else:
            for frame in audio.values():
                if frame.FrameID == "GEOB" and getattr(frame, "desc", "").lower().startswith("serato"):
                    tag_data = frame.data
                    break
        if tag_data:
            #results["geob_tags"].append({"tag": tag_key, "size": len(tag_data)})
            cues = parse_serato_hot_cues(tag_data)
            if cues:
                results["hot_cues"] = cues
                break  # Use the first tag with valid cues.
    return results

def extract_metadata(input_file: str) -> dict:
    res = _extract_metadata(input_file)

    return res