#Serato to Rekordbox converter by BytePhoenix
#change the values below

serato_folder_path = "_Serato_/subcrates"
base_dir = "Users/administrator/Music/"

#------------------------------------------------

from xml.etree.ElementTree import Element, SubElement, ElementTree, tostring
from xml.dom import minidom
import os
import re
import struct
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
import base64
import traceback

START_MARKER = b'ptrk'
PATH_LENGTH_OFFSET = 4
START_MARKER_FULL_LENGTH = len(START_MARKER) + PATH_LENGTH_OFFSET

processedSeratoFiles = {}
unsuccessfulConversions = []

def prettify(elem):
    rough_string = tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")

def generate_rekordbox_xml(processed_data):
    root = Element('DJ_PLAYLISTS', Version="1.0.0")
    product = SubElement(root, 'PRODUCT', Name="rekordbox", Version="6.7.4", Company="AlphaTheta")
    collection = SubElement(root, 'COLLECTION', Entries=str(len(processed_data)))
    playlists_elem = SubElement(root, 'PLAYLISTS')
    root_playlist = SubElement(playlists_elem, 'NODE', Type="0", Name="ROOT", Count=str(len(processed_data)))

    track_id = 1
    for playlist_name, tracks in processed_data.items():
        playlist_elem = SubElement(root_playlist, 'NODE', Name=playlist_name, Type="1", KeyType="0", Entries=str(len(tracks)))
        
        for track in tracks:
            full_file_path = "file://localhost" + os.path.join(os.getcwd(), track['file_location'])
            track_elem = SubElement(collection, 'TRACK', TrackID=str(track_id), Name=track['title'].strip(),
                                    Artist=track['artist'].strip(), Kind="MP3 File", TotalTime=track['totalTime'], Location=full_file_path)
            
            for hot_cue in track.get('hot_cues', []):
                SubElement(track_elem, 'POSITION_MARK', Name="", Type="0", Start=str(round(hot_cue['position_ms'] / 1000, 3)), Num=str(hot_cue['index']),
                           Red=str(int(hot_cue['color'][1:3], 16)), Green=str(int(hot_cue['color'][3:5], 16)), Blue=str(int(hot_cue['color'][5:7], 16)))

            SubElement(playlist_elem, 'TRACK', Key=str(track_id))
            track_id += 1

    with open("Serato_Converted.xml", "w", encoding='utf-8') as f:
        f.write(prettify(root))

def find_serato_crates(serato_folder_path):
    crate_file_paths = []
    for root, dirs, files in os.walk(serato_folder_path):
        for file in files:
            if file.endswith('.crate'):
                full_path = os.path.join(root, file)
                crate_file_paths.append(full_path)
    return crate_file_paths

def has_equal_bytes_at(idx, bytes_array, subset):
    return idx < len(bytes_array) - len(subset) and all(bytes_array[idx + i] == subset[i] for i in range(len(subset)))

def extract_file_paths_from_crate(crate_file_path, encoding='utf-16-be'):
    with open(crate_file_path, 'rb') as f:
        bytes_of_file = f.read()
    
    bytes_length = len(bytes_of_file)
    i = 0
    results = []

    while i < bytes_length - START_MARKER_FULL_LENGTH:
        if has_equal_bytes_at(i, bytes_of_file, START_MARKER):
            i += len(START_MARKER)
            path_size = struct.unpack('>I', bytes_of_file[i:i + PATH_LENGTH_OFFSET])[0]
            i += PATH_LENGTH_OFFSET

            audio_path = bytes_of_file[i:i + path_size].decode(encoding)
            results.append(audio_path)
            
            i += path_size

        i += 1

    return results

def extract_m4a_metadata(track):
    audio = MP4(track)
    
    audio_metadata = {
        'TIT2': audio.get('\xa9nam', ['Unknown Title'])[0],
        'TPE1': audio.get('\xa9ART', ['Unknown Artist'])[0],
        'TBPM': audio.get('tmpo', ['Unknown BPM'])[0],
        'TotalTime': round(audio.info.length)
    }
    
    # Check for both '----:com.serato:markersv2' and '----:com.serato.dj:markersv2'
    serato_markers_base64 = audio.get('----:com.serato:markersv2', [None])[0] or audio.get('----:com.serato.dj:markersv2', [None])[0]
    
    if serato_markers_base64:
        hot_cues = parseSeratoHotCues(serato_markers_base64, track)
        return audio_metadata, hot_cues
    else:
        return audio_metadata, []

