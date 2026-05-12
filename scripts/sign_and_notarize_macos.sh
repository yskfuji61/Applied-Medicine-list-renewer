#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
APP_NAME="薬剤リスト変換アプリ"
RELEASE_NAME="macos-standalone-release"
DIST_DIR="$PROJECT_DIR/dist"
RELEASE_DIR="$DIST_DIR/$RELEASE_NAME"
APP_DIR="$RELEASE_DIR/$APP_NAME.app"
ZIP_PATH="$DIST_DIR/${APP_NAME}-standalone-macos.zip"
SHA_PATH="$ZIP_PATH.sha256"

SIGN_IDENTITY=${APPLE_SIGN_IDENTITY:-}
NOTARY_PROFILE=${APPLE_NOTARY_PROFILE:-}

if [[ -z "$SIGN_IDENTITY" ]]; then
  echo "APPLE_SIGN_IDENTITY が未設定です。Developer ID Application の名前を設定してください。" >&2
  exit 1
fi

if [[ -z "$NOTARY_PROFILE" ]]; then
  echo "APPLE_NOTARY_PROFILE が未設定です。notarytool 用の keychain profile 名を設定してください。" >&2
  exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "アプリが見つかりません: $APP_DIR" >&2
  echo "先に ./scripts/build_macos_standalone.sh を実行してください。" >&2
  exit 1
fi

xattr -cr "$APP_DIR"

codesign \
  --force \
  --deep \
  --options runtime \
  --timestamp \
  --sign "$SIGN_IDENTITY" \
  "$APP_DIR"

codesign --verify --deep --strict --verbose=2 "$APP_DIR"

rm -f "$ZIP_PATH" "$SHA_PATH"
ditto -c -k --sequesterRsrc --keepParent "$RELEASE_DIR" "$ZIP_PATH"

xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
xcrun stapler staple "$APP_DIR"
spctl -a -vvv "$APP_DIR"
shasum -a 256 "$ZIP_PATH" > "$SHA_PATH"

echo "Signed app: $APP_DIR"
echo "Notarized zip: $ZIP_PATH"
echo "SHA256: $SHA_PATH"