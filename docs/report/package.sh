#!/usr/bin/env bash
# Package the paper from the sources in this directory; nothing is copied into
# the repo, the archive is staged in a temporary directory.
#
#   ./package.sh overleaf      sources at the archive root, for "Upload Project"
#   ./package.sh camera-ready  SOICT File B: Source/, Corresponding_Author.txt
#                              and the signed licence form from submission/;
#                              without the scan yet, the archive is built without
#                              it and the scan must be added before uploading
set -euo pipefail
cd "$(dirname "$0")"

MAIN=SoICT2026_Agentic_RAG_Vietnamese_Pharmaceutical_Documents
SOURCES=("$MAIN.tex" "$MAIN.bbl" llncs.cls splncs04.bst references.bib sections tables figures)
SUBMISSION=submission
CONTACT="$SUBMISSION/Corresponding_Author.txt"
LICENCE="$SUBMISSION/LTP_signed.pdf"

mode=${1:-}
case "$mode" in
  overleaf | camera-ready) ;;
  *) echo "usage: $0 overleaf|camera-ready" >&2; exit 2 ;;
esac

# Build first so the PDF, the .bbl and the archived sources are the same version.
latexmk -quiet >/dev/null 2>&1 || { echo "build failed, run latexmk to see why" >&2; exit 1; }

stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT

if [[ $mode == overleaf ]]; then
  out=$MAIN.zip
  cp -r "${SOURCES[@]}" "$stage/"
else
  [[ -f $CONTACT ]] || { echo "missing $CONTACT" >&2; exit 1; }
  out=$SUBMISSION/${MAIN}_camera_ready.zip
  mkdir "$stage/Source"
  cp -r "${SOURCES[@]}" "$stage/Source/"
  cp "$CONTACT" "$stage/"
  if [[ -f $LICENCE ]]; then
    cp "$LICENCE" "$stage/"
  else
    echo "warning: $LICENCE not found; add the signed scan to the archive before uploading" >&2
  fi
fi

rm -f "$out"
(cd "$stage" && zip -q -r -X - .) >"$out"
unzip -l "$out"
if [[ $mode == camera-ready ]]; then
  echo "File A: $MAIN.pdf"
  echo "File B: $out"
fi
