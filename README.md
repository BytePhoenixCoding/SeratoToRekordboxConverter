# Serato to Rekordbox Converter

## Overview

This script provides an automated solution for importing Serato crates into Rekordbox playlists. It is designed for DJs who primarily use Serato but also perform with standalone Rekordbox equipment. The script eliminates the time-consuming task of manually updating your Rekordbox library with new tracks.

## How It Works

1. The script scans the specified directory for Serato crate files (`.crate`).
2. Each crate is analyzed to extract the track information it contains.
3. Metadata, including song name, artist, and hot cues, is collected from each track file.
4. A Rekordbox-compatible XML file is generated, ready for import into Rekordbox.

Converting my own library of around 1,500 tracks took around 10 seconds for the script.

## Limitations

- Currently, only `.mp3` and `.m4a` files are supported. Support for additional formats like FLAC or AIFF may be added in the future.
- Some tracks may have hot cues that cannot be parsed. This issue is rare and primarily affects tracks that were initially converted from Rekordbox using third-party software.
- The analysis data from Serato is not converted. The files will need to be re-analysed in Rekordbox, however the hot cues are set as number of milliseconds in the track so they shouldn't be affected by Rekordbox's analysis.
- This script is experimental and may require code adjustments to function correctly in your setup.

## Setup Instructions

### Prerequisites

Install the Mutagen library:

```pip install mutagen```

### Configuration

Modify the following variables in the script as needed:

```
serato_folder_path = "_Serato_/subcrates"
base_dir = "Users/administrator/Music/"
```

### Folder Structure

My library structure looks like this:

```
Music/
├── serato_to_rekordbox_converter.py
├── _Serato_
   ├── Subcrates
├── House/ (contains .mp3 and .m4a files)
└── Rap/ (contains .mp3 and .m4a files)
```

### Execution

Run the script with Python 3:

```python3 serato_to_rekordbox_converter.py```

If successful, a `Serato_Converter.xml` file will be generated.

### Import into Rekordbox

1. Open Rekordbox.
2. Navigate to `Preferences -> Advanced -> rekordbox xml`.
3. Your playlists will appear in Rekordbox under the `rekordbox xml` format. Import them into your main library, analyze, and export to USB as needed.

## Donations

This script offers functionality that many paid programs provide. If you find it helpful, consider supporting its development by donating BNB, Ethereum, or other cryptocurrencies to the following address:

```0x40f1f74038ac7A2B1b8e6Aa4dA80d7C0fC60ab74```

Cheers!



