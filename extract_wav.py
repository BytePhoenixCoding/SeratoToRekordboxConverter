import os
import re
import struct
import base64
import logging
from pathlib import Path
import io
import json
import sys
from collections import namedtuple
import mutagen
from mutagen.id3 import GEOB 

from utils import major_key_conversion, minor_key_conversion, convert_key_to_camelot


NonTerminalBeatgridMarker = namedtuple("NonTerminalBeatgridMarker", ["position", "beats_till_next_marker"])
TerminalBeatgridMarker = namedtuple("TerminalBeatgridMarker", ["position", "bpm"])

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def parse_serato_hot_cues(base64_data):
    if not base64_data:
        logging.debug("No hot cue data provided.")
        return []

    if isinstance(base64_data, str):
        base64_data = base64_data.encode('utf-8')

    clean_data = re.sub(rb'[^a-zA-Z0-9+/=]', b'', base64_data)

    padding_needed = 4 - (len(clean_data) % 4)
    if padding_needed != 4: 
        clean_data += b'=' * padding_needed

    try:
        data = base64.b64decode(clean_data)
        logging.debug(f"Decoded hot cue data length: {len(data)} bytes.")
    except Exception as e:
        logging.error(f"Base64 decode error for hot cue data: {e}")
        return []

    index = 0
    hot_cues = []

    while index < len(data):
        null_byte_pos = data[index:].find(b'\x00')
        if null_byte_pos == -1:
            logging.debug("No more null bytes found to indicate entry type separator.")
            break 

        entry_type_bytes = data[index : index + null_byte_pos]
        index += null_byte_pos + 1 

        try:
            entry_type = entry_type_bytes.decode('utf-8')

        except UnicodeDecodeError:
            logging.warning(f"Could not decode entry type starting at index {index - null_byte_pos - 1}. Skipping remaining data.")

            break 

        len_bytes = data[index:index+4]
        if len(len_bytes) < 4:
            #logging.warning(f"Not enough data left for entry length (expected 4 bytes) at index {index}. Remaining: {len(data) - index} bytes. Stopping.")
            break 

        try:
            entry_len = struct.unpack('>I', len_bytes)[0]

        except struct.error as e:
             logging.warning(f"Struct unpack error for entry length at index {index}: {e}. Data: {len_bytes.hex()}. Stopping.")
             break 

        index += 4 

        if index + entry_len > len(data):
            logging.warning(f"Declared entry length ({entry_len}) exceeds remaining data ({len(data) - index} bytes) at index {index}. Stopping.")
            break 

        entry_data = data[index : index + entry_len]

        if entry_type == 'CUE':
            min_cue_len = 12 

            if len(entry_data) >= min_cue_len:
                try:
                    hotcue_index = entry_data[1]
                    position_ms = struct.unpack('>I', entry_data[2:6])[0]
                    color_data = entry_data[7:10]
                    label_bytes = entry_data[12:]
                    label = label_bytes.rstrip(b"\x00").decode("utf-8", errors="replace")

                    if len(color_data) == 3:
                         color_hex = "#{:02X}{:02X}{:02X}".format(color_data[0], color_data[1], color_data[2])
                    else:
                         color_hex = "#000000" 

                    hot_cues.append({
                        'index': hotcue_index,
                        'position_ms': position_ms,
                        'color': color_hex,
                        'name': label
                    })

                except Exception as e:
                    logging.warning(f"Error parsing CUE entry data at index {index - entry_len}: {e}. Entry data length: {entry_len}. Skipping this cue.")

            else:
                logging.warning(f"CUE entry data at index {index - entry_len} is too short ({len(entry_data)} bytes, expected at least {min_cue_len}). Skipping.")

        index += entry_len

    return hot_cues

def parse_beatgrid_markers(fp):
    fp.seek(0)

    try:
        version_bytes = fp.read(2)
        if len(version_bytes) < 2: 
            raise ValueError("Not enough data for BeatGrid version.")
        version = struct.unpack("BB", version_bytes)

        if version != (0x01, 0x00):
            logging.warning(f"Unsupported BeatGrid version: {version}. Expected (1, 0). Attempting to parse anyway, results may be incorrect.")

        num_markers_bytes = fp.read(4)

        if len(num_markers_bytes) < 4: 
            raise ValueError("Not enough data for BeatGrid number of markers.")
        num_markers = struct.unpack(">I", num_markers_bytes)[0]

        markers = []

        for i in range(num_markers):
            pos_bytes = fp.read(4)

            if len(pos_bytes) < 4: 
                raise ValueError(f"Not enough data for marker {i} position (expected 4 bytes).")

            pos = struct.unpack(">f", pos_bytes)[0]
            data_bytes = fp.read(4)

            if len(data_bytes) < 4: 
                raise ValueError(f"Not enough data for marker {i} data (expected 4 bytes).")

            if i == num_markers - 1:
                try:
                    bpm = struct.unpack(">f", data_bytes)[0]
                    markers.append(TerminalBeatgridMarker(pos, bpm))

                except struct.error:
                     logging.warning(f"Could not unpack float for terminal marker BPM at index {i}. Data: {data_bytes.hex()}. Skipping this marker.")
                     pass 

            else:
                try:
                    beats_till_next_marker = struct.unpack(">I", data_bytes)[0]
                    markers.append(NonTerminalBeatgridMarker(pos, beats_till_next_marker))

                except struct.error:
                     logging.warning(f"Could not unpack int for non-terminal marker beats_till_next at index {i}. Data: {data_bytes.hex()}. Skipping this marker and subsequent ones as chain is broken.")

                     break 

        fp.read(1) 
        return markers

    except ValueError as ve:
        logging.error(f"BeatGrid data incomplete or malformed: {ve}")
        return []

    except Exception as e:
        logging.error(f"Unexpected error parsing BeatGrid data structure: {e}", exc_info=True)
        return []