def extract_mp3_metadata(track):
    try:
        audio = ID3(track)
    except Exception as e:
        print(f"Warning: Unable to read ID3 tags from {track} due to {e}")
        return {}, []

    audio_metadata = {}
    hot_cues = []

    for tag_name in ['TIT2', 'TPE1', 'TALB', 'TBPM']:
        try:
            tag = audio.get(tag_name, 'Unknown')
            if hasattr(tag, 'text'):
                audio_metadata[tag_name] = tag.text[0]
            else:
                if tag_name == "TIT2" or tag_name == "TPE1":  # Ignore TALB warnings
                    print(f"Warning: Tag {tag_name} not properly formatted in file {track}.")
                audio_metadata[tag_name] = 'Unknown'
        except Exception as e:
            print(f"Warning: An issue occurred while reading {tag_name} from {track}: {e}")

    for tag in audio.values():
        if tag.FrameID == 'GEOB':
            if tag.desc == 'Serato Markers2':
                try:
                    hot_cues = parseSeratoHotCues(tag.data, track)
                except Exception as e:
                    print(f"Warning: An issue occurred while reading Serato Markers2 from {track}: {e}")

    return audio_metadata, hot_cues

def parseSeratoHotCues(base64_data, track):
    # Remove non-base64 characters
    clean_base64_data = re.sub(r'[^a-zA-Z0-9+/=]', '', base64_data.decode('utf-8'))

    # Pad the base64 string to make its length a multiple of 4
    padding_needed = 4 - len(clean_base64_data) % 4
    if padding_needed != 4:
        clean_base64_data += "=" * padding_needed

    try:
        data = base64.b64decode(clean_base64_data)
    except Exception as e:
        print(f"Error decoding base64 data: {e} {track}")  
        return []
    
    index = 0
    hot_cues = []
    
    while index < len(data):
        next_null = data[index:].find(b'\x00')
        if next_null == -1:
            print("Reached end of data")
            break

        entry_type = data[index:index + next_null].decode('utf-8')
        index += len(entry_type) + 1

        if index + 4 > len(data):
            break

        entry_len = struct.unpack('>I', data[index:index + 4])[0]
        index += 4  # Move past the length field

        if entry_type == 'CUE':
            hot_cue_data = data[index:index + entry_len]
            
            hotcue_index = hot_cue_data[1]
            position_ms = struct.unpack('>I', hot_cue_data[2:6])[0]
            color_data = hot_cue_data[7:10]
            color_hex = "#{:02X}{:02X}{:02X}".format(color_data[0], color_data[1], color_data[2])
            
            hot_cues.append({
                'index': hotcue_index,
                'position_ms': position_ms,
                'color': color_hex,
            })
        
        index += entry_len

    return hot_cues

serato_crate_paths = find_serato_crates(serato_folder_path)

for path in serato_crate_paths:
    playlistName = os.path.basename(path)[:-6]  # Remove '.crate' from the filename to get the playlist name
    print("Converting: " + playlistName)

    # Initialize the playlist entry in processedSeratoFiles if not already present
    if playlistName not in processedSeratoFiles:
        processedSeratoFiles[playlistName] = []

    for track in extract_file_paths_from_crate(path):
        track = os.path.relpath(track, base_dir)
        audio_metadata = {}
        hot_cues = []

        try:
            if track.lower().endswith('.mp3'):
                audio_metadata, hot_cues = extract_mp3_metadata(track)
            elif track.lower().endswith('.m4a'):
                audio_metadata, hot_cues = extract_m4a_metadata(track)
            else:
                unsuccessfulConversions.append(track)
                continue

            songTitle = audio_metadata.get('TIT2', 'Unknown Title')
            songArtist = audio_metadata.get('TPE1', 'Unknown Artist')

            totalTime = None

            if track.lower().endswith('.mp3'):
                audio = MP3(track)
                totalTime = round(audio.info.length)
            elif track.lower().endswith('.m4a'):
                audio = MP4(track)
                totalTime = round(audio.info.length)
            else:
                raise Exception("Invalid format type")

            processedSeratoFiles[playlistName].append({
                'file_location': track,
                'title': songTitle,
                'artist': songArtist,
                'hot_cues': hot_cues,
                'totalTime': str(totalTime)
            })

        except Exception as e:
            print(f"An exception occurred: {e}")
            #traceback.print_exc()
            unsuccessfulConversions.append(track)

generate_rekordbox_xml(processedSeratoFiles)
print("\nOutput successfully generated: Serato_Converted.xml\n")

# Print the unsuccessful conversions
if unsuccessfulConversions:
    print("The following files have not been converted (corrupt / unrecognised metadata, unsupported format, missing file etc): ")
    for track in unsuccessfulConversions:
        print(track)
