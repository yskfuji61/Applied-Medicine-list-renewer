# Release Integrity Operations

この文書は、checksum 署名と provenance 公開の実運用を固定するための runbook です。対象は release 配布担当者です。

## Final Policy

- 公開側の一次検証手段は `SHA256SUMS.txt` と `SHA256SUMS.txt.minisig`、および `minisign.pub` とする。
- 受領者向けの正式な検証導線は README と GitHub Release notes に置く。
- GitHub Artifact Attestation は二次的な provenance として扱い、公開できる場合は併用してよいが、受領者の必須手順にはしない。
- release notes 本文だけで integrity を成立させない。検証データは必ず release asset として添付する。
- GitHub Releases のダウンロード名に合わせて `SHA256SUMS.txt` を生成する。label とローカル build ファイル名を基準にしない。

## Secret Key Handling

- `minisign.key` は release machine ローカル専用とし、CI secret に登録しない。
- passphrase を平文ファイルとして長期保存しない。パスワードマネージャかオフライン紙保管へ移行し、作業ディレクトリ内の一時ファイルは release 作業完了後に削除する。
- 秘密鍵の保管場所はフルディスク暗号化されたローカルストレージに限定する。
- 秘密鍵をコピーするのは暗号化済み backup 媒体だけに限定し、メッセンジャー、メール、クラウドメモへ送らない。

## Backup Policy

- バックアップは 2 系統持つ。1 つは手元管理、1 つは物理的に離れた保管場所に置く。
- バックアップ媒体は暗号化コンテナに入れ、秘密鍵と passphrase を同じ媒体に同居させない。
- 半年に 1 回、バックアップから `minisign.pub` を再生成できることをテストする。

## Rotation Policy

- 定期ローテーションは 12 か月ごと、または release machine 更新時に行う。
- 露出疑い、紛失、端末盗難、バックアップ不明化が起きたら即時ローテーションする。
- 新鍵へ切り替える release では、release notes に旧鍵終了と新公開鍵切り替えを明記する。
- 鍵切り替え後も、過去 release の検証用に旧公開鍵は参照可能な場所へ保持する。

## Loss / Compromise Response

- 秘密鍵露出が疑われた時点で、その鍵を信頼済みとして扱わない。
- GitHub Release notes と README に失効告知を出し、新公開鍵へ切り替えたことを明記する。
- 可能なら既存 release の integrity asset を新鍵で再発行し、どの時点から新鍵が有効かを書く。
- 根本原因が端末侵害の可能性を含む場合、その release machine は再利用しない。

## Release Operator Checklist

1. 配布 ZIP を確定する。
2. GitHub Release の asset 名を確認し、`SHA256SUMS.txt` はその公開名で生成する。
3. `SHA256SUMS.txt` に `minisign` 署名を付ける。
4. `SHA256SUMS.txt`、`SHA256SUMS.txt.minisig`、`minisign.pub` を Release へ upload する。
5. 隔離ディレクトリで Release から再ダウンロードし、README の受領者手順どおりに検証する。
6. 作業後、一時 passphrase ファイルが残っていないことを確認する。

## v2026.05.13 Verification Record

- 検証方法: この macOS ホスト上の隔離一時ディレクトリに Release asset を再ダウンロードして確認
- 取得ファイル: `-macos.zip`, `-standalone-macos.zip`, `-standalone-windows.zip`, `SHA256SUMS.txt`, `SHA256SUMS.txt.minisig`, `minisign.pub`
- 結果:
  - `minisign -V -p minisign.pub -m SHA256SUMS.txt -x SHA256SUMS.txt.minisig` 成功
  - `shasum -a 256 --check SHA256SUMS.txt` 成功
- 制約: 真の別マシン検証ではない。別 OS イメージまたは新規 VM での再検証が理想だが、この環境では隔離ディレクトリ再現までを実施した。