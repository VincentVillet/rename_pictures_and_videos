import os
import sys
from datetime import datetime
from PIL import Image
import piexif

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".webp"}


def parse_exif_datetime(value):
    if not value:
        return None
    try:
        return datetime.strptime(value.decode(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def get_best_timestamp(path):
    # 1) Try EXIF
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

    # 2) Fallback: filesystem modified time (WhatsApp-friendly)
    ts = os.path.getmtime(path)
    return datetime.fromtimestamp(ts), "FileModifyDate"


def safe_rename(path, new_name, directory):
    base, ext = os.path.splitext(new_name)
    counter = 1
    candidate = new_name

    while os.path.exists(candidate):
        candidate = f"{base}-{counter}{ext}"
        counter += 1

    os.rename(path, os.path.join(directory, candidate))
    return candidate


def main(directory="."):
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue

        ext = os.path.splitext(name)[1].lower()
        if ext not in SUPPORTED_EXTS:
            continue

        dt, source = get_best_timestamp(path)
        new_name = dt.strftime("%Y-%m-%d %H:%M:%S") + ext

        if name == new_name:
            continue

        final_name = safe_rename(path, new_name, directory)
        print(f"{name}  →  {final_name}   [{source}]")


if __name__ == "__main__":
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    main(target_dir)
