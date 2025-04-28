# serato2rekordbox v1.3

This Python script converts your Serato DJ Pro library (playlists, tracks, metadata, beatgrids, and hot cues) into a Rekordbox XML file that can be imported into Rekordbox DJ (tested on 6.8.5 and should work on older/newer versions) and can be exported easily to a USB or just used in Rekordbox in HID mode. 

## Changelog

### v1.3:

- Fixed issue where subcrates inside subcrates were not shown at all
- Added auto update checker

### v1.2:

- Supports Rekordbox folders instead of only singular crates
- Playlist song order now the same as in Serato
- `.wav` files now supported

### v1.1:

- Optimised code
- Fixed hot cue names not being correctly processed
- Fixed issue where hot cue slot 1 was never filled
- Fixed issue where key was not properly displayed
- Fixed issues with beatgrids in `.m4a` files (using fixed offset value)

### v1.0:

- Initial release

## Why this was developed

As a DJ who mostly uses Serato in HID mode with my laptop, it's still beneficial to have a working USB so I can go along to a gig with just a USB and headphones, or just to have it as a backup. I only use Serato and don't like to use Rekordbox in general but Serato doesn't have an easy way of exporting tracks to a USB.

I couldn't find any other free software that could convert it so I decided to make my own.

<p align="center">
  <img src="https://github.com/user-attachments/assets/137876c4-04da-470e-a921-4c39486815b5" width="406" />
  &nbsp;&nbsp;&nbsp;➡️&nbsp;&nbsp;&nbsp;
  <img src="https://github.com/user-attachments/assets/ba1af165-993f-459d-9c79-41735e57b2e7" width="326" />
</p>

## Features

*   **Playlist Conversion:** Converts your Serato crates into Rekordbox playlists/folders.
*   **Track Metadata:** Transfers essential metadata including Title, Artist, BPM, and Key.
*   **Hot Cue Transfer:** Extracts and transfers hot cues.
*   **Accurate Beatgrids:** Extracts the Serato beatgrid data directly from the audio files to extract the *first beat position* from the audio file's beatgrid data and includes it in the XML. This tells Rekordbox exactly where the first beat is, allowing it to correctly align the entire beatgrid without needing to re-analyse it itself.
*   **Automatic Serato Folder Detection:** Automatically attempts to find your Serato `_Serato_` folder on standard Windows, macOS and Linux locations.
*   **Detailed Error Reporting:** Collects and reports errors (missing files, unsupported formats, processing errors, crate reading issues) in a clear, grouped summary at the end. Failed tracks are excluded from the output XML.
*   **File Support:** Supports conversion for `.mp3`, `.m4a` and `.wav` audio files found in your Serato library.
*   Normal crates and subcrates are supported.

## Prerequisites

Before running the script, ensure you have the following:

1.  **Python 3:** The script is written in Python 3. You can download it from [python.org](https://www.python.org/downloads/).
2.  **Serato DJ Pro:** Serato must be installed and run at least once on the computer where you run this script, as the script needs to access the Serato `_Serato_` folder and the music files.
3.  **Rekordbox DJ:** You will need Rekordbox DJ (version 6 recommended) to import the generated XML file.

## Installation

1.  **Clone or Download:** Get the script files. You can clone the repository by running:
    ```bash
    git clone https://github.com/BytePhoenixCoding/serato2rekordbox
    cd serato2rekordbox
    ```
    Or download the ZIP file and extract it.

2.  **Install Dependencies:** Open your terminal or command prompt, navigate to the script's directory, and install the required Python package:
    ```bash
    pip install tqdm mutagen
    ```

## Usage

1.  **Open Terminal/Command Prompt:** Navigate to the directory where you saved the script files.
2.  **Run the Script:** Execute the script using Python 3:
    ```bash
    python3 serato2rekordbox.py
    ```
3.  **Let the magic happen:** The script will attempt to auto-detect your Serato folder, read your crates, process your tracks, structure playlists, and finally write the XML file. It shouldn't take longer than a few seconds to complete unless you have a huge library.
4.  **Review Output:** After completion, the script will print a summary of successful/unsuccessful conversions and list any items that could not be processed, grouped by the type of error.

The output file `serato2rekordbox.xml` will be generated in the same directory as the script.

**Note:** There are no configuration variables (`base_dir`, `serato_folder_path`) to change at the top of the script anymore, as it attempts to find the Serato folder automatically.

## Importing into Rekordbox

Once `serato2rekordbox.xml` is generated:

1.  Open Rekordbox DJ.
2.  Go to Settings (Gear icon at top) > Advanced > rekordbox xml and select the generated XML file.
3.  In the sidebar, drag the imported playlists into your USB and wait for Rekordbox to finish processing.

Rekordbox will import the playlists and tracks. The tracks should appear with their correct metadata (Title, Artist, BPM, Key), Hot Cues, and the accurate Beatgrids based on the first beat position provided in the XML. Rekordbox may still perform some background analysis (like waveform drawing), but it should respect the imported beatgrid and cue data.

## Limitations

*   This script primarily transfers playlists, basic metadata, hot cues, and the **first beat position** for the beatgrid. Other Serato-specific data like loops, specific track flags (e.g., played status) etc. may not work.
*   Some tracks may not have the correct beatgrid data or key.
*   Smart crates are not supported.
*   Some beatgrids in Rekordbox appear to be slightly off beat even though perfectly on beat in Serato.
*   You may have to manually adjust the Serato folder path in the code if it isn't auto detected.

## Notes

*   The script has been tested on my own Serato library which contains almost 4000 tracks and performs as intended. It was able to process the entire library in around 20 seconds and rekordbox exporting to my USB (HFS+) only took around 15 minutes.
*   Rekordbox 6.8.5 is recommended at the moment as Rekordbox 7 is reported to export to USB much slower. 
*   `HFS+` seems to be the fastest USB file format but `FAT32` is more compatible with older Pioneer hardware.
*   `.wav` files have not been extensively tested but appear to work fine.

## Future improvements

- Support other file formats eg. `.flac`, `.alac`, `.aiff` - only `.mp3`, `.m4a` and `.wav` are supported at the moment.
- Make a GUI?
- I thought about trying to reverse engineer the USB export structure so the program could directly export to a USB itself without needing Rekordbox at all, however the USB structure (analysis, database etc) is extremely complex, would require alot of effort and likely wouldn't be as reliable.

## Contributing

If you find issues or have ideas for improvements, please feel free to open an issue or submit a pull request.
