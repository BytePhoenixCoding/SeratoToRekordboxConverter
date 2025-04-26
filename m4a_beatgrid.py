import mutagen.mp4
import base64
import binascii
import struct
import json

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