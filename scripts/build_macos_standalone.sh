#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
APP_NAME="薬剤リスト変換アプリ"
RELEASE_NAME="macos-standalone-release"
DIST_DIR="$PROJECT_DIR/dist"
RELEASE_DIR="$DIST_DIR/$RELEASE_NAME"
PYI_ROOT="$PROJECT_DIR/.tmp/pyinstaller-standalone"
PYI_DIST="$PYI_ROOT/dist"
PYI_BUILD="$PYI_ROOT/build"
APP_DIR="$RELEASE_DIR/$APP_NAME.app"
DOCS_DIR="$RELEASE_DIR/docs"
ICON_SOURCE="$PROJECT_DIR/assets/macos/app-icon.svg"
ICON_PNG="$PYI_ROOT/app-icon.png"
ICONSET_DIR="$PYI_ROOT/AppIcon.iconset"
ICNS_PATH="$PYI_ROOT/AppIcon.icns"
ZIP_PATH="$DIST_DIR/${APP_NAME}-standalone-macos.zip"

rm -rf "$RELEASE_DIR" "$PYI_ROOT"
mkdir -p "$RELEASE_DIR" "$DOCS_DIR" "$PYI_ROOT"

qlmanage -t -s 1024 -o "$PYI_ROOT" "$ICON_SOURCE" >/dev/null 2>&1
mv "$PYI_ROOT/app-icon.svg.png" "$ICON_PNG"
mkdir -p "$ICONSET_DIR"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
  doubled=$((size * 2))
  sips -z "$doubled" "$doubled" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

python3 -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_NAME" \
  --distpath "$PYI_DIST" \
  --workpath "$PYI_BUILD" \
  --specpath "$PYI_ROOT" \
  --icon "$ICNS_PATH" \
  --paths "$PROJECT_DIR/src" \
  "$PROJECT_DIR/packaging/macos/standalone_launcher.py"

cp -R "$PYI_DIST/$APP_NAME.app" "$APP_DIR"
codesign --force --deep --sign - "$APP_DIR" >/dev/null 2>&1 || true
cp -R "$PROJECT_DIR/config" "$RELEASE_DIR/"
cp -R "$PROJECT_DIR/260508_Musashino_採用医薬品" "$RELEASE_DIR/"
cp -R "$PROJECT_DIR/旧採用医薬品リスト" "$RELEASE_DIR/"
cp "$PROJECT_DIR/README.md" "$RELEASE_DIR/"
cp "$PROJECT_DIR/RELEASE_NOTES_TEMPLATE.md" "$RELEASE_DIR/"
cp "$PROJECT_DIR/docs/requirements-spec.html" "$DOCS_DIR/"
cp "$PROJECT_DIR/docs/macos-distribution-guide.html" "$DOCS_DIR/"

rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$RELEASE_DIR" "$ZIP_PATH"

echo "Standalone app bundle: $APP_DIR"
echo "Standalone release directory: $RELEASE_DIR"
echo "Standalone zip archive: $ZIP_PATH"