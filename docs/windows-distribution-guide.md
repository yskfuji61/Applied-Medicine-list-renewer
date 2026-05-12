# Windows Distribution Guide

## Overview

Windows ネイティブ版は PyInstaller による standalone 配布です。生成物は `dist/windows-standalone-release/薬剤リスト変換アプリ/` と `dist/薬剤リスト変換アプリ-standalone-windows.zip` です。

## Expected Sibling Layout

```text
薬剤リスト/
  Applied-Medicine-list-renewer/
  260508_Musashino_採用医薬品/
  旧採用医薬品リスト/
  audit-reports/
  dist/
```

Windows build script も macOS 版と同じく sibling workspace を前提にしますが、入力データと旧採用医薬品リストは release へコピーしません。

## Local Build on Windows

PowerShell で repo root に移動して次を実行します。

```powershell
.\scripts\build_windows_standalone.ps1
```

生成された release は、上位階層のどこかに `260508_Musashino_採用医薬品` と `旧採用医薬品リスト` がある sibling workspace で実行してください。

## Runtime Layout

- 実行ファイル: `dist/windows-standalone-release/薬剤リスト変換アプリ/薬剤リスト変換アプリ.exe`
- 入力データ: 上位階層のどこかにある `260508_Musashino_採用医薬品/references`
- 参照データ: 上位階層のどこかにある `旧採用医薬品リスト`
- レポート: sibling workspace 側の `audit-reports`

## Docker on Windows

Windows ではネイティブ版に加えて Docker 版も使えます。PowerShell で repo root に移動して次を実行します。

```powershell
docker build -t pharmalist:local .
docker compose run --rm pharmalist
```

`compose.yaml` は sibling workspace の相対パスを使っているため、Windows 上でも同じディレクトリ構成ならそのまま使えます。

Docker image 自体にも実データは含めません。入力と参照は必ず host 側から mount します。