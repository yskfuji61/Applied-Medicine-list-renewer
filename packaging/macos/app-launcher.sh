#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONTENTS_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
APP_DIR=$(cd "$CONTENTS_DIR/.." && pwd)
RELEASE_DIR=$(cd "$APP_DIR/.." && pwd)
RUNTIME_DIR="$CONTENTS_DIR/Resources/runtime"
LOG_DIR="$RELEASE_DIR/logs"
LOG_FILE="$LOG_DIR/pharmalist-app.log"
REPORT_PATH="$RELEASE_DIR/docs/audit-reports/latest/diff-report.html"
TARGET_DIR="$RELEASE_DIR/260508_Musashino_採用医薬品/references"
REFERENCE_DIR="$RELEASE_DIR/旧採用医薬品リスト"
CONFIG_PATH="$RUNTIME_DIR/config/defaults.json"

mkdir -p "$LOG_DIR"

notify() {
  local message="$1"
  osascript -e "display notification \"${message//\"/\\\"}\" with title \"薬剤リスト変換アプリ\"" >/dev/null 2>&1 || true
}

alert() {
  local message="$1"
  osascript -e "display alert \"薬剤リスト変換アプリ\" message \"${message//\"/\\\"}\" as critical" >/dev/null 2>&1 || true
}

require_path() {
  local path="$1"
  local label="$2"
  if [[ ! -e "$path" ]]; then
    echo "Missing ${label}: ${path}" > "$LOG_FILE"
    alert "${label} が見つかりません。\n${path}"
    exit 1
  fi
}

require_path "$RUNTIME_DIR/src" "ランタイム"
require_path "$CONFIG_PATH" "設定ファイル"
require_path "$TARGET_DIR" "変換対象ディレクトリ"
require_path "$REFERENCE_DIR" "旧採用医薬品リスト"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 command not found" > "$LOG_FILE"
  alert "python3 が見つかりません。Python 3.10 以上をインストールしてください。"
  exit 1
fi

export PYTHONPATH="$RUNTIME_DIR/src"
cd "$RELEASE_DIR"

notify "変換を開始しました。"

if ! python3 -m pharmalist.cli publish-report \
  "$TARGET_DIR" \
  "$REFERENCE_DIR" \
  --config "$CONFIG_PATH" \
  --name "app" > "$LOG_FILE" 2>&1; then
  alert "変換に失敗しました。ログを開きます。"
  open -a TextEdit "$LOG_FILE" >/dev/null 2>&1 || true
  exit 1
fi

if [[ -f "$REPORT_PATH" ]]; then
  open "$REPORT_PATH" >/dev/null 2>&1 || true
fi

notify "変換が完了しました。最新レポートを開きます。"