def get_beatgrid(tagfile):
    if not tagfile:
        logging.error("Invalid tagfile object passed to get_beatgrid.")
        return {"markers": {"non_terminal": [], "terminal": None}}

    try:
        tag = tagfile.tags.get("GEOB:Serato BeatGrid")

        if tag is None:
             logging.debug('Beatgrid tag "GEOB:Serato BeatGrid" not found.')
             return {"markers": {"non_terminal": [], "terminal": None}}

        markers = parse_beatgrid_markers(io.BytesIO(tag.data))

    except Exception as e:

        logging.error(f"An error occurred while trying to get beatgrid tag: {e}", exc_info=True)
        return {"markers": {"non_terminal": [], "terminal": None}}

    result = {
        "markers": {
            "non_terminal": [],
            "terminal": None
        }
    }

    if not markers:
        return result

    non_terminal = []
    terminal = None

    if markers:
        if isinstance(markers[-1], TerminalBeatgridMarker):
            terminal = markers[-1]
            non_terminal = markers[:-1]
        else:
             logging.warning("Last parsed marker is not a terminal marker type. Beatgrid structure may be unexpected.")
             non_terminal = markers 

    result["markers"]["non_terminal"] = [{
        "position": m.position,
        "beats_till_next_marker": m.beats_till_next_marker
    } for m in non_terminal]

    if terminal:
         result["markers"]["terminal"] = {
             "position": terminal.position,
             "bpm": terminal.bpm
         }

    return result

def extract_metadata(input_file: str) -> dict:
    audio_metadata = {
        "title": "Unknown",
        "artist": "Unknown",
        "bpm": 0.0,
        "key": "Unknown",
        "duration_sec": 0.0
    }
    hot_cues = []
    beatgrid_data = {"markers": {"non_terminal": [], "terminal": None}} 

    try:
        tagfile = mutagen.File(input_file)

        if tagfile is None:
            logging.warning(f"Unable to open or read tags from {input_file} using mutagen.")

            return {
                "metadata": audio_metadata,
                "hot_cues": [],
                "beatgrid": beatgrid_data
            }

        tags = tagfile.tags if tagfile.tags is not None else {}
        audio_metadata["title"] = str(tags.get("TIT2", tags.get("©nam", "Unknown")))
        audio_metadata["artist"] = str(tags.get("TPE1", tags.get("©art", "Unknown")))
        bpm_tag = tags.get("TBPM", tags.get("BPM")) 

        if bpm_tag:
             try:

                 bpm_value = None
                 if hasattr(bpm_tag, 'text') and bpm_tag.text:
                      bpm_str = str(bpm_tag.text[0]).strip()
                      bpm_str_cleaned = re.sub(r'[^0-9.]', '', bpm_str)

                      if bpm_str_cleaned:
                        bpm_value = float(bpm_str_cleaned)

                 elif isinstance(bpm_tag, (int, float)):
                      bpm_value = float(bpm_tag)

                 if bpm_value is not None:
                     audio_metadata["bpm"] = bpm_value
                 else:
                     logging.warning(f"Could not extract valid BPM value from tag(s) '{bpm_tag}' for {input_file}.")

             except (ValueError, TypeError) as e:
                 logging.warning(f"Could not convert BPM tag '{bpm_tag}' to float for {input_file}: {e}.")
                 audio_metadata["bpm"] = 0.0

        key_tag = tags.get("TKEY")
        key = "Unknown"

        if key_tag and hasattr(key_tag, 'text') and key_tag.text:
             key = str(key_tag.text[0]).strip()

        else:
             key_tag_initialkey = tags.get("initialkey") 
             if key_tag_initialkey and hasattr(key_tag_initialkey, 'text') and key_tag_initialkey.text:
                 key = str(key_tag_initialkey.text[0]).strip()

        audio_metadata["key"] = convert_key_to_camelot(key)

        if tagfile.info and hasattr(tagfile.info, 'length'):
            audio_metadata["duration_sec"] = round(tagfile.info.length, 3)
        else:
            logging.warning(f"Could not get duration from file info for {input_file}.")

        geob_hotcues_tag = tags.get("GEOB:Serato Markers2")
        if geob_hotcues_tag and isinstance(geob_hotcues_tag, GEOB):
            try:
                hot_cues = parse_serato_hot_cues(geob_hotcues_tag.data)

            except Exception as e:
                logging.error(f"Error reading Serato Markers2 (hot cues) from {input_file}: {e}", exc_info=True)

        beatgrid_data = get_beatgrid(tagfile)

    except FileNotFoundError:
        logging.error(f"File not found: {input_file}")

        return {
            "metadata": audio_metadata,
            "hot_cues": [],
            "beatgrid": beatgrid_data
        }
    except Exception as e:
        logging.error(f"An unexpected error occurred while processing {input_file}: {e}", exc_info=True)

        return {
            "metadata": audio_metadata,
            "hot_cues": [],
            "beatgrid": beatgrid_data
        }

    return {
        "metadata": audio_metadata,
        "hot_cues": hot_cues,
        "beatgrid": beatgrid_data
    }