print(r'''         
                     _       ___           _                 _ _               
                    | |     |__ \         | |               | | |              
  ___  ___ _ __ __ _| |_ ___   ) |_ __ ___| | _____  _ __ __| | |__   _____  __
 / __|/ _ \ '__/ _` | __/ _ \ / /| '__/ _ \ |/ / _ \| '__/ _` | '_ \ / _ \ \/ /
 \__ \  __/ | | (_| | || (_) / /_| | |  __/   < (_) | | | (_| | |_) | (_) >  < 
 |___/\___|_|  \__,_|\__\___/____|_|  \___|_|\_\___/|_|  \__,_|_.__/ \___/_/\_\
''')

current_version = "serato2rekordbox v1.3"
print("\nVersion 1.3\n\n")

import os
import re
import struct
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from tqdm import tqdm
import platform
import urllib.parse
from collections import defaultdict
from collections import OrderedDict 

import extract_mp3
import extract_m4a
import extract_wav

import urllib.request
import ssl

try:
    url = "https://raw.githubusercontent.com/BytePhoenixCoding/serato2rekordbox/main/README.md"
    context = ssl._create_unverified_context()  # <- disable SSL verification
    with urllib.request.urlopen(url, timeout=5, context=context) as response:
        content = response.read().decode('utf-8')

    if current_version not in content:
        print("──────────────────────────────────────────────────────────")
        print("⚠️ A new version of serato2rekordbox is available!")
        print("🔗 Please update here: https://github.com/BytePhoenixCoding/serato2rekordbox")
        print("──────────────────────────────────────────────────────────\n")
    else:
        print("✅ serato2rekordbox is up to date.")
except Exception as e:
    print(f"(Update check skipped: {e})")

START_MARKER = b'ptrk'
PATH_LENGTH_OFFSET = 4
START_MARKER_FULL_LENGTH = len(START_MARKER) + PATH_LENGTH_OFFSET
M4A_BEATGRID_OFFSET = 0.07
M4A_HOTCUE_OFFSET = 0.03

unsuccessfulConversions = [] 

def prettify(elem):
    rough_string = tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")

def find_serato_folder():
    home_dir = os.path.expanduser('~')

    potential_paths = []
    if platform.system() == "Windows":
        potential_paths = [
            os.path.join(home_dir, 'Music', '_Serato_'),
            os.path.join(home_dir, 'Documents', '_Serato_'),
        ]
    elif platform.system() == "Darwin": 
        potential_paths = [
            os.path.join(home_dir, 'Music', '_Serato_'),
        ]
    else: 
        potential_paths = [
            os.path.join(home_dir, 'Music', '_Serato_'),
        ]

    for path in potential_paths:
        if os.path.exists(path) and os.path.isdir(path):
            print(f"✅ Found Serato folder at: {path}")
            return path

    print("Error: Serato '_Serato_' folder not found in common locations.")
    print("Please ensure Serato DJ Pro has been run at least once.")
    return None

