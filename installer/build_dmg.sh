#!/usr/bin/env bash
# Night Crew — macOS installer (.dmg) builder.
# Run on macOS AFTER `python build.py` has produced dist/Night Crew.app
#   ./installer/build_dmg.sh
# Output: installer/Night Crew.dmg  (drag-to-Applications installer)
set -e
cd "$(dirname "$0")/.."

APP="dist/Night Crew.app"
[ -d "$APP" ] || { echo "Build first: python build.py  (need $APP)"; exit 1; }

STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"      # drag-to-install target

OUT="installer/Night Crew.dmg"
rm -f "$OUT"
hdiutil create -volname "Night Crew" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
rm -rf "$STAGE"
echo "Built $OUT — share this. User drags Night Crew into Applications."
echo "Note: unsigned apps need right-click > Open the first time (Gatekeeper)."
