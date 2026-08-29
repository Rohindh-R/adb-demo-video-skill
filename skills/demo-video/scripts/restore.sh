#!/usr/bin/env bash
# Undo preflight. Run ONLY after the final video is done and QC'd.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CFG(){ python3 "$HERE/_cfgsh.py" "$1"; }
REPO="${REPO:-$(CFG repo)}"
ENTRY="$REPO/$(CFG entry_js)"

echo "== 1. discard any unsaved on-device edits =="
echo "   (do this by hand in the app: Back -> Discard. Nothing was ever Saved,"
echo "    so the live store is untouched. Verify with a FRESH app launch.)"

echo "== 2. restore device settings =="
adb shell settings put system show_touches 0
adb shell svc power stayon false
adb shell cmd notification set_dnd off >/dev/null 2>&1 || true
adb shell ime enable "$(CFG ime)" >/dev/null 2>&1 || true

echo "== 3. revert the LogBox patch =="
if [ -f "$ENTRY.demo-backup" ]; then
  mv "$ENTRY.demo-backup" "$ENTRY"; echo "   reverted from backup"
elif grep -q 'LogBox.uninstall' "$ENTRY"; then
  git -C "$REPO" checkout -- "$ENTRY" && echo "   reverted with git checkout"
else
  echo "   nothing to revert"
fi
git -C "$REPO" status --porcelain "$ENTRY"

echo "== 4. rebuild so the dev build has LogBox back =="
echo "   IMPORTANT: the installed APK still has LogBox removed until you rebuild."
echo "   A dev build that hides warnings and errors is a debugging hazard."
( cd "$REPO" && eval "$(CFG build_cmd)" ) >/tmp/demo-restore-build.log 2>&1 \
  && echo "   build OK" || echo "   BUILD FAILED - see /tmp/demo-restore-build.log"
