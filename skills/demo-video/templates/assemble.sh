#!/bin/bash
# Everything after recording. Safe to re-run: each stage overwrites its own output.
set -uo pipefail
cd "$(dirname "$0")"
export DEMO_DIR="$PWD"
S="${KIT:-$HOME/Desktop/adb-demo-video-kit}/scripts"
PY="${PY:-python3}"
step(){ echo; echo "===== $* ====="; }

step "GATE: raw clips - status bar / keyboard / dev-overlay intrusions"
$PY -u "$S/qc.py" clips --sheet qc.png --step 0.4 || echo "   (see above; post.py cuts banner ranges automatically)"
step "cards + stills"
$PY -u "$S/cards.py"            || exit 1
$PY -u "$S/cards.py" thumbnail  || exit 1
$PY -u "$S/stills.py"           || true
step "normalize takes"
$PY -u "$S/post.py" normalize   || exit 1
step "highlights from the measured spans"
$PY -u "$S/annots.py"           || true
step "build: cut dead time, anchor every action to its sentence"
$PY -u "$S/post.py" build       || exit 1
step "overlay: pointer, highlights, subtitles"
$PY -u "$S/overlay.py"          || exit 1
step "GATE: narration/visual contract"
$PY -u "$S/audit.py" | tee AUDIT.txt
step "GATE: seams"
$PY -u "$S/continuity.py" | tee CONTINUITY.txt
step "deliver"
$PY -u "$S/deliver.py" video    || exit 1
step "contact sheet for the human pass"
$PY -u "$S/sheet.py" "$($PY -c "import sys;sys.path.insert(0,'$S');from cfg import CFG;print(CFG.out_name)")".mp4 contact-sheet.png || exit 1
echo "ASSEMBLE DONE - now LOOK at contact-sheet.png"
