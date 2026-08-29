#!/usr/bin/env bash
# Prepare the device + build for a clean recording. Run ONCE, up front.
# Do NOT undo any of this until the video is finished and QC'd.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CFG(){ python3 "$HERE/_cfgsh.py" "$1"; }
REPO="${REPO:-$(CFG repo)}"
ENTRY="$REPO/$(CFG entry_js)"
PKG="$(CFG package)"

echo "== 1. patch the dev warning overlay out of the build (React Native only) =="
# ignoreAllLogs() is NOT enough: it leaves console.error banners and the full-screen
# inspector. uninstall() removes LogBox entirely. Skipped when entry_js is empty.
if [ -z "$(CFG entry_js)" ]; then
  echo "   no entry_js in config - skipping (not a React Native app, or no overlay to remove)"
elif grep -q 'LogBox.uninstall' "$ENTRY"; then
  echo "   already patched"
else
  cp "$ENTRY" "$ENTRY.demo-backup"
  python3 - "$ENTRY" <<'PY'
import re,sys
p=sys.argv[1]; s=open(p).read()
add=("\n// TEMPORARY (demo recording): remove the dev warning overlay so no banner can appear\n"
     "// on screen. ignoreAllLogs() does NOT cover console.error. REVERT before commit.\n"
     "LogBox.ignoreAllLogs();\nLogBox.uninstall();\n")
if 'LogBox' not in s:
    add="\nimport { LogBox } from 'react-native';"+add
# insert after the last top-level import, wherever that is - anchoring on one project's
# specific line does not travel
lines=s.split("\n")
last=max((i for i,l in enumerate(lines) if l.startswith(('import ','const ')) and 'require(' in l
          or l.startswith('import ')), default=-1)
if last<0: sys.exit("could not find an import block in %s - patch it by hand" % p)
lines.insert(last+1,add)
open(p,'w').write("\n".join(lines)); print("   patched")
PY
fi

echo "== 2. rebuild + install (debug APK bakes the JS bundle; editing source alone does nothing) =="
( cd "$REPO" && eval "$(CFG build_cmd)" ) >/tmp/demo-preflight-build.log 2>&1 \
  && echo "   build OK" || { echo "   BUILD FAILED - see /tmp/demo-preflight-build.log"; exit 1; }

echo "== 3. device settings =="
adb shell settings put system show_touches 0     # we draw our own pointer in post
adb shell svc power stayon true
adb shell cmd notification set_dnd priority >/dev/null 2>&1 || true
# Disabling the IME does two jobs: no soft keyboard covering the canvas, and `input text`
# stops being mangled by composing text (this is what made renaming a label unfixable in v5).
# Android restores the default IME on its own, so rec.py re-asserts this before every text
# action - do not rely on it holding from here.
adb shell ime disable "$(CFG ime)" >/dev/null 2>&1 || true
echo "   show_touches off, screen stays on, DND on, soft keyboard disabled"

echo "== 4. cache the whisper model at a stable path (verifies the narration later) =="
MODEL="$HOME/.cache/whisper/ggml-base.en.bin"
mkdir -p "$(dirname "$MODEL")"
if [ ! -s "$MODEL" ]; then
  command -v whisper-cli >/dev/null || brew install whisper-cpp
  curl -sL -o "$MODEL" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
  echo "   model downloaded"
else
  echo "   model cached"
fi
echo
echo "PREFLIGHT DONE. Leave the IME alone (see SKILL.md gotcha 5) and do not revert"
echo "anything until the final video has passed qc.py."
