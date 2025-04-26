import os
import re
import struct
import base64
import logging
from pathlib import Path
from mutagen.id3 import ID3, GEOB
from mutagen.mp3 import MP3

import mp3_beatgrid

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

def convert_key_to_camelot(key: str) -> str:
    # If already in Camelot format (e.g. 1A to 12B), just return it
    if re.match(r'^(1[0-2]|[1-9])[AB]$', key):
        return key
    
    if key in major_key_conversion:
        return major_key_conversion[key]
    elif key in minor_key_conversion:
        return minor_key_conversion[key]
    else:
        return "Unknown"

def extract_mp3_metadata(track_path):
    try:
        audio = ID3(track_path)
    except Exception as e:
        logging.warning(f"Unable to read ID3 tags from {track_path}: {e}")
        return {}, [], []
    
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
                    logging.warning(f"Error reading Serato Markers2 from {track_path}: {e}")

    # Add track duration using MP3 info
    try:
        audio_file = MP3(track_path)
        audio_metadata['TotalTime'] = round(audio_file.info.length)
    except Exception:
        audio_metadata['TotalTime'] = 0

    return audio_metadata, geob_tags, hot_cues

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
        #logging.error(f"Failed to decode hot cues: {e}")
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
                hot_cues.append({
                    'index': hotcue_index,
                    'position_ms': position_ms,
                    'color': color_hex,
                    'name': ""  # Name support can be added if found in structure
                })
            except Exception as e:
                logging.warning(f"Error parsing hot cue data: {e}")
        index += entry_len
    return hot_cues

def extract_metadata(input_file: str) -> dict:
    meta, geobs, cues = extract_mp3_metadata(input_file)

    key = str(MP3(input_file).tags.get('TKEY'))
    key = convert_key_to_camelot(key)

    return {
        "metadata": {
            "title": meta.get("TIT2", "Unknown"),
            "artist": meta.get("TPE1", "Unknown"),
            "bpm": float(meta.get("TBPM", 0)) if str(meta.get("TBPM", "")).replace('.', '', 1).isdigit() else 0.0,
            "key": key, # Added Key
            "duration_sec": meta.get("TotalTime", 0)
        },
        "hot_cues": cues,
        "beatgrid": mp3_beatgrid.get_beatgrid(input_file)
    }