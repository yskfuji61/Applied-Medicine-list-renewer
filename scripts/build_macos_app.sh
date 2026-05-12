#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
WORKSPACE_DIR=$(cd "$PROJECT_DIR/.." && pwd)
APP_NAME="薬剤リスト変換アプリ"
RELEASE_NAME="macos-release"
DIST_DIR="$PROJECT_DIR/dist"
RELEASE_DIR="$DIST_DIR/$RELEASE_NAME"
APP_DIR="$RELEASE_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
RUNTIME_DIR="$RESOURCES_DIR/runtime"
TMP_DIR="$PROJECT_DIR/.tmp/macos-app-build"
ICON_SOURCE="$PROJECT_DIR/assets/macos/app-icon.svg"
ICON_PNG="$TMP_DIR/app-icon.png"
ICONSET_DIR="$TMP_DIR/AppIcon.iconset"
ZIP_PATH="$DIST_DIR/${APP_NAME}-macos.zip"
SOURCE_INPUT_DIR="$WORKSPACE_DIR/260508_Musashino_採用医薬品"
SOURCE_REFERENCE_DIR="$WORKSPACE_DIR/旧採用医薬品リスト"
RELEASE_NOTES_TEMPLATE="$PROJECT_DIR/docs/templates/release-assets/RELEASE_NOTES_TEMPLATE.md"

rm -rf "$RELEASE_DIR" "$TMP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR" "$RUNTIME_DIR" "$TMP_DIR" "$RELEASE_DIR/docs"

cp -R "$PROJECT_DIR/src" "$RUNTIME_DIR/"
cp -R "$PROJECT_DIR/config" "$RUNTIME_DIR/"
cp "$PROJECT_DIR/docs/requirements-spec.html" "$RELEASE_DIR/docs/"
if [[ -f "$PROJECT_DIR/docs/macos-distribution-guide.html" ]]; then
  cp "$PROJECT_DIR/docs/macos-distribution-guide.html" "$RELEASE_DIR/docs/"
fi
if [[ -f "$PROJECT_DIR/README.md" ]]; then
  cp "$PROJECT_DIR/README.md" "$RELEASE_DIR/"
fi
if [[ -f "$RELEASE_NOTES_TEMPLATE" ]]; then
  cp "$RELEASE_NOTES_TEMPLATE" "$RELEASE_DIR/RELEASE_NOTES_TEMPLATE.md"
fi
cp -R "$SOURCE_INPUT_DIR" "$RELEASE_DIR/"
cp -R "$SOURCE_REFERENCE_DIR" "$RELEASE_DIR/"

RUNTIME_CONFIG_PATH="$RUNTIME_DIR/config/defaults.json"
RUNTIME_CONFIG_PATH="$RUNTIME_CONFIG_PATH" python3 - <<'PY'
import json
import os
from pathlib import Path

config_path = Path(os.environ["RUNTIME_CONFIG_PATH"])
payload = json.loads(config_path.read_text(encoding="utf-8"))
release_rel = "../../../../旧採用医薬品リスト"
payload["masters"]["pharmacological_code"] = f"{release_rel}/薬効コード-表1.csv"
payload["pharmacological_fill"]["supplement_sources"] = [f"{release_rel}/■作業シート-表1.csv"]
payload["legacy_view_scope"]["reference_sources"] = [f"{release_rel}/■作業シート-表1.csv"]
payload["legacy_view_overrides"]["reference_sources"] = [f"{release_rel}/■作業シート-表1.csv"]
payload["legacy_view_order"]["source_files"] = {
  "worksheet": f"{release_rel}/■作業シート-表1.csv",
  "generic": f"{release_rel}/一般名順-表1.csv",
  "product": f"{release_rel}/製品名順-表1.csv",
  "pharmacological": f"{release_rel}/薬効順-表1.csv",
  "pharmacological_code": f"{release_rel}/薬効コード-表1.csv",
}
config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

qlmanage -t -s 1024 -o "$TMP_DIR" "$ICON_SOURCE" >/dev/null 2>&1
mv "$TMP_DIR/app-icon.svg.png" "$ICON_PNG"
mkdir -p "$ICONSET_DIR"

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
  doubled=$((size * 2))
  sips -z "$doubled" "$doubled" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/AppIcon.icns"

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>ja</string>
  <key>CFBundleDisplayName</key>
  <string>薬剤リスト変換アプリ</string>
  <key>CFBundleExecutable</key>
  <string>pharmalist-launcher</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>jp.musashino.pharmalist.launcher</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>薬剤リスト変換アプリ</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

install -m 755 "$PROJECT_DIR/packaging/macos/app-launcher.sh" "$MACOS_DIR/pharmalist-launcher"

rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$RELEASE_DIR" "$ZIP_PATH"

echo "App bundle: $APP_DIR"
echo "Release directory: $RELEASE_DIR"
echo "Zip archive: $ZIP_PATH"