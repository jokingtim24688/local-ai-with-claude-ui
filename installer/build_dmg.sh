#!/usr/bin/env bash
# Ai Heaven — macOS installer (.dmg) builder.
# Run on macOS AFTER `python build.py` has produced dist/Ai Heaven.app
#   ./installer/build_dmg.sh
# Output: installer/Ai Heaven.dmg  (drag-to-Applications installer)
set -e
cd "$(dirname "$0")/.."

APP="dist/Ai Heaven.app"
[ -d "$APP" ] || { echo "Build first: python build.py  (need $APP)"; exit 1; }

STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"      # drag-to-install target

OUT="installer/Ai Heaven.dmg"
rm -f "$OUT"
hdiutil create -volname "Ai Heaven" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
rm -rf "$STAGE"
echo "Built $OUT — share this. User drags Ai Heaven into Applications."
echo "Note: unsigned apps need right-click > Open the first time (Gatekeeper)."
