from __future__ import annotations

import subprocess
import sys
import traceback
import os
from pathlib import Path

from pharmalist.cli import render_publish_report


APP_TITLE = "薬剤リスト変換アプリ"


def _display_notification(message: str) -> None:
    escaped = message.replace('"', '\\"')
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{escaped}" with title "{APP_TITLE}"',
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _display_alert(message: str) -> None:
    escaped = message.replace('"', '\\"')
    subprocess.run(
        [
            "osascript",
            "-e",
            f'display alert "{APP_TITLE}" message "{escaped}" as critical',
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _open_path(path: Path) -> None:
    subprocess.run(["open", str(path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _release_root() -> Path:
    executable = Path(sys.executable).resolve()
    if executable.name == "Python":
        return Path(__file__).resolve().parents[2]
    return executable.parents[3]


def _require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} が見つかりません: {path}")


def main() -> int:
    release_root = _release_root()
    logs_dir = release_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "pharmalist-standalone.log"
    target_dir = release_root / "260508_Musashino_採用医薬品" / "references"
    reference_dir = release_root / "旧採用医薬品リスト"
    config_path = release_root / "config" / "defaults.json"
    latest_report = release_root / "docs" / "audit-reports" / "latest" / "diff-report.html"

    try:
        os.chdir(release_root)
        _require_path(target_dir, "変換対象ディレクトリ")
        _require_path(reference_dir, "旧採用医薬品リスト")
        _require_path(config_path, "設定ファイル")
        _display_notification("変換を開始しました。")
        summary = render_publish_report(
            target_dir,
            reference_dir,
            "standalone-app",
            config_path=config_path,
        )
        log_path.write_text(summary + "\n", encoding="utf-8")
        if latest_report.exists():
            _open_path(latest_report)
        _display_notification("変換が完了しました。最新レポートを開きます。")
        return 0
    except Exception as exc:
        details = "\n".join(traceback.format_exception(exc))
        log_path.write_text(details, encoding="utf-8")
        _display_alert(f"変換に失敗しました。\nログ: {log_path}")
        _open_path(log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())