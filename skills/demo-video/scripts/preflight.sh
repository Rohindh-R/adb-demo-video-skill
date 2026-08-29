#!/usr/bin/env bash
# Prepare the device + build for a clean recording. Run ONCE, up front.
# Do NOT undo any of this until the video is finished and QC'd.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CFG(){ python3 "$HERE/_cfgsh.py" "$1"; }
REPO="${REPO:-$(CFG repo)}"
ENTRY="$REPO/$(CFG entry_js)"

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
if ( cd "$REPO" && eval "$(CFG build_cmd)" ) >/tmp/demo-preflight-build.log 2>&1; then
  echo "   build OK"
else
  echo "   BUILD FAILED - see /tmp/demo-preflight-build.log" >&2
  exit 1
fi

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
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
# Pinned: sha256 of the published LFS object (Hugging Face reports it as x-linked-etag). Without
# this a truncated or substituted download is fed straight to whisper-cli, and every sentence
# span the whole video is cut to comes from that model.
MODEL_SHA256="a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"
mkdir -p "$(dirname "$MODEL")"
model_ok(){ [ -s "$1" ] && [ "$(shasum -a 256 "$1" | cut -d' ' -f1)" = "$MODEL_SHA256" ]; }

if ! command -v whisper-cli >/dev/null; then
  echo "   whisper-cli not found - installing whisper-cpp via brew"
  brew install whisper-cpp
fi

if model_ok "$MODEL"; then
  echo "   model cached, checksum OK"
else
  [ -s "$MODEL" ] && echo "   cached model FAILED checksum - refetching"
  TMP="$(mktemp "${MODEL}.XXXXXX")"
  curl -fsSL -o "$TMP" "$MODEL_URL"
  if ! model_ok "$TMP"; then
    rm -f "$TMP"
    echo "   DOWNLOADED MODEL FAILED CHECKSUM - refusing to use it" >&2
    exit 1
  fi
  mv "$TMP" "$MODEL"
  echo "   model downloaded, checksum OK"
fi
echo
echo "PREFLIGHT DONE. Leave the IME alone (see SKILL.md gotcha 5) and do not revert"
echo "anything until the final video has passed qc.py."