def generate_rekordbox_xml(processed_data, all_tracks_in_tracks):
    root = Element("DJ_PLAYLISTS", Version="1.0.0")
    SubElement(root, "PRODUCT", Name="rekordbox", Version="6.0.0", Company="AlphaTheta")
    collection = SubElement(root, "COLLECTION", Entries=str(len(all_tracks_in_tracks)))
    playlists_elem = SubElement(root, "PLAYLISTS")
    root_playlist = SubElement(playlists_elem, "NODE", Type="0", Name="ROOT", Count="0")

    track_id_map = {}
    current_track_id = 1

    for path, data in tqdm(all_tracks_in_tracks.items(), desc="⚙️ (4/4) Adding tracks"):
        track_id_map[path] = current_track_id

        if platform.system() == "Windows":
            uri_path = path.replace("\\", "/")
            if re.match(r"^[A-Za-z]:", uri_path):
                uri_path = "/" + uri_path
            uri = "file://localhost" + urllib.parse.quote(uri_path)
        else:
            uri = "file://localhost/" + urllib.parse.quote(path.lstrip("/"))

        kind = "MP3 File" if path.lower().endswith(".mp3") else "M4A File" if path.lower().endswith(".m4a") else "WAV File"

        tr = SubElement(collection, "TRACK",
                        TrackID=str(current_track_id),
                        Name=data["title"].strip(),
                        Artist=data["artist"].strip(),
                        Kind=kind,
                        Location=uri,
                        AverageBpm=f"{data['bpm']:.2f}",
                        Tonality=data["key"],
                        TotalTime=f"{data['totalTime_sec']:.3f}")

        is_m4a = path.lower().endswith(".m4a")
        sr = data.get("sample_rate", 0)
        delay = (2 * 1024 / sr) if (is_m4a and sr) else 0.0
        raw_grid = data.get("beatgrid")
        seg_positions, seg_bpms = [], []

        if isinstance(raw_grid, dict):
            markers = raw_grid.get("markers", {})
            non_term = markers.get("non_terminal") or []
            terminal = markers.get("terminal")

            if terminal:
                for i, nt in enumerate(non_term):
                    pos = float(nt["position"])
                    nxt = float(non_term[i + 1]["position"]) if i + 1 < len(non_term) else float(terminal["position"])
                    beats = nt.get("beats_till_next_marker", 0)
                    dur = nxt - pos
                    seg_bpms.append((beats * 60.0 / dur) if dur > 0 else data["bpm"])
                    seg_positions.append(pos)

                seg_positions.append(float(terminal["position"]))
                seg_bpms.append(float(terminal.get("bpm", data["bpm"])))

            else:
                seg_positions, seg_bpms = [data.get("first_beat_pos_sec") or 0.0], [data["bpm"]]

        elif isinstance(raw_grid, list) and raw_grid:
            seg_positions, seg_bpms = [float(raw_grid[0])], [data["bpm"]]

        else:
            seg_positions, seg_bpms = [0.0], [data["bpm"]]

        for pos, bpm_val in zip(seg_positions, seg_bpms):
            if is_m4a:
                pos += M4A_BEATGRID_OFFSET

            pos += delay / 1000.0
            SubElement(tr, "TEMPO", Inizio=f"{pos:.3f}", Bpm=f"{bpm_val:.2f}", Battito="1")

        for cue in data.get("hot_cues", []):
            sec = cue["position_ms"] / 1000.0

            if is_m4a:
                sec += M4A_HOTCUE_OFFSET
            r, g, b = (int(cue["color"][i:i + 2], 16) for i in (1, 3, 5))

            SubElement(tr, "POSITION_MARK",
                       Name=cue["name"], Type="0",
                       Start=f"{sec:.3f}", Num=str(cue["index"]),
                       Red=str(r), Green=str(g), Blue=str(b))
        current_track_id += 1

    root_playlist.set("Count", str(len(processed_data)))

    for plist_name, tracks in processed_data.items():
        pnode = SubElement(root_playlist, "NODE", Name=plist_name, Type="1", KeyType="0", Entries=str(len(tracks)))

        for t in tracks:
            tid = track_id_map.get(t["file_location"])
            
            if tid:
                SubElement(pnode, "TRACK", Key=str(tid))

    with open("serato2rekordbox.xml", "w", encoding="utf-8") as f:
        f.write(prettify(root))

def find_serato_crates(serato_subcrates_path):
    crate_file_paths = []

    if not os.path.exists(serato_subcrates_path):
        print(f"Error: Serato subcrates folder path not found: {serato_subcrates_path}")
        return []

    print(f"✅ Searching for .crate files in: {serato_subcrates_path}")
    for root, dirs, files in os.walk(serato_subcrates_path):
        for file in files:
            if file.endswith('.crate'):
                full_path = os.path.join(root, file)
                crate_file_paths.append(full_path)
    print(f"✅ Found {len(crate_file_paths)} crate files.\n")
    return crate_file_paths

