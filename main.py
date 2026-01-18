import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from PIL import Image
import piexif

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".webp"}
VIDEO_EXTS = {".mov", ".mp4"}

def run(cmd):
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()

# ---------- Timestamp helpers ----------

def parse_exif_datetime(value):
    if not value:
        return None
    try:
        return datetime.strptime(value.decode(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None

def get_image_timestamp(path):
    try:
        img = Image.open(path)
        exif_bytes = img.info.get("exif")
        if exif_bytes:
            exif = piexif.load(exif_bytes)

            for tag, label in [
                (piexif.ExifIFD.DateTimeOriginal, "DateTimeOriginal"),
                (piexif.ExifIFD.DateTimeDigitized, "DateTimeDigitized"),
            ]:
                dt = parse_exif_datetime(exif["Exif"].get(tag))
                if dt:
                    return dt, label

            dt = parse_exif_datetime(exif["0th"].get(piexif.ImageIFD.DateTime))
            if dt:
                return dt, "CreateDate"
    except Exception:
        pass

    return None, None

def get_video_timestamp(path):
    try:
        meta = run([
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format_tags=creation_time",
            path
        ])
        data = json.loads(meta)
        ts = data.get("format", {}).get("tags", {}).get("creation_time")
        if ts:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")), "QuickTimeCreationTime"
    except Exception:
        pass

    return None, None

def get_best_timestamp(path):
    ext = os.path.splitext(path)[1].lower()

    if ext in IMAGE_EXTS:
        dt, src = get_image_timestamp(path)
        if dt:
            return dt, src

    if ext in VIDEO_EXTS:
        dt, src = get_video_timestamp(path)
        if dt:
            return dt, src

    # Fallback (WhatsApp / Messenger friendly)
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts), "FileModifyDate"

# ---------- MOV → MP4 ----------

def convert_mov_to_mp4(path):
    mp4_path = os.path.splitext(path)[0] + ".mp4"

    try:
        subprocess.check_call([
            "ffmpeg", "-y",
            "-i", path,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c", "copy",
            mp4_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        method = "stream-copy"
    except Exception:
        subprocess.check_call([
            "ffmpeg", "-y",
            "-i", path,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-movflags", "+faststart",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-level", "4.2",
            "-c:a", "aac",
            mp4_path
        ]
        , stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        method = "re-encode"

    shutil.copystat(path, mp4_path)
    os.remove(path)

    return mp4_path, method

# ---------- Rename ----------

def safe_rename(path, new_name, directory):
    base, ext = os.path.splitext(new_name)
    counter = 1
    candidate = new_name

    while os.path.exists(candidate):
        candidate = f"{base}-{counter}{ext}"
        counter += 1

    os.rename(path, os.path.join(directory, candidate))
    return candidate

# ---------- Main ----------

def main(directory="."):
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue

        ext = os.path.splitext(name)[1].lower()

        # Convert MOV → MP4
        if ext == ".mov":
            new_path, method = convert_mov_to_mp4(path)
            print(f"{name}  →  {os.path.basename(new_path)}   [MOV→MP4:{method}]")
            path = new_path
            name = os.path.basename(new_path)
            ext = ".mp4"

        if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
            continue

        dt, source = get_best_timestamp(path)
        new_name = dt.strftime("%Y-%m-%d %H:%M:%S") + ext

        if name == new_name:
            continue

        final_name = safe_rename(path, new_name, directory)
        print(f"{name}  →  {final_name}   [{source}]")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    main(target)
