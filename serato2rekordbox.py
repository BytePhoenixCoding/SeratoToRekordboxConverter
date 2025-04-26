import os
import re
import struct
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from tqdm import tqdm
import platform
import urllib.parse
from collections import defaultdict
import extract_mp3
import extract_m4a

START_MARKER = b'ptrk'
PATH_LENGTH_OFFSET = 4
START_MARKER_FULL_LENGTH = len(START_MARKER) + PATH_LENGTH_OFFSET

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
    elif platform.system() == "Darwin": # macOS
        potential_paths = [
            os.path.join(home_dir, 'Music', '_Serato_'),
        ]
    else: # Linux
         potential_paths = [
            os.path.join(home_dir, 'Music', '_Serato_'),
         ]

    print("Attempting to auto-detect Serato '_Serato_' folder...")
    for path in potential_paths:
        if os.path.exists(path) and os.path.isdir(path):
            print(f"Found Serato folder at: {path}")
            return path
            
    print("Error: Serato '_Serato_' folder not found in common locations.")
    print("Please ensure Serato DJ Pro has been run at least once.")
    return None

def generate_rekordbox_xml(processed_data, all_tracks_in_tracks):
    root = Element('DJ_PLAYLISTS', Version="1.0.0")
    product = SubElement(root, 'PRODUCT', Name="rekordbox", Version="6.0.0", Company="AlphaTheta")
    
    collection = SubElement(root, 'COLLECTION', Entries=str(len(all_tracks_in_tracks)))

    playlists_elem = SubElement(root, 'PLAYLISTS')
    root_playlist = SubElement(playlists_elem, 'NODE', Type="0", Name="ROOT", Count=str(len(processed_data))) 

    track_id_map = {}
    current_track_id = 1

    for absolute_file_path, track_data in tqdm(all_tracks_in_tracks.items(), desc="Adding tracks to Collection"):
        track_id_map[absolute_file_path] = current_track_id

        quoted_path = urllib.parse.quote(absolute_file_path)

        if platform.system() == "Windows":
            uri_path = absolute_file_path.replace('\\', '/') 
            if re.match(r'^[A-Za-z]:/', uri_path):
                uri_path = '/' + uri_path
            full_file_uri = "file://localhost" + urllib.parse.quote(uri_path)

        else: 
            uri_path = absolute_file_path.lstrip('/') 
            full_file_uri = "file://localhost/" + urllib.parse.quote(uri_path)


        track_elem = SubElement(collection, 'TRACK', 
                                TrackID=str(current_track_id), 
                                Name=track_data.get('title', 'Unknown Title').strip(),
                                Artist=track_data.get('artist', 'Unknown Artist').strip(), 
                                Kind="MP3 File" if absolute_file_path.lower().endswith('.mp3') else "AAC File", 
                                Location=full_file_uri,
                                AverageBpm=str(round(track_data.get('bpm', 0.0), 2)), 
                                Key=track_data.get('key', ''), 
                                TotalTime=str(round(track_data.get('totalTime_sec', 0), 3))
                                )
        
        total_time_ms = int(track_data.get('totalTime_sec', 0) * 1000)
        bpm_val = track_data.get('bpm', 0.0)
        if bpm_val > 0:
             SubElement(track_elem, 'TEMPO', InMs="0", BPM=str(round(bpm_val, 2)), OutMs=str(total_time_ms))

        first_beat_pos_sec = track_data.get('first_beat_pos_sec')
        if first_beat_pos_sec is not None and track_data.get('has_beatgrid', False):
             SubElement(track_elem, 'POSITION_MARK', Name="", Type="1", Start=str(round(first_beat_pos_sec, 3)), Num="1")

        for hot_cue in track_data.get('hot_cues', []):
            position_sec = round(hot_cue.get('position_ms', 0) / 1000.0, 3)
            rekordbox_num = hot_cue.get('index', 0) + 1 

            color = hot_cue.get('color', '#000000')
            try:
                 red = int(color[1:3], 16)
                 green = int(color[3:5], 16)
                 blue = int(color[5:7], 16)
            except (ValueError, IndexError):
                 red, green, blue = 0, 0, 0 

            SubElement(track_elem, 'POSITION_MARK', 
                       Name=hot_cue.get('name', ''), 
                       Type="0", 
                       Start=str(position_sec), 
                       Num=str(rekordbox_num),
                       Red=str(red), 
                       Green=str(green), 
                       Blue=str(blue))

        current_track_id += 1 

    for playlist_name, tracks_data_list in tqdm(processed_data.items(), desc="Structuring Playlists"):
        if not tracks_data_list:
            continue

        playlist_elem = SubElement(root_playlist, 'NODE', 
                                   Name=playlist_name, 
                                   Type="1", 
                                   KeyType="0", 
                                   Entries=str(len(tracks_data_list))) 
        
        for track_data in tracks_data_list:
            absolute_path = track_data['file_location']
            track_id = track_id_map.get(absolute_path)

            if track_id is not None:
                SubElement(playlist_elem, 'TRACK', Key=str(track_id))


    output_filename = "serato2rekordbox.xml"
    print(f"\nWriting XML file: {output_filename}")
    try:
        with open(output_filename, "w", encoding='utf-8') as f:
            f.write(prettify(root))
    except Exception as e:
         print(f"Error writing XML file: {e}")

