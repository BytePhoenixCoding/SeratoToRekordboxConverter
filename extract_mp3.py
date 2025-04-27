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
from mutagen.id3 import ID3, GEOB
from mutagen.mp3 import MP3

from utils import major_key_conversion, minor_key_conversion, convert_key_to_camelot

NonTerminalBeatgridMarker = namedtuple("NonTerminalBeatgridMarker", ["position", "beats_till_next_marker"])
TerminalBeatgridMarker = namedtuple("TerminalBeatgridMarker", ["position", "bpm"])

def parse_serato_hot_cues(base64_data):
    if isinstance(base64_data, str):
        base64_data = base64_data.encode('utf-8')

    clean_data = re.sub(rb'[^a-zA-Z0-9+/=]', b'', base64_data)
    padding_needed = 4 - (len(clean_data) % 4)

    if padding_needed != 4:
        clean_data += b'=' * padding_needed

    try:
        data = base64.b64decode(clean_data)

    except Exception as e:
        return []

    index = 0
    hot_cues = []

    while index < len(data):
        next_null = data[index:].find(b'\x00')

        if next_null == -1:
            break

        entry_type = data[index:index+next_null].decode('utf-8')
        index += next_null + 1

        if index + 4 > len(data):
            break

        entry_len = struct.unpack('>I', data[index:index+4])[0]
        index += 4

        if entry_type == 'CUE' and index + entry_len <= len(data):
            hot_cue_data = data[index:index + entry_len]

            try:
                hotcue_index = hot_cue_data[1]
                position_ms = struct.unpack('>I', hot_cue_data[2:6])[0]
                color_data = hot_cue_data[7:10]
                color_hex = "#{:02X}{:02X}{:02X}".format(color_data[0], color_data[1], color_data[2])
                label = hot_cue_data[12:].rstrip(b"\x00").decode("utf-8", errors="replace")

                hot_cues.append({
                    'index': hotcue_index,
                    'position_ms': position_ms,
                    'color': color_hex,
                    'name': label  
                })

            except Exception as e:
                logging.warning(f"Error parsing hot cue data: {e}")

        index += entry_len
    return hot_cues

def extract_metadata(input_file: str) -> dict:
    try:
        audio = ID3(input_file)
    except Exception as e:
        logging.warning(f"Unable to read ID3 tags from {input_file}: {e}")
        audio_metadata = {"TIT2": "Unknown", "TPE1": "Unknown", "TBPM": "Unknown"}
        hot_cues = []
        geob_tags = []
    else:
        audio_metadata = {}
        hot_cues = []
        geob_tags = []

        for tag_name in ['TIT2', 'TPE1', 'TBPM']:
            tag = audio.get(tag_name, None)
            if tag and hasattr(tag, 'text'):
                audio_metadata[tag_name] = tag.text[0]
            else:
                audio_metadata[tag_name] = 'Unknown'

        for tag in audio.values():
            if isinstance(tag, GEOB):
                desc = getattr(tag, 'desc', '')
                geob_tags.append({
                    "tag": f"----:com.serato.dj:{desc}" if desc else "GEOB",
                    "size": len(tag.data)
                })
                if desc == 'Serato Markers2':
                    try:
                        hot_cues = parse_serato_hot_cues(tag.data)
                    except Exception as e:
                        logging.warning(f"Error reading Serato Markers2 from {input_file}: {e}")

    try:
        audio_file = MP3(input_file)
        audio_metadata['TotalTime'] = round(audio_file.info.length, 3)
    except Exception:
        audio_metadata['TotalTime'] = 0

    try:
        key = str(MP3(input_file).tags.get('TKEY'))
    except Exception:
        key = "Unknown"

    key = convert_key_to_camelot(key)

    return {
        "metadata": {
            "title": audio_metadata.get("TIT2", "Unknown"),
            "artist": audio_metadata.get("TPE1", "Unknown"),
            "bpm": float(audio_metadata.get("TBPM", 0)) if str(audio_metadata.get("TBPM", "")).replace('.', '', 1).isdigit() else 0.0,
            "key": key,
            "duration_sec": audio_metadata.get("TotalTime", 0)
        },
        "hot_cues": hot_cues,
        "beatgrid": get_beatgrid(input_file)
    }

def parse_beatgrid_markers(fp):
    version = struct.unpack("BB", fp.read(2))

    if version != (0x01, 0x00):
        raise ValueError("Unsupported version: " + str(version))

    num_markers = struct.unpack(">I", fp.read(4))[0]
    markers = []

    for i in range(num_markers):
        pos = struct.unpack(">f", fp.read(4))[0]
        data = fp.read(4)

        if i == num_markers - 1:
            bpm = struct.unpack(">f", data)[0]
            markers.append(TerminalBeatgridMarker(pos, bpm))

        else:
            beats_till_next_marker = struct.unpack(">I", data)[0]
            markers.append(NonTerminalBeatgridMarker(pos, beats_till_next_marker))

    fp.read(1)  
    return markers

def get_beatgrid(file_path):
    tagfile = mutagen.File(file_path)

    if not tagfile:
        raise ValueError("Could not open file.")

    try:
        tag = tagfile["GEOB:Serato BeatGrid"]

    except KeyError:
        raise ValueError('Beatgrid tag not found.')

    fp = io.BytesIO(tag.data)
    with fp:
        markers = parse_beatgrid_markers(fp)

    result = {
        "markers": {
            "non_terminal": [], 
            "terminal": None
        }
    }

    if not markers:
        return result

    if len(markers) == 1:
        m = markers[0]
        result["markers"]["terminal"] = {"position": m.position, "bpm": m.bpm}

    else:
        non_terminal = []
        
        for m in markers[:-1]:
            non_terminal.append({
                "position": m.position,
                "beats_till_next_marker": m.beats_till_next_marker
            })

        result["markers"]["non_terminal"] = non_terminal
        terminal = markers[-1]
        result["markers"]["terminal"] = {"position": terminal.position, "bpm": terminal.bpm}

    return result
