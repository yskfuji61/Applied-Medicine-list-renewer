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

Windows build script も macOS 版と同じく sibling workspace を前提にし、親ディレクトリから入力データと旧採用医薬品リストを release へコピーします。

## Local Build on Windows

PowerShell で repo root に移動して次を実行します。

```powershell
.\scripts\build_windows_standalone.ps1
```

CI では repo に実データを置かない前提のため、`PHARMALIST_SKIP_DATA_BUNDLE=1` を使って code-only artifact を作れます。ローカル配布用 build ではこの変数を指定せず、実データを sibling workspace から同梱してください。

## Runtime Layout

- 実行ファイル: `dist/windows-standalone-release/薬剤リスト変換アプリ/薬剤リスト変換アプリ.exe`
- 入力データ: release 配下の `260508_Musashino_採用医薬品/references`
- 参照データ: release 配下の `旧採用医薬品リスト`
- レポート: release 配下の `docs/audit-reports`

## Docker on Windows

Windows ではネイティブ版に加えて Docker 版も使えます。PowerShell で repo root に移動して次を実行します。

```powershell
docker build -t pharmalist:local .
docker compose run --rm pharmalist
```

`compose.yaml` は sibling workspace の相対パスを使っているため、Windows 上でも同じディレクトリ構成ならそのまま使えます。