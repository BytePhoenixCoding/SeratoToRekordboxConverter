import base64
import io
import logging
import re
import struct
from pathlib import Path
import binascii
import json

from mutagen.mp4 import MP4
from mutagen.id3 import ID3
import mutagen.mp4

from utils import major_key_conversion, minor_key_conversion, convert_key_to_camelot

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
        return None

    index = entry_data[1]
    position_ms = struct.unpack(">I", entry_data[2:6])[0]
    r, g, b = entry_data[7:10]
    color = "#{:02X}{:02X}{:02X}".format(r, g, b)

    if struct.unpack(">H", entry_data[10:12])[0] != 0:
        logging.warning("Unexpected bytes in cue entry at positions 10-11.")
        return None

    label = entry_data[12:].rstrip(b"\x00").decode("utf-8", errors="replace")

    return {"index": index, "position_ms": position_ms, "color": color, "name": label}

def parse_markers_with_header(data: bytes) -> list:
    fp = io.BytesIO(data)
    version = fp.read(2)

    if struct.unpack("BB", version) != (1, 1):
        logging.error("Unexpected version header: %s", version.hex())
        return []

    _ = read_null_terminated(fp)  
    cues = []

    while True:
        marker_name_bytes = read_null_terminated(fp)
        if not marker_name_bytes:
            break  

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
    _ = read_null_terminated(fp)  
    _ = read_null_terminated(fp)  
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

    trimmed = ascii_str[2:]  
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

def extract_metadata(file_path: str) -> dict:
    results = {"metadata": {}, "hot_cues": [], "beatgrid":[]}
    track = Path(file_path)

    if not track.exists():
        logging.error("File not found: %s", file_path)
        return results

    results["beatgrid"] = get_beatgrid(file_path)
    candidates = []

    if track.suffix.lower() == ".m4a":
        audio = MP4(str(track))
        results["metadata"]["title"] = audio.get("\xa9nam", ["Unknown Title"])[0]
        results["metadata"]["artist"] = audio.get("\xa9ART", ["Unknown Artist"])[0]
        results["metadata"]["bpm"] = float(audio.get("tmpo", [0])[0]) if audio.get("tmpo") else 0.0

        classical_key = (audio.get("\xa9key", [None])[0] or
                         audio.get("----:com.serato:initialkey", [None])[0] or
                         audio.get("----:com.mixedinkey:initialkey", [None])[0] or
                         audio.get("----:com.apple.iTunes:initialkey", [None])[0] or
                         "Unknown")

        camelot_key = convert_key_to_camelot(classical_key) if classical_key != "Unknown" else "Unknown"

        results["metadata"]["key"] = camelot_key
        results["metadata"]["duration_sec"] = round(audio.info.length, 3)

        candidates = ["----:com.serato:Markers2", "----:com.serato:markers_", "----:com.serato.dj:markersv2", "SERATO_MARKERS_V2"]

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
            cues = parse_serato_hot_cues(tag_data)
            sr = audio.info.sample_rate
            results["metadata"]["sample_rate"] = sr

            if cues:
                results["hot_cues"] = cues
                # adjust cue positions to account for AAC leading silence
                delay_ms = 2 * 1024 / sr * 1000      # ≈ 46.4 ms

                for cue in cues:
                    cue['position_ms'] += delay_ms

                results['hot_cues'] = cues
                break  

    return results

def decode_beatgrid(value):
    raw_bytes = bytes(value)
    cleaned = raw_bytes.replace(b'\n', b'')

    try:
        potential = cleaned[:-1]
        missing_padding = len(potential) % 4

        if missing_padding:
            potential += b'=' * (4 - missing_padding)

        decoded = base64.b64decode(potential, validate=True)

    except binascii.Error:
        missing_padding = len(cleaned) % 4

        if missing_padding:
            cleaned += b'=' * (4 - missing_padding)

        decoded = base64.b64decode(cleaned, validate=True)

    return decoded

def process_grid_data(grid_data):
    if len(grid_data) < 7:
        raise ValueError("Grid data is too short to contain header and footer.")

    header = grid_data[:6]
    marker_count = int.from_bytes(header[2:6], byteorder='big')
    expected_length = 6 + (marker_count * 8) + 1

    if len(grid_data) != expected_length:
        print(f"Warning: Decoded grid data length ({len(grid_data)}) does not match expected length ({expected_length}).")

    markers_block = grid_data[6:6 + marker_count * 8]
    markers = []

    if marker_count == 0:
        return markers

    elif marker_count == 1:
        if len(markers_block) < 8:
            raise ValueError("Insufficient data for terminal marker.")

        pos, bpm = struct.unpack(">ff", markers_block[:8])
        markers.append({
            "type": "terminal",
            "position": pos,
            "bpm": bpm
        })

    else:
        for i in range(marker_count - 1):
            offset = i * 8
            pos = struct.unpack(">f", markers_block[offset:offset+4])[0]
            beats_till_next = int.from_bytes(markers_block[offset+4:offset+8], byteorder='big')
            markers.append({
                "type": "non-terminal",
                "position": pos,
                "beats_till_next_marker": beats_till_next
            })

        offset = (marker_count - 1) * 8
        pos, bpm = struct.unpack(">ff", markers_block[offset:offset+8])
        markers.append({
            "type": "terminal",
            "position": pos,
            "bpm": bpm
        })

    return markers

def get_beatgrid(file_path):
    try:
        audio = mutagen.mp4.MP4(file_path)

    except Exception as e:
        raise RuntimeError(f"Error reading file '{file_path}': {e}")

    tags = audio.tags
    key = '----:com.serato.dj:beatgrid'

    if key not in tags:
        raise ValueError("Beatgrid tag not found.")

    beatgrid_entries = tags[key]

    for entry in beatgrid_entries:
        if not isinstance(entry, mutagen.mp4.MP4FreeForm):
            continue

        decoded = decode_beatgrid(entry)
        parts = decoded.split(b'\x00\x00', 1)

        if len(parts) < 2:
            raise ValueError("Could not find the double-null separator in the data.")

        data_part = parts[1]
        marker_str = b"Serato BeatGrid\x00"

        if not data_part.startswith(marker_str):
            raise ValueError("Marker string 'Serato BeatGrid\\x00' not found in data part.")

        grid_data = data_part[len(marker_str):]
        markers = process_grid_data(grid_data)
        non_terminal = []
        terminal = None

        for marker in markers:
            if marker["type"] == "terminal":
                terminal = { 
                    "position": marker["position"], 
                    "bpm": marker["bpm"]
                }

            else:
                non_terminal.append({
                    "position": marker["position"],
                    "beats_till_next_marker": marker["beats_till_next_marker"]
                })

        result = {
            "markers": {
                "non_terminal": non_terminal,
                "terminal": terminal
            }
        }
        return result

    raise ValueError("No valid beatgrid marker group found.")
