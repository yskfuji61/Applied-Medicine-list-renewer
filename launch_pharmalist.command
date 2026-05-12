#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR"

WORKSPACE_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
INPUT_DIR="$WORKSPACE_DIR/260508_Musashino_採用医薬品/references"
REFERENCE_DIR="$WORKSPACE_DIR/旧採用医薬品リスト"
AUDIT_ROOT="$WORKSPACE_DIR/audit-reports"
CONFIG_PATH="$SCRIPT_DIR/config/defaults.json"

export PYTHONPATH="$SCRIPT_DIR/src"
export PHARMALIST_CONFIG="$CONFIG_PATH"
export PHARMALIST_AUDIT_ROOT="$AUDIT_ROOT"

echo "薬剤リスト変換を実行します..."
python3 -m pharmalist.cli publish-report \
  "$INPUT_DIR" \
  "$REFERENCE_DIR" \
  --audit-root "$AUDIT_ROOT" \
  --name "launcher"

REPORT_PATH="$AUDIT_ROOT/latest/diff-report.html"
if [[ -f "$REPORT_PATH" ]]; then
  echo "レポートを開きます: $REPORT_PATH"
  open "$REPORT_PATH"
fi