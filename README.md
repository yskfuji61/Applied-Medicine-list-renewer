# 薬剤リスト変換アプリ

武蔵野向けの新 CSV 群を、旧採用医薬品リスト互換の 5 ビューへ deterministic に変換し、差分レポートまで生成する macOS 向けアプリです。

## 現在の構成

このリポジトリは sibling workspace 構成を前提にしています。

```text
薬剤リスト/
  Applied-Medicine-list-renewer/
  260508_Musashino_採用医薬品/
  旧採用医薬品リスト/
  audit-reports/
  dist/
```

コードと build scripts は `Applied-Medicine-list-renewer` から実行し、入力データと旧採用リスト、監査レポートは親ディレクトリ配下に置きます。

## 主な配布物

- `dist/macos-standalone-release/薬剤リスト変換アプリ.app`
- `dist/薬剤リスト変換アプリ-standalone-macos.zip`
- `docs/macos-distribution-guide.html`

## ローカル実行

### CLI

```bash
PYTHONPATH=src python3 -m pharmalist.cli publish-report \
  ../260508_Musashino_採用医薬品/references \
  ../旧採用医薬品リスト \
  --name local-run \
  --audit-root ../audit-reports
```

または次の環境変数を使います。

```bash
export PHARMALIST_CONFIG="$PWD/config/defaults.json"
export PHARMALIST_AUDIT_ROOT="$PWD/../audit-reports"
PYTHONPATH=src python3 -m pharmalist.cli publish-report \
  ../260508_Musashino_採用医薬品/references \
  ../旧採用医薬品リスト \
  --name local-run
```

### スタンドアロン版ビルド

```bash
./scripts/build_macos_standalone.sh
```

build script は親ディレクトリにある `260508_Musashino_採用医薬品` と `旧採用医薬品リスト` を自動で取り込みます。

### 署名と公証

```bash
export APPLE_SIGN_IDENTITY="Developer ID Application: YOUR NAME"
export APPLE_NOTARY_PROFILE="your-notary-profile"
./scripts/sign_and_notarize_macos.sh
```

## GitHub Actions

- Workflow: `.github/workflows/macos-standalone-release.yml`
- 必須 secrets:
  - `MACOS_CERTIFICATE_BASE64`
  - `MACOS_CERTIFICATE_PASSWORD`
  - `KEYCHAIN_PASSWORD`
  - `APPLE_SIGN_IDENTITY`
  - `APPLE_ID`
  - `APPLE_APP_SPECIFIC_PASSWORD`
  - `APPLE_TEAM_ID`

GitHub への secrets 投入は `./scripts/configure_github_actions_secrets.sh` を使って自動化できます。実行には GitHub CLI (`gh`) の認証と、対象リポジトリの remote が必要です。

## このマシンを署名・公証可能にする手順

### GitHub CLI

```bash
brew install gh
gh auth login
```

### Apple ローカル設定

フル Xcode を導入してから、次の環境変数を設定して実行します。

```bash
export APPLE_CERT_P12_PATH="/absolute/path/to/developer-id-application.p12"
export APPLE_CERT_P12_PASSWORD="p12-password"
export APPLE_ID="apple-id@example.com"
export APPLE_TEAM_ID="TEAMID1234"
export APPLE_APP_SPECIFIC_PASSWORD="xxxx-xxxx-xxxx-xxxx"
export KEYCHAIN_PASSWORD="your-login-keychain-password"
./scripts/setup_local_release_machine.sh
```

`notarytool` が見つからない場合は、App Store から Xcode を導入し、必要なら `sudo xcode-select -s /Applications/Xcode.app` を実行してください。

## 既知の前提

- 変換ロジックは旧採用医薬品リストとの完全一致を目標に調整済みです。
- スタンドアロン版は Python を同梱します。
- 開発 repo は `Applied-Medicine-list-renewer`、実データと監査レポートは親ディレクトリ側に分離されています。
- 社外配布前には Developer ID 署名と notarization を行ってください。
