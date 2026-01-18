# Media Timestamp & Compression Pipeline

This Python script automatically renames your photos and videos based on their timestamps, compresses videos, and converts MOV files to MP4. It works with iPhone photos, WhatsApp/Messenger media, and other common formats.  

---

## Features

- Renames images and videos using **EXIF, QuickTime, or filesystem timestamps**  
- Handles images: `.jpg`, `.jpeg`, `.png`, `.heic`, `.tiff`, `.webp`  
- Handles videos: `.mov`, `.mp4`  
- Converts `.MOV` → `.MP4` with **H.264 compression**  
- Compresses videos while keeping them **QuickTime compatible**  
- Automatically prevents filename collisions  

---

## Requirements

- Python 3.10+  
- FFmpeg (must be installed and available in your PATH)  

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install FFmpeg:

macOS (Homebrew):

```bash
brew install ffmpeg
```

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

Check FFmpeg is installed:

```bash
ffmpeg -version
```

## Usage

Run the script on your folder of media:

```bash
python rename_media.py /path/to/your/folder
```

If no folder is provided, the script defaults to the current directory.

Example output:

```
IMG_7133.MOV → IMG_7133.mp4 [H.264 compressed]
IMG_7133.mp4 → 2025-07-17_09-42-11.mp4 [QuickTimeCreationTime]
bff6-2de10b0d.mp4 → 2025-07-18_20-08-07.mp4 [FileModifyDate]
IMG_9297.HEIC → 2025-07-19_14-22-30.heic [DateTimeOriginal]
```

## Notes

All videos are compressed using H.264 for smaller size and maximum compatibility.

Images are renamed based on their capture timestamp if available, otherwise file modification time is used.

Safe renaming: duplicate filenames automatically get -1, -2, etc.

## License

MIT License — feel free to use for personal projects.