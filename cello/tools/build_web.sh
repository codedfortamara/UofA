#!/usr/bin/env bash
# Assemble the deployable static site into cello/build/claudecello.
# The curriculum is shared with the Android app, so it is copied in here
# rather than duplicated in the web source tree.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="${1:-$root/build/claudecello}"

rm -rf "$out"
mkdir -p "$out"
cp -r "$root/web/." "$out/"
cp "$root/shared/curriculum.json" "$out/curriculum.json"

# Stamp the service worker cache name so a deploy actually invalidates.
stamp="$(date -u +%Y%m%d%H%M%S)"
sed -i "s/const VERSION = 'claudecello-v1';/const VERSION = 'claudecello-${stamp}';/" "$out/sw.js"

missing=0
for f in index.html app.css curriculum.json manifest.webmanifest sw.js \
         js/app.js js/pitch.js js/music.js js/analysis.js js/tuner.js js/lessons.js js/tone.js js/store.js js/audio.js \
         worklet/capture.js icons/icon.svg icons/icon-192.png icons/icon-512.png icons/icon-maskable-512.png \
         fonts/fraunces-latin-wght-normal.woff2 fonts/quicksand-latin-wght-normal.woff2; do
  if [ ! -f "$out/$f" ]; then echo "MISSING: $f"; missing=1; fi
done
[ "$missing" -eq 0 ] || { echo "build incomplete"; exit 1; }

echo "built -> $out ($(find "$out" -type f | wc -l) files, $(du -sh "$out" | cut -f1))"
