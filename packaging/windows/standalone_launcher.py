from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import traceback
from pathlib import Path

from pharmalist.cli import render_publish_report


APP_TITLE = "薬剤リスト変換アプリ"


def _message_box(message: str, style: int) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, style)


def _display_notification(message: str) -> None:
    _message_box(message, 0x40)


def _display_error(message: str) -> None:
    _message_box(message, 0x10)


def _open_path(path: Path) -> None:
    os.startfile(str(path))


def _release_root() -> Path:
    executable = Path(sys.executable).resolve()
    if executable.suffix.lower() != ".exe":
        return Path(__file__).resolve().parents[2]
    return executable.parent.parent


def _require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} が見つかりません: {path}")


def main() -> int:
    release_root = _release_root()
    logs_dir = release_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "pharmalist-standalone-windows.log"
    target_dir = release_root / "260508_Musashino_採用医薬品" / "references"
    reference_dir = release_root / "旧採用医薬品リスト"
    config_path = release_root / "config" / "defaults.json"
    audit_root = release_root / "docs" / "audit-reports"
    latest_report = audit_root / "latest" / "diff-report.html"

    try:
        os.chdir(release_root)
        _require_path(target_dir, "変換対象ディレクトリ")
        _require_path(reference_dir, "旧採用医薬品リスト")
        _require_path(config_path, "設定ファイル")
        summary = render_publish_report(
            target_dir,
            reference_dir,
            "standalone-windows-app",
            config_path=config_path,
            audit_root=audit_root,
        )
        log_path.write_text(summary + "\n", encoding="utf-8")
        if latest_report.exists():
            _open_path(latest_report)
        _display_notification("変換が完了しました。最新レポートを開きます。")
        return 0
    except Exception as exc:
        details = "\n".join(traceback.format_exception(exc))
        log_path.write_text(details, encoding="utf-8")
        _display_error(f"変換に失敗しました。\nログ: {log_path}")
        if log_path.exists():
            _open_path(log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())