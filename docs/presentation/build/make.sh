#!/usr/bin/env bash
# Build → stamp → check → export → render the SoICT 2026 deck.
# Usage: presentation/build/make.sh [render_dir]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PRES="$(dirname "$HERE")"
SK="$(cd "$PRES/.." && pwd)/.claude/skills/ppt-master/scripts"
W="$PRES/projects/soict2026_20261104"
PY=/usr/bin/python3
OUT="${1:-}"

if [ ! -f "$W/analysis/roundtrip_manifest.json" ]; then
  # The workspace is generated, not versioned: rebuild it from the template.
  $PY "$SK/pptx_to_svg.py" "$PRES/template.pptx" -o "$W" --inheritance-mode both --roundtrip > /dev/null
  mkdir -p "$W/validation" "$W/notes" "$W/images"
fi
$PY "$HERE/build_deck.py"
$PY "$SK/stamp_native_fallbacks.py" "$W/authoring-svg-flat" --write >/dev/null
$PY "$SK/svg_authoring_view.py" "$W/authoring-svg-flat" --refresh-summary >/dev/null
$PY "$SK/svg_quality_checker.py" "$W" --roundtrip --json > "$W/validation/quality.txt" 2>&1 || {
  grep -E "ERROR" "$W/validation/quality.txt" | head -40; exit 1; }
rm -f "$W"/exports/*.pptx
$PY "$SK/svg_to_pptx.py" "$W" --roundtrip --native-charts-and-tables --primary-language en-US > "$W/validation/export.log" 2>&1 || {
  grep -E "Error|ERROR" "$W/validation/export.log" | head -40; exit 1; }
grep -E "Round-trip export summary|\[POSTFLIGHT\] status|\[PPTX\]" "$W/validation/export.log"
DECK="$(ls -t "$W"/exports/*.pptx | head -1)"
cp "$DECK" "$PRES/SoICT2026_ViPharmInd_talk.pptx"
echo "deck: $PRES/SoICT2026_ViPharmInd_talk.pptx"
if [ -n "$OUT" ]; then
  rm -rf "$OUT"; mkdir -p "$OUT"
  cp "$DECK" "$OUT/deck.pptx"
  (cd "$OUT" && timeout 240 soffice --headless --convert-to pdf deck.pptx >/dev/null 2>&1 && pdftoppm -r 80 -png deck.pdf s)
  echo "rendered: $(ls "$OUT"/s-*.png | wc -l) pages in $OUT"
fi