def find_serato_crates(serato_subcrates_path):
    crate_file_paths = []
    
    if not os.path.exists(serato_subcrates_path):
        print(f"Error: Serato subcrates folder path not found: {serato_subcrates_path}")
        return []

    print(f"Searching for .crate files in: {serato_subcrates_path}")
    for root, dirs, files in os.walk(serato_subcrates_path):
        for file in files:
            if file.endswith('.crate'):
                full_path = os.path.join(root, file)
                crate_file_paths.append(full_path)
    print(f"Found {len(crate_file_paths)} crate files.")
    return crate_file_paths

def extract_file_paths_from_crate(crate_file_path, encoding='utf-16-be'):
    paths = []
    try:
        with open(crate_file_path, 'rb') as f:
            bytes_of_file = f.read()

        bytes_length = len(bytes_of_file)
        i = 0

        while i < bytes_length - START_MARKER_FULL_LENGTH:
            marker_index = bytes_of_file.find(START_MARKER, i)
            if marker_index == -1:
                break 

            i = marker_index + len(START_MARKER)

            if i + PATH_LENGTH_OFFSET > bytes_length:
                 error_msg = f"Malformed crate, unexpected end of file after marker at pos {marker_index}."
                 unsuccessfulConversions.append({'type': 'crate_parse_error', 'path': crate_file_path, 'error': error_msg})
                 break
            path_size_bytes = bytes_of_file[i:i + PATH_LENGTH_OFFSET]
            path_size = struct.unpack('>I', path_size_bytes)[0]
            i += PATH_LENGTH_OFFSET

            if i + path_size > bytes_length:
                error_msg = f"Malformed crate, path size ({path_size}) exceeds remaining data at pos {i}."
                unsuccessfulConversions.append({'type': 'crate_parse_error', 'path': crate_file_path, 'error': error_msg})
                break
            audio_path_bytes = bytes_of_file[i:i + path_size]

            try:
                absolute_audio_path = audio_path_bytes.decode(encoding).strip()
                paths.append(absolute_audio_path) 

            except UnicodeDecodeError:
                error_msg = f"Could not decode path in crate at position {i}."
                unsuccessfulConversions.append({'type': 'crate_decode_error', 'path': crate_file_path, 'error': error_msg})

            i += path_size 

    except FileNotFoundError:
        print(f"Error: Crate file not found: {crate_file_path}")
    except Exception as e:
        error_msg = f"Error reading crate file: {e}"
        unsuccessfulConversions.append({'type': 'crate_read_error', 'path': crate_file_path, 'error': error_msg})

    return paths

print("Serato to Rekordbox Converter (with advanced metadata & beatgrids)")

