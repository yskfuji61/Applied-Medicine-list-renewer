#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONTENTS_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
APP_DIR=$(cd "$CONTENTS_DIR/.." && pwd)
RELEASE_DIR=$(cd "$APP_DIR/.." && pwd)
RUNTIME_DIR="$CONTENTS_DIR/Resources/runtime"
APP_SUPPORT_DIR="$HOME/Library/Application Support/jp.musashino.pharmalist"
WORKSPACE_CACHE_PATH="$APP_SUPPORT_DIR/workspace-root.txt"
WORKSPACE_ROOT=""
LOG_DIR=""
LOG_FILE="$LOG_DIR/pharmalist-app.log"
REPORT_PATH=""
TARGET_DIR=""
REFERENCE_DIR=""
AUDIT_ROOT=""
CONFIG_TEMPLATE_PATH="$RUNTIME_DIR/config/defaults.json"
CONFIG_PATH=""

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

is_valid_workspace_root() {
  local candidate="$1"
  [[ -d "$candidate/260508_Musashino_採用医薬品/references" && -d "$candidate/旧採用医薬品リスト" ]]
}

read_cached_workspace_root() {
  if [[ -f "$WORKSPACE_CACHE_PATH" ]]; then
    local cached_path
    cached_path=$(<"$WORKSPACE_CACHE_PATH")
    if [[ -n "$cached_path" ]] && is_valid_workspace_root "$cached_path"; then
      echo "$cached_path"
      return 0
    fi
  fi
  return 1
}

cache_workspace_root() {
  local workspace_root="$1"
  mkdir -p "$APP_SUPPORT_DIR"
  printf '%s\n' "$workspace_root" > "$WORKSPACE_CACHE_PATH"
}

prompt_for_workspace_root() {
  while true; do
    local selected_path
    if ! selected_path=$(osascript <<'APPLESCRIPT'
set chosenFolder to choose folder with prompt "260508_Musashino_採用医薬品 と 旧採用医薬品リスト を含む作業フォルダを選択してください。"
POSIX path of chosenFolder
APPLESCRIPT
); then
      return 1
    fi
    selected_path=${selected_path%/}
    if is_valid_workspace_root "$selected_path"; then
      cache_workspace_root "$selected_path"
      echo "$selected_path"
      return 0
    fi
    osascript -e 'display alert "薬剤リスト変換アプリ" message "選択したフォルダに 260508_Musashino_採用医薬品/references と 旧採用医薬品リスト がありません。" as critical' >/dev/null 2>&1 || true
  done
}

find_workspace_root() {
  if [[ -n "${PHARMALIST_WORKSPACE_ROOT:-}" ]] && is_valid_workspace_root "$PHARMALIST_WORKSPACE_ROOT"; then
    echo "$PHARMALIST_WORKSPACE_ROOT"
    return 0
  fi
  if read_cached_workspace_root; then
    return 0
  fi
  local candidate="$RELEASE_DIR"
  while [[ "$candidate" != "/" ]]; do
    if is_valid_workspace_root "$candidate"; then
      cache_workspace_root "$candidate"
      echo "$candidate"
      return 0
    fi
    candidate=$(cd "$candidate/.." && pwd)
  done
  prompt_for_workspace_root
}

prepare_runtime_config() {
  local output_path="$1"
  CONFIG_TEMPLATE_PATH="$CONFIG_TEMPLATE_PATH" \
  WORKSPACE_ROOT="$WORKSPACE_ROOT" \
  OUTPUT_PATH="$output_path" python3 - <<'PY'
import json
import os
from pathlib import Path

template_path = Path(os.environ["CONFIG_TEMPLATE_PATH"])
workspace_root = Path(os.environ["WORKSPACE_ROOT"])
output_path = Path(os.environ["OUTPUT_PATH"])
payload = json.loads(template_path.read_text(encoding="utf-8"))
reference_root = workspace_root / "旧採用医薬品リスト"
worksheet = reference_root / "■作業シート-表1.csv"
payload["masters"]["pharmacological_code"] = str(reference_root / "薬効コード-表1.csv")
payload["pharmacological_fill"]["supplement_sources"] = [str(worksheet)]
payload["legacy_view_scope"]["reference_sources"] = [str(worksheet)]
payload["legacy_view_overrides"]["reference_sources"] = [str(worksheet)]
payload["legacy_view_order"]["source_files"] = {
    "worksheet": str(worksheet),
    "generic": str(reference_root / "一般名順-表1.csv"),
    "product": str(reference_root / "製品名順-表1.csv"),
    "pharmacological": str(reference_root / "薬効順-表1.csv"),
    "pharmacological_code": str(reference_root / "薬効コード-表1.csv"),
}
output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

if ! WORKSPACE_ROOT=$(find_workspace_root); then
  mkdir -p "$RELEASE_DIR/logs"
  LOG_DIR="$RELEASE_DIR/logs"
  LOG_FILE="$LOG_DIR/pharmalist-app.log"
  echo "Workspace root selection was cancelled or no valid workspace was found. Release dir: $RELEASE_DIR" > "$LOG_FILE"
  alert "作業フォルダを特定できませんでした。\n260508_Musashino_採用医薬品 と 旧採用医薬品リスト を含むフォルダを選択してください。"
  exit 1
fi

LOG_DIR="$WORKSPACE_ROOT/audit-reports/logs"
LOG_FILE="$LOG_DIR/pharmalist-app.log"
AUDIT_ROOT="$WORKSPACE_ROOT/audit-reports"
REPORT_PATH="$AUDIT_ROOT/latest/diff-report.html"
TARGET_DIR="$WORKSPACE_ROOT/260508_Musashino_採用医薬品/references"
REFERENCE_DIR="$WORKSPACE_ROOT/旧採用医薬品リスト"
CONFIG_PATH="$LOG_DIR/runtime-defaults.json"

mkdir -p "$LOG_DIR"
prepare_runtime_config "$CONFIG_PATH"

require_path "$RUNTIME_DIR/src" "ランタイム"
require_path "$CONFIG_TEMPLATE_PATH" "設定ファイルテンプレート"
require_path "$CONFIG_PATH" "設定ファイル"
require_path "$TARGET_DIR" "変換対象ディレクトリ"
require_path "$REFERENCE_DIR" "旧採用医薬品リスト"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 command not found" > "$LOG_FILE"
  alert "python3 が見つかりません。Python 3.10 以上をインストールしてください。"
  exit 1
fi

export PYTHONPATH="$RUNTIME_DIR/src"
export PHARMALIST_AUDIT_ROOT="$AUDIT_ROOT"
cd "$WORKSPACE_ROOT"

notify "変換を開始しました。"

if ! python3 -m pharmalist.cli publish-report \
  "$TARGET_DIR" \
  "$REFERENCE_DIR" \
  --config "$CONFIG_PATH" \
  --audit-root "$AUDIT_ROOT" \
  --name "app" > "$LOG_FILE" 2>&1; then
  alert "変換に失敗しました。ログを開きます。"
  open -a TextEdit "$LOG_FILE" >/dev/null 2>&1 || true
  exit 1
fi

if [[ -f "$REPORT_PATH" ]]; then
  open "$REPORT_PATH" >/dev/null 2>&1 || true
fi

notify "変換が完了しました。最新レポートを開きます。"