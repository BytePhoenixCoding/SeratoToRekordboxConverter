import argparse
import io
import struct
import mutagen
import json
import sys
from collections import namedtuple

NonTerminalBeatgridMarker = namedtuple("NonTerminalBeatgridMarker", ["position", "beats_till_next_marker"])
TerminalBeatgridMarker = namedtuple("TerminalBeatgridMarker", ["position", "bpm"])

def parse(fp):
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
        markers = parse(fp)

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