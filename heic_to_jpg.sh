#!/usr/bin/env bash
# heic_to_jpg.sh — convert all HEIC files in a folder to JPG, in place.
#
# EXIF metadata (DateTimeOriginal, GPS, camera make/model, dimensions) is
# preserved by `sips`; the filesystem mtime of the original is copied onto
# the new JPG with `touch -r` (some online albums fall back to it).
#
# Each HEIC is only deleted after its JPG has been written, is non-empty,
# and has a readable DateTimeOriginal. HEICs that already have a same-name
# .jpg neighbour are skipped to avoid silent overwrites.
#
# Usage:
#   ./heic_to_jpg.sh                   # operate on the current directory
#   ./heic_to_jpg.sh /path/to/folder   # operate on the given folder
#
# Requirements: macOS `sips` (built in) and `exiftool` (`brew install exiftool`).

set -u

dir="${1:-.}"
cd "$dir" || { echo "Cannot cd to $dir"; exit 1; }

shopt -s nullglob nocaseglob 2>/dev/null || setopt NULL_GLOB NO_CASE_GLOB 2>/dev/null

ok=0
skipped=0
failed=0
failed_files=""

for f in *.heic; do
  base="${f%.*}"
  out="${base}.jpg"

  if [ ! -s "$f" ]; then
    echo "SKIP (empty): $f"
    skipped=$((skipped + 1))
    continue
  fi

  if [ -e "$out" ] && [ "$out" != "$f" ]; then
    echo "SKIP (target exists): $out"
    skipped=$((skipped + 1))
    continue
  fi

  if sips -s format jpeg "$f" --out "$out" >/dev/null 2>&1 \
     && [ -s "$out" ] \
     && exiftool -s -s -s -DateTimeOriginal "$out" 2>/dev/null | grep -q .; then
    touch -r "$f" "$out"
    rm "$f"
    ok=$((ok + 1))
  else
    failed=$((failed + 1))
    failed_files="${failed_files}
  $f"
    [ -f "$out" ] && [ ! -s "$out" ] && rm "$out"
  fi
done

echo "Converted: $ok"
echo "Skipped:   $skipped"
echo "Failed:    $failed"
[ -n "$failed_files" ] && printf "Failed files:%s\n" "$failed_files"
