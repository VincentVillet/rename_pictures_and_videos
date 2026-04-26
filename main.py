import os
import json
import shutil
import argparse
import subprocess
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageOps
import piexif
import pillow_heif

pillow_heif.register_heif_opener()

# ---------- Supported extensions ----------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".webp"}
VIDEO_EXTS = {".mov", ".mp4"}

# ---------- Helpers ----------
def run(cmd):
    return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()

# ---------- Timestamp extraction ----------
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
            dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt_utc.astimezone().replace(tzinfo=None), "QuickTimeCreationTime"
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
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts), "FileModifyDate"

# ---------- MOV → H.264 MP4 conversion ----------
def convert_to_h264_mp4(path):
    """
    Converts MOV or MP4 videos to H.264 MP4 for smaller files.
    Returns the new file path and method used.
    """
    mp4_path = os.path.splitext(path)[0] + ".mp4"

    try:
        # Compress to H.264
        subprocess.check_call([
            "ffmpeg", "-y",
            "-i", path,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-map_metadata", "0",
            "-c:v", "libx264",
            "-crf", "24",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-movflags", "+faststart",
            mp4_path
        ])
        method = "H.264 compressed"
    except subprocess.CalledProcessError:
        # fallback: stream copy
        mp4_path = os.path.splitext(path)[0] + "_copy.mp4"
        subprocess.check_call([
            "ffmpeg", "-y",
            "-i", path,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c", "copy",
            mp4_path
        ])
        method = "stream-copy fallback"

    # Preserve timestamps
    shutil.copystat(path, mp4_path)
    os.remove(path)
    return mp4_path, method

# ---------- Burn timestamp ----------
BACKUP_DIRNAME = ".originals"

def has_burn_backup(path, directory):
    return os.path.exists(os.path.join(directory, BACKUP_DIRNAME, os.path.basename(path)))

def backup_original(path, directory):
    backup_dir = os.path.join(directory, BACKUP_DIRNAME)
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(path))
    shutil.copy2(path, backup_path)
    return backup_path

def _load_font(size):
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()

def burn_timestamp(path, dt):
    img = Image.open(path)
    exif_bytes = img.info.get("exif")

    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")

    if exif_bytes:
        try:
            exif_dict = piexif.load(exif_bytes)
            exif_dict["0th"][piexif.ImageIFD.Orientation] = 1
            exif_bytes = piexif.dump(exif_dict)
        except Exception:
            pass

    text = dt.strftime("%Y-%m-%d %H:%M")
    w, h = img.size
    base = min(w, h)
    font_size = max(14, int(base * 0.03))
    padding = max(10, int(base * 0.02))
    stroke = max(1, font_size // 12)
    font = _load_font(font_size)

    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = w - tw - padding - bbox[0]
    y = h - th - padding - bbox[1]

    draw.text((x, y), text, font=font, fill="white",
              stroke_width=stroke, stroke_fill="black")

    ext = os.path.splitext(path)[1].lower()
    save_kwargs = {}
    if ext in (".jpg", ".jpeg"):
        save_kwargs["quality"] = 95
    if exif_bytes and ext in (".jpg", ".jpeg", ".tiff", ".webp", ".heic"):
        save_kwargs["exif"] = exif_bytes

    img.save(path, **save_kwargs)

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

# ---------- Main pipeline ----------
def main(directory=".", shift_hours=0, burn_date=False, assume_yes=False):
    if burn_date:
        images = [
            n for n in os.listdir(directory)
            if os.path.isfile(os.path.join(directory, n))
            and os.path.splitext(n)[1].lower() in IMAGE_EXTS
        ]
        if images and not assume_yes:
            backup_dir = os.path.join(directory, BACKUP_DIRNAME)
            print(f"About to burn timestamps onto up to {len(images)} images in {directory}.")
            print(f"Originals will be copied to {backup_dir}/")
            print("This will overwrite the originals in place.")
            resp = input("Continue? [y/N] ").strip().lower()
            if resp != "y":
                print("Aborted.")
                return

    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue

        ext = os.path.splitext(name)[1].lower()

        # Convert MOV and MP4 videos
        if ext in {".mov"}:
            new_path, method = convert_to_h264_mp4(path)
            print(f"{name} → {os.path.basename(new_path)} [{method}]")
            path = new_path
            name = os.path.basename(new_path)
            ext = ".mp4"

        # Skip unsupported files
        if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
            continue

        # Rename file using best available timestamp
        dt, source = get_best_timestamp(path)
        if shift_hours:
            dt += timedelta(hours=shift_hours)
        new_name = dt.strftime("%Y-%m-%d %H:%M:%S") + ext
        if name != new_name:
            final_name = safe_rename(path, new_name, directory)
            print(f"{name} → {final_name} [{source}]")
            path = os.path.join(directory, final_name)
            name = final_name

        if burn_date and ext in IMAGE_EXTS:
            if has_burn_backup(path, directory):
                print(f"{name} [burn skipped — backup already exists]")
                continue
            try:
                backup_original(path, directory)
                burn_timestamp(path, dt)
                print(f"{name} [burned {dt.strftime('%Y-%m-%d %H:%M')}]")
            except Exception as e:
                print(f"{name} [burn failed: {e}]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rename pictures/videos by timestamp.")
    parser.add_argument("directory", nargs="?", default=".", help="Target directory")
    parser.add_argument("--shift-by", type=float, default=0, dest="shift_hours",
                        help="Shift all timestamps by this many hours (e.g. --shift-by=-5)")
    parser.add_argument("--burn-date", action="store_true",
                        help="Burn timestamp into images in place (originals → .originals/)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip the burn confirmation prompt")
    args = parser.parse_args()
    main(args.directory, args.shift_hours, args.burn_date, args.yes)
