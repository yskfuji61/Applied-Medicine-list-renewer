# 薬剤リスト変換アプリ

武蔵野向けの新 CSV 群を、旧採用医薬品リスト互換の 5 ビューへ deterministic に変換し、差分レポートまで生成するアプリです。macOS standalone、Windows standalone、Docker CLI 実行をサポートします。

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
- `dist/windows-standalone-release/薬剤リスト変換アプリ/薬剤リスト変換アプリ.exe`
- `dist/薬剤リスト変換アプリ-standalone-windows.zip`
- `docs/macos-distribution-guide.html`
- `docs/windows-distribution-guide.md`

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

### Windows スタンドアロン版ビルド

```powershell
.\scripts\build_windows_standalone.ps1
```

Windows 版も sibling workspace 構成を前提にし、親ディレクトリ側の `260508_Musashino_採用医薬品` と `旧採用医薬品リスト` を release に取り込みます。

## Docker 実行

Docker 版は macOS の `.app` を置き換えるものではなく、既存 CLI をコンテナとして実行するための構成です。

### イメージを build する

```bash
docker build -t pharmalist:local .
```

### `docker run` で実行する

```bash
docker run --rm \
  -v "$PWD/../260508_Musashino_採用医薬品/references:/data/input:ro" \
  -v "$PWD/../旧採用医薬品リスト:/data/reference:ro" \
  -v "$PWD/../audit-reports:/data/audit" \
  pharmalist:local \
  publish-report /data/input /data/reference --name docker-run
```

PowerShell では次の形で実行できます。

```powershell
docker run --rm `
  -v "${PWD}\..\260508_Musashino_採用医薬品\references:/data/input:ro" `
  -v "${PWD}\..\旧採用医薬品リスト:/data/reference:ro" `
  -v "${PWD}\..\audit-reports:/data/audit" `
  pharmalist:local `
  publish-report /data/input /data/reference --name docker-run
```

container 内では次の固定 mount point を使います。

- 入力: `/data/input`
- 参照: `/data/reference`
- 監査レポート出力: `/data/audit`
- config: `/app/config/docker-defaults.json`

### Compose で実行する

この repo には sibling workspace 前提の `compose.yaml` を含めています。

```bash
docker compose run --rm pharmalist
```

PowerShell でも同じコマンドで実行できます。

```powershell
docker compose run --rm pharmalist
```

既定では `publish-report /data/input /data/reference --name docker-run` を実行します。別コマンドに切り替える場合は次のように override します。

```bash
docker compose run --rm pharmalist profile /data/input
```

### 署名と公証

```bash
export APPLE_SIGN_IDENTITY="Developer ID Application: YOUR NAME"
export APPLE_NOTARY_PROFILE="your-notary-profile"
./scripts/sign_and_notarize_macos.sh
```

## GitHub Actions

- Workflow: `.github/workflows/macos-standalone-release.yml`
- Workflow: `.github/workflows/windows-standalone-release.yml`
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
- Docker 版は CLI 実行専用です。macOS の `.app` ランチャーや Finder 連携は含みません。
- Windows ネイティブ版は `.exe` 配布で、署名やインストーラ生成はまだ含みません。
- 開発 repo は `Applied-Medicine-list-renewer`、実データと監査レポートは親ディレクトリ側に分離されています。
- 社外配布前には Developer ID 署名と notarization を行ってください。
