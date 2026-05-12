#!/bin/zsh
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "gh コマンドが見つかりません。GitHub CLI をインストールしてください。" >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo ".git が見つかりません。GitHub リポジトリで実行してください。" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh が未認証です。先に gh auth login を実行してください。" >&2
  exit 1
fi

required_vars=(
  MACOS_CERTIFICATE_BASE64
  MACOS_CERTIFICATE_PASSWORD
  KEYCHAIN_PASSWORD
  APPLE_SIGN_IDENTITY
  APPLE_ID
  APPLE_APP_SPECIFIC_PASSWORD
  APPLE_TEAM_ID
)

for name in "${required_vars[@]}"; do
  if [[ -z "${(P)name:-}" ]]; then
    echo "環境変数 $name が未設定です。" >&2
    exit 1
  fi
done

for name in "${required_vars[@]}"; do
  printf '%s' "${(P)name}" | gh secret set "$name"
  echo "secret set: $name"
done

echo "GitHub Actions secrets の投入が完了しました。"