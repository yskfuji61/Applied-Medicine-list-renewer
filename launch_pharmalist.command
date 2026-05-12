#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
cd "$SCRIPT_DIR"

export PYTHONPATH="$SCRIPT_DIR/src"

echo "薬剤リスト変換を実行します..."
python3 -m pharmalist.cli publish-report \
  "260508_Musashino_採用医薬品/references" \
  "旧採用医薬品リスト" \
  --name "launcher"

REPORT_PATH="$SCRIPT_DIR/docs/audit-reports/latest/diff-report.html"
if [[ -f "$REPORT_PATH" ]]; then
  echo "レポートを開きます: $REPORT_PATH"
  open "$REPORT_PATH"
fi