def extract_file_paths_from_crate(crate_file_path, encoding: str = "utf-16-be"):
    paths: list[str] = []
    seen: set[str] = set()

    try:
        with open(crate_file_path, "rb") as f:
            blob = f.read()

        blob_len = len(blob)
        i = 0

        while i < blob_len - START_MARKER_FULL_LENGTH:
            marker_idx = blob.find(START_MARKER, i)
            if marker_idx == -1:
                break

            i = marker_idx + len(START_MARKER)

            # read 4-byte BE length
            if i + PATH_LENGTH_OFFSET > blob_len:
                unsuccessfulConversions.append({
                    "type": "crate_parse_error",
                    "path": crate_file_path,
                    "error": f"Unexpected EOF after marker at byte {marker_idx}"
                })
                break

            path_len = struct.unpack(">I", blob[i : i + PATH_LENGTH_OFFSET])[0]
            i += PATH_LENGTH_OFFSET

            if i + path_len > blob_len:
                unsuccessfulConversions.append({
                    "type": "crate_parse_error",
                    "path": crate_file_path,
                    "error": f"Path size {path_len} exceeds remaining data at byte {i}"
                })
                break

            raw_path = blob[i : i + path_len]
            i += path_len                 # advance for next loop

            try:
                abs_path = raw_path.decode(encoding).strip()
            except UnicodeDecodeError:
                unsuccessfulConversions.append({
                    "type": "crate_decode_error",
                    "path": crate_file_path,
                    "error": f"Failed UTF-16 decode at byte {i - path_len}"
                })
                continue

            # keep only the first occurrence of any duplicate
            if abs_path not in seen:
                paths.append(abs_path)
                seen.add(abs_path)

    except FileNotFoundError:
        print(f"Error: Crate file not found: {crate_file_path}")
    except Exception as exc:
        unsuccessfulConversions.append({
            "type": "crate_read_error",
            "path": crate_file_path,
            "error": str(exc)
        })

    return paths

### Main script ###

serato_base_path = find_serato_folder()

serato_subcrates_path = os.path.join(serato_base_path, 'subcrates')

serato_crate_paths = find_serato_crates(serato_subcrates_path)

if not serato_crate_paths:
    print("⚠️ No .crate files found in the subcrates folder.")
    exit(0)

track_to_crates = defaultdict(list)
all_track_paths_from_crates = set()

for path in tqdm(serato_crate_paths, desc="⚙️ (1/4) Reading crate contents"):
    crate_name = os.path.basename(path)[:-6]

    try:
        formatted_crate_name = crate_name.split('%%')[0] + " [" + crate_name.split('%%')[1] + "]"
    except IndexError:
        formatted_crate_name = crate_name 
    except Exception as e:
         unsuccessfulConversions.append({'type': 'crate_name_format_error', 'path': path, 'error': f"Error formatting crate name: {e}"})
         formatted_crate_name = crate_name 

    paths_in_crate = extract_file_paths_from_crate(path)
    for track_path in paths_in_crate:

        normalized_path = track_path.replace('\\', os.sep)
        if platform.system() != "Windows" and not normalized_path.startswith(os.sep):
            lookup_path = os.sep + normalized_path
        else:
            lookup_path = normalized_path

        track_to_crates[lookup_path].append(formatted_crate_name) 
        all_track_paths_from_crates.add(lookup_path) 

all_tracks_in_tracks = {} 

for full_system_path in tqdm(all_track_paths_from_crates, desc="⚙️ (2/4) Processing tracks"):
    if not os.path.exists(full_system_path):
        unsuccessfulConversions.append({'type': 'file_not_found', 'path': full_system_path, 'error': 'File not found'})
        continue

    try:
        file_extension = os.path.splitext(full_system_path)[1].lower()
        extracted_data = None

        if file_extension == '.mp3':
            extracted_data = extract_mp3.extract_metadata(full_system_path)

        elif file_extension == '.m4a':
            extracted_data = extract_m4a.extract_metadata(full_system_path)

        elif file_extension == '.wav':
            extracted_data = extract_wav.extract_metadata(full_system_path)

        else:
            unsuccessfulConversions.append({'type': 'unsupported_format', 'path': full_system_path, 'error': f"Unsupported format: {file_extension}"})
            continue

        metadata = extracted_data.get('metadata', {})
        hot_cues = extracted_data.get('hot_cues', [])
        beatgrid = extracted_data.get('beatgrid')

        all_tracks_in_tracks[full_system_path] = {
            'file_location': full_system_path, 
            'title': metadata.get('title', os.path.basename(full_system_path)), 
            'artist': metadata.get('artist', 'Unknown Artist'), 
            'bpm': metadata.get('bpm', 0.0),
            'key': metadata.get('key', 'Unknown'), 
            'totalTime_sec': metadata.get('duration_sec', 0), 
            'hot_cues': hot_cues,
            'beatgrid': beatgrid,
            'sample_rate': metadata.get('sample_rate', 0)
        }

    except Exception as e:
        unsuccessfulConversions.append({'type': 'processing_error', 'path': full_system_path, 'error': f"{e}"})


