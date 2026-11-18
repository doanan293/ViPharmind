#!/usr/bin/env bash
# Build → stamp → check → export → render the SoICT 2026 A0 poster.
# Usage: docs/poster/build/make.sh [render_dir]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
POSTER="$(dirname "$HERE")"
SK="$(cd "$POSTER/../.." && pwd)/.claude/skills/ppt-master/scripts"
W="$POSTER/projects/poster_a0"
PY=/usr/bin/python3
OUT="${1:-}"

if [ ! -f "$HERE/template-a0.pptx" ]; then
  $PY "$HERE/make_template.py" > /dev/null
fi
if [ ! -f "$W/analysis/roundtrip_manifest.json" ]; then
  # The workspace is generated, not versioned: rebuild it from the A0 template.
  $PY "$SK/pptx_to_svg.py" "$HERE/template-a0.pptx" -o "$W" --inheritance-mode both --roundtrip > /dev/null
  mkdir -p "$W/validation" "$W/notes" "$W/images"
fi
$PY "$HERE/build_poster.py"
$PY "$SK/stamp_native_fallbacks.py" "$W/authoring-svg-flat" --write >/dev/null
$PY "$SK/svg_authoring_view.py" "$W/authoring-svg-flat" --refresh-summary >/dev/null
$PY "$SK/svg_quality_checker.py" "$W" --roundtrip --json > "$W/validation/quality.txt" 2>&1 || {
  grep -E "ERROR" "$W/validation/quality.txt" | head -40; exit 1; }
rm -f "$W"/exports/*.pptx
$PY "$SK/svg_to_pptx.py" "$W" --roundtrip --native-charts-and-tables --primary-language en-US > "$W/validation/export.log" 2>&1 || {
  grep -E "Error|ERROR" "$W/validation/export.log" | head -40; exit 1; }
grep -E "Round-trip export summary|\[POSTFLIGHT\] status|\[PPTX\]" "$W/validation/export.log"
EXPORT="$(ls -t "$W"/exports/*.pptx | head -1)"
cp "$EXPORT" "$POSTER/SoICT2026_ViPharmInd_poster.pptx"
echo "pptx: $POSTER/SoICT2026_ViPharmInd_poster.pptx"
$PY "$HERE/render_pdf.py"
SVG="$W/authoring-svg-flat/poster.svg"
$PY "$HERE/test_check_poster.py"
$PY "$HERE/test_check_numbers.py"
$PY "$HERE/check_poster.py" svg "$SVG"
$PY "$HERE/check_poster.py" pptx "$POSTER/SoICT2026_ViPharmInd_poster.pptx"
$PY "$HERE/check_poster.py" pdf "$POSTER/SoICT2026_ViPharmInd_poster.pdf"
$PY "$HERE/check_numbers.py" "$SVG"
$PY "$HERE/test_poster_output.py"
echo "all checks passed"
if [ -n "$OUT" ]; then
  rm -rf "$OUT"; mkdir -p "$OUT"
  cp "$EXPORT" "$OUT/poster.pptx"
  (cd "$OUT" && timeout 300 soffice --headless --convert-to pdf poster.pptx >/dev/null 2>&1 && pdftoppm -r 20 -png poster.pdf lo)
  echo "rendered: $OUT"
fi