serato_base_path = find_serato_folder()

if not serato_base_path:
    exit(1)

serato_subcrates_path = os.path.join(serato_base_path, 'subcrates')

serato_crate_paths = find_serato_crates(serato_subcrates_path)

if not serato_crate_paths:
    print("No .crate files found in the subcrates folder.")
    exit(0)

# Build the map of track paths to crate names
track_to_crates = defaultdict(list)
all_track_paths_from_crates = set()

for path in tqdm(serato_crate_paths, desc="Reading crate contents"):
    crate_name = os.path.basename(path)[:-6]
    # Format crate name like playlist name
    try:
        formatted_crate_name = crate_name.split('%%')[0] + " [" + crate_name.split('%%')[1] + "]"
    except IndexError:
        formatted_crate_name = crate_name # Use original name if no %%
    except Exception as e:
         # Capture playlist naming errors related to the crate itself
         unsuccessfulConversions.append({'type': 'crate_name_format_error', 'path': path, 'error': f"Error formatting crate name: {e}"})
         formatted_crate_name = crate_name # Fallback to original name


    paths_in_crate = extract_file_paths_from_crate(path)
    for track_path in paths_in_crate:
        # Normalize path separators and add leading slash for lookup key consistency
        normalized_path = track_path.replace('\\', os.sep)
        if platform.system() != "Windows" and not normalized_path.startswith(os.sep):
            lookup_path = os.sep + normalized_path
        else:
            lookup_path = normalized_path

        track_to_crates[lookup_path].append(formatted_crate_name) # Add formatted crate name
        all_track_paths_from_crates.add(lookup_path) # Collect unique *normalized* paths


print(f"Found {len(all_track_paths_from_crates)} unique tracks across all crates.")

all_tracks_in_tracks = {} 

for full_system_path in tqdm(all_track_paths_from_crates, desc="Processing tracks"):
    
    # full_system_path is already normalized and potentially has a leading slash from the track_to_crates map building

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
        else:
            unsuccessfulConversions.append({'type': 'unsupported_format', 'path': full_system_path, 'error': f"Unsupported format: {file_extension}"})
            continue

        metadata = extracted_data.get('metadata', {})
        hot_cues = extracted_data.get('hot_cues', [])
        beatgrid = extracted_data.get('beatgrid', [])

        first_beat_pos_sec = None
        has_beatgrid = len(beatgrid) > 0 and isinstance(beatgrid, list)

        if has_beatgrid:
             try:
                 first_beat_pos_sec = float(beatgrid[0])
                 if first_beat_pos_sec < 0:
                     first_beat_pos_sec = 0.0
             except (IndexError, ValueError) as e:
                 unsuccessfulConversions.append({'type': 'beatgrid_parse_error', 'path': full_system_path, 'error': f"Invalid beatgrid data: {e}"})
                 first_beat_pos_sec = None
                 has_beatgrid = False 

        all_tracks_in_tracks[full_system_path] = {
            'file_location': full_system_path, 
            'title': metadata.get('title', os.path.basename(full_system_path)), 
            'artist': metadata.get('artist', 'Unknown Artist'), 
            'bpm': metadata.get('bpm', 0.0),
            'key': metadata.get('key', 'Unknown'), 
            'totalTime_sec': metadata.get('duration_sec', 0), 
            'hot_cues': hot_cues,
            'first_beat_pos_sec': first_beat_pos_sec, 
            'has_beatgrid': has_beatgrid 
        }

    except Exception as e:
        unsuccessfulConversions.append({'type': 'processing_error', 'path': full_system_path, 'error': f"{e}"})

processedSeratoFiles = {}

# Re-read crate paths for playlist structuring, as we need the original crate path for naming
for path in tqdm(serato_crate_paths, desc="Structuring Playlists"):
    playlistName = os.path.basename(path)[:-6]

    try:
        playlistName = playlistName.split('%%')[0] + " [" + playlistName.split('%%')[1] + "]"
    except IndexError:
        pass
    except Exception as e:
        # These are playlist names, errors already captured during track_to_crates build or handled by fallback
        pass 

    processedSeratoFiles[playlistName] = []

    raw_paths_in_crate = extract_file_paths_from_crate(path)

