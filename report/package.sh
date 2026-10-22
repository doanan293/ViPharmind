#!/usr/bin/env bash
# Package the paper from the sources in this directory; nothing is copied into
# the repo, the archive is staged in a temporary directory.
#
#   ./package.sh overleaf      sources at the archive root, for "Upload Project"
#   ./package.sh camera-ready  SOICT File B: Source/, Corresponding_Author.txt
#                              and the signed licence form from submission/;
#                              without the scan yet, the archive is built without
#                              it (to send the rest to the signatory) and the scan
#                              must be added before uploading
#   ./package.sh camera-ready --final
#                              the same, but stops when the signed scan is missing
#
# The scan is the one PDF in submission/ whose name contains "signed" (any case, any
# prefix such as LTP_signed_scan.pdf); "unsigned" names are not taken for it.
set -euo pipefail
cd "$(dirname "$0")"

MAIN=SoICT2026_Agentic_RAG_Vietnamese_Pharmaceutical_Documents
SOURCES=("$MAIN.tex" "$MAIN.bbl" llncs.cls splncs04.bst references.bib sections tables figures)
SUBMISSION=submission
CONTACT="$SUBMISSION/Corresponding_Author.txt"

mode=${1:-}
final=${2:-}
case "$mode" in
  overleaf | camera-ready) ;;
  *) echo "usage: $0 overleaf|camera-ready [--final]" >&2; exit 2 ;;
esac
[[ -z $final || ( $mode == camera-ready && $final == --final ) ]] \
  || { echo "usage: $0 overleaf|camera-ready [--final]" >&2; exit 2; }

# The signed scan of the licence form: the PDF in submission/ named "...signed...".
find_licence() {
  local file name
  local -a found=()
  shopt -s nullglob nocaseglob
  for file in "$SUBMISSION"/*.pdf; do
    name=$(basename "$file")
    name=${name,,}
    if [[ $name == *signed* && $name != *unsigned* ]]; then
      found+=("$file")
    fi
  done
  shopt -u nullglob nocaseglob
  if ((${#found[@]} > 1)); then
    echo "more than one signed scan in $SUBMISSION/: ${found[*]}" >&2
    return 1
  fi
  LICENCE=${found[0]:-}
}

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
  find_licence || exit 1
  if [[ -n $LICENCE ]]; then
    cp "$LICENCE" "$stage/LTP_signed.pdf"
  elif [[ -n $final ]]; then
    echo "no signed scan of the licence form in $SUBMISSION/ (a PDF named ...signed...)" >&2
    exit 1
  else
    echo "warning: no signed scan in $SUBMISSION/; add it to the archive before uploading" >&2
  fi
fi

rm -f "$out"
(cd "$stage" && zip -q -r -X - .) >"$out"
unzip -l "$out"
if [[ $mode == camera-ready ]]; then
  echo "File A: $MAIN.pdf"
  echo "File B: $out"
fi
