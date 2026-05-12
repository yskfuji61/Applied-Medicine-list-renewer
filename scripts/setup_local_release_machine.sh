#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
KEYCHAIN_PATH=${APPLE_KEYCHAIN_PATH:-$HOME/Library/Keychains/login.keychain-db}
NOTARY_PROFILE=${APPLE_NOTARY_PROFILE:-local-notary}

required_vars=(
  APPLE_CERT_P12_PATH
  APPLE_CERT_P12_PASSWORD
  APPLE_ID
  APPLE_TEAM_ID
  APPLE_APP_SPECIFIC_PASSWORD
)

require_command() {
  local command_name=$1
  local install_hint=$2
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "$command_name が見つかりません。$install_hint" >&2
    exit 1
  fi
}

require_xcode_tool() {
  local tool_name=$1
  if ! xcrun --find "$tool_name" >/dev/null 2>&1; then
    echo "$tool_name が利用できません。フル Xcode を導入後、sudo xcode-select -s /Applications/Xcode.app を実行してください。" >&2
    exit 1
  fi
}

require_command security "macOS 標準コマンドが必要です。"
require_command codesign "Xcode Command Line Tools または Xcode を導入してください。"
require_xcode_tool notarytool

for name in "${required_vars[@]}"; do
  if [[ -z "${(P)name:-}" ]]; then
    echo "環境変数 $name が未設定です。" >&2
    exit 1
  fi
done

CERT_P12_PATH=${APPLE_CERT_P12_PATH}
CERT_P12_PASSWORD=${APPLE_CERT_P12_PASSWORD}

if [[ ! -f "$CERT_P12_PATH" ]]; then
  echo "証明書ファイルが見つかりません: $CERT_P12_PATH" >&2
  exit 1
fi

security unlock-keychain "$KEYCHAIN_PATH" >/dev/null 2>&1 || true
security import "$CERT_P12_PATH" \
  -k "$KEYCHAIN_PATH" \
  -P "$CERT_P12_PASSWORD" \
  -T /usr/bin/codesign \
  -T /usr/bin/security \
  -T /usr/bin/xcrun

security set-key-partition-list \
  -S apple-tool:,apple:,codesign: \
  -s \
  -k "${KEYCHAIN_PASSWORD:-}" \
  "$KEYCHAIN_PATH" >/dev/null 2>&1 || true

xcrun notarytool store-credentials "$NOTARY_PROFILE" \
  --apple-id "$APPLE_ID" \
  --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_SPECIFIC_PASSWORD"

echo "Imported certificate: $CERT_P12_PATH"
echo "Stored notary profile: $NOTARY_PROFILE"
echo "Available signing identities:"
security find-identity -v -p codesigning

cat <<EOF

次の環境変数を設定すると、署名・公証スクリプトをそのまま実行できます。

export APPLE_SIGN_IDENTITY="Developer ID Application: YOUR NAME"
export APPLE_NOTARY_PROFILE="$NOTARY_PROFILE"
./scripts/sign_and_notarize_macos.sh
EOF