processedSeratoFiles = defaultdict(list)

# Iterate through all successfully processed tracks
for full_system_path, track_data in all_tracks_in_tracks.items():
    # Find all crates this track belongs to
    crates_for_track = track_to_crates.get(full_system_path, [])
    
    for crate_name in crates_for_track:
        # Add this track's data to the list for the corresponding playlist name
        processedSeratoFiles[crate_name].append(track_data)

# Filter out playlists that ended up empty after removing failed tracks
processedSeratoFiles = {name: tracks for name, tracks in processedSeratoFiles.items() if tracks}

if processedSeratoFiles:
    generate_rekordbox_xml(processedSeratoFiles, all_tracks_in_tracks)
else:
    print("\nNo tracks were successfully processed. XML file not generated.")

print("\n\n")
print(f'{str(len(all_track_paths_from_crates) - len(unsuccessfulConversions))} / {str(len(all_track_paths_from_crates))} tracks successfully converted.')
print("\n\n")

# --- Refactored Error Reporting ---
if unsuccessfulConversions:
    print(f"\n--- {len(unsuccessfulConversions)} Unsuccessful Conversions ({len(all_track_paths_from_crates) - len(all_tracks_in_tracks)} tracks failed) ---")
    print("The following items could not be processed and have not been included in the XML file:")

    # Group errors by type
    grouped_errors = {}
    for item in unsuccessfulConversions:
        error_type = item.get('type', 'unknown')
        if error_type not in grouped_errors:
            grouped_errors[error_type] = []
        grouped_errors[error_type].append(item)

    # Define user-friendly titles and print order
    error_type_titles = {
        'file_not_found': "Files Not Found:",
        'unsupported_format': "Unsupported File Formats:",
        'processing_error': "Errors During Track Processing:",
        'beatgrid_parse_error': "Errors Parsing Beatgrid Data:",
        'crate_read_error': "Errors Reading Crate Files:",
        'crate_parse_error': "Errors Parsing Crate File Contents:",
        'crate_decode_error': "Errors Decoding Paths in Crate Files:",
        'crate_name_format_error': "Errors Formatting Crate/Playlist Names:", # Updated title
        'unknown': "Other Errors:"
    }

    # Print grouped errors in a defined order
    # Sort keys to ensure consistent order even if a new type is added
    sorted_error_types = sorted(grouped_errors.keys(), key=lambda x: list(error_type_titles.keys()).index(x) if x in error_type_titles else len(error_type_titles))

    for error_type in sorted_error_types:
        title = error_type_titles.get(error_type, error_type + ":") # Use default if not in titles map
        print(f"\n{title}")
        for item in grouped_errors[error_type]:
            item_path = item.get('path', 'N/A')
            item_error = item.get('error', 'No details')

            # Track-related errors: Use filename and crate names
            if error_type in ['file_not_found', 'unsupported_format', 'processing_error', 'beatgrid_parse_error']:
                # Get the filename (basename)
                filename = os.path.basename(item_path)
                # Get the crates this file was found in
                crates_for_file = track_to_crates.get(item_path, [])
                crate_display = ", ".join(crates_for_file) if crates_for_file else "Unknown Crate"

                if "not a MP4 file" in item_error:
                    item_error = "File appears to be invalid or corrupt"

                print(f'- "{filename}" ({crate_display}): {item_error}')
            
            # Crate-related errors
            elif error_type in ['crate_read_error', 'crate_parse_error', 'crate_decode_error', 'crate_name_format_error']:
                 # Use the basename of the crate file path
                 crate_filename = os.path.basename(item_path)
                 print(f'- Crate "{crate_filename}": {item_error}')

            else: # Catch-all
                 print(f'- Item "{item_path}": {item_error}')


else:
    print("\nAll tracks successfully processed.")