processedSeratoFiles: "OrderedDict[str, list]" = OrderedDict()

for crate_path in tqdm(serato_crate_paths,
                        desc="⚙️ (3/4) Structuring Playlists"):
    raw_name = os.path.basename(crate_path)[:-6]          # strip ".crate"

    segments = raw_name.split("%%")
    if len(segments) == 1:
        crate_display_name = segments[0]                  # flat crate
    else:
        crate_display_name = segments[0] + "".join(
            f" [{seg}]" for seg in segments[1:]
        )

    processedSeratoFiles[crate_display_name] = []

    # Re-read paths *in crate order* so the playlist keeps Serato's sequence.
    ordered_paths = extract_file_paths_from_crate(crate_path)

    for p in ordered_paths:
        # normalise path exactly the same way as earlier
        norm = p.replace("\\", os.sep)
        if platform.system() != "Windows" and not norm.startswith(os.sep):
            norm = os.sep + norm

        track_data = all_tracks_in_tracks.get(norm)
        if track_data:
            processedSeratoFiles[crate_display_name].append(track_data)

# strip out any empty crates
processedSeratoFiles = {
    name: tracks for name, tracks in processedSeratoFiles.items() if tracks
}

if processedSeratoFiles:
    generate_rekordbox_xml(processedSeratoFiles, all_tracks_in_tracks)

else:
    print("\nNo tracks were successfully processed. XML file not generated.")


print("\n")
print(f"✅ Found {len(all_track_paths_from_crates)} unique tracks across all crates.")
print(f'✅ {str(len(all_track_paths_from_crates) - len(unsuccessfulConversions))} / {str(len(all_track_paths_from_crates))} tracks successfully converted.')
print("\n")

if unsuccessfulConversions:
    print(f"⚠️ {len(unsuccessfulConversions)} Unsuccessful Conversions ({len(all_track_paths_from_crates) - len(all_tracks_in_tracks)} tracks failed).")
    print("⚠️ The following items could not be processed and have not been included in the XML file:")

    grouped_errors = {}
    for item in unsuccessfulConversions:
        error_type = item.get('type', 'unknown')
        if error_type not in grouped_errors:
            grouped_errors[error_type] = []
        grouped_errors[error_type].append(item)

    error_type_titles = {
        'file_not_found': "Files Not Found:",
        'unsupported_format': "Unsupported File Formats:",
        'processing_error': "Errors During Track Processing:",
        'beatgrid_parse_error': "Errors Parsing Beatgrid Data:",
        'crate_read_error': "Errors Reading Crate Files:",
        'crate_parse_error': "Errors Parsing Crate File Contents:",
        'crate_decode_error': "Errors Decoding Paths in Crate Files:",
        'crate_name_format_error': "Errors Formatting Crate/Playlist Names:", 
        'unknown': "Other Errors:"
    }

    sorted_error_types = sorted(grouped_errors.keys(), key=lambda x: list(error_type_titles.keys()).index(x) if x in error_type_titles else len(error_type_titles))

    for error_type in sorted_error_types:
        title = error_type_titles.get(error_type, error_type + ":") 
        print(f"\n{title}")
        for item in grouped_errors[error_type]:
            item_path = item.get('path', 'N/A')
            item_error = item.get('error', 'No details')

            if error_type in ['file_not_found', 'unsupported_format', 'processing_error', 'beatgrid_parse_error']:

                filename = os.path.basename(item_path)

                crates_for_file = track_to_crates.get(item_path, [])
                crate_display = ", ".join(crates_for_file) if crates_for_file else "Unknown Crate"

                if "not a MP4 file" in item_error:
                    item_error = "File appears to be invalid or corrupt"

                print(f'- "{filename}" ({crate_display}): {item_error}')

            elif error_type in ['crate_read_error', 'crate_parse_error', 'crate_decode_error', 'crate_name_format_error']:

                 crate_filename = os.path.basename(item_path)
                 print(f'- Crate "{crate_filename}": {item_error}')

            else: 
                 print(f'- Item "{item_path}": {item_error}')

else:
    print("\n✅ All tracks successfully processed.")