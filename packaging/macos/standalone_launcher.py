from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

from pharmalist.cli import render_publish_report


APP_TITLE = "薬剤リスト変換アプリ"
APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "jp.musashino.pharmalist"
WORKSPACE_CACHE_PATH = APP_SUPPORT_DIR / "workspace-root.txt"


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


def _is_valid_workspace_root(candidate: Path) -> bool:
    return (candidate / "260508_Musashino_採用医薬品" / "references").exists() and (
        candidate / "旧採用医薬品リスト"
    ).exists()


def _cache_workspace_root(workspace_root: Path) -> None:
    APP_SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_CACHE_PATH.write_text(str(workspace_root) + "\n", encoding="utf-8")


def _read_cached_workspace_root() -> Path | None:
    if not WORKSPACE_CACHE_PATH.exists():
        return None
    cached_path = Path(WORKSPACE_CACHE_PATH.read_text(encoding="utf-8").strip()).expanduser()
    if cached_path and _is_valid_workspace_root(cached_path):
        return cached_path
    return None


def _prompt_for_workspace_root() -> Path:
    while True:
        selected = subprocess.run(
            [
                "osascript",
                "-e",
                'POSIX path of (choose folder with prompt "260508_Musashino_採用医薬品 と 旧採用医薬品リスト を含む作業フォルダを選択してください。")',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if selected.returncode != 0:
            raise FileNotFoundError(
                "入力データと旧採用医薬品リストを含む作業フォルダの選択がキャンセルされました。"
            )
        candidate = Path(selected.stdout.strip()).expanduser()
        if _is_valid_workspace_root(candidate):
            _cache_workspace_root(candidate)
            return candidate
        _display_alert(
            "選択したフォルダに 260508_Musashino_採用医薬品/references と 旧採用医薬品リスト がありません。"
        )


def _release_root() -> Path:
    executable = Path(sys.executable).resolve()
    if executable.name == "Python":
        return Path(__file__).resolve().parents[2]
    return executable.parents[3]


def _template_config_path(release_root: Path) -> Path:
    executable = Path(sys.executable).resolve()
    if executable.name == "Python":
        return release_root / "config" / "defaults.json"

    bundled_config = executable.parents[1] / "Resources" / "config" / "defaults.json"
    if bundled_config.exists():
        return bundled_config
    return release_root / "config" / "defaults.json"


def _find_workspace_root(release_root: Path) -> Path:
    env_override = os.environ.get("PHARMALIST_WORKSPACE_ROOT")
    if env_override:
        env_candidate = Path(env_override).expanduser().resolve()
        if _is_valid_workspace_root(env_candidate):
            _cache_workspace_root(env_candidate)
            return env_candidate

    cached_root = _read_cached_workspace_root()
    if cached_root is not None:
        return cached_root

    for candidate in (release_root, *release_root.parents):
        if _is_valid_workspace_root(candidate):
            _cache_workspace_root(candidate)
            return candidate
    return _prompt_for_workspace_root()


def _prepare_runtime_config(template_path: Path, workspace_root: Path, output_path: Path) -> Path:
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    reference_root = workspace_root / "旧採用医薬品リスト"
    worksheet = reference_root / "■作業シート-表1.csv"
    payload["masters"]["pharmacological_code"] = str(reference_root / "薬効コード-表1.csv")
    payload["pharmacological_fill"]["supplement_sources"] = [str(worksheet)]
    payload["legacy_view_scope"]["reference_sources"] = [str(worksheet)]
    payload["legacy_view_overrides"]["reference_sources"] = [str(worksheet)]
    payload["legacy_view_order"]["source_files"] = {
        "worksheet": str(worksheet),
        "generic": str(reference_root / "一般名順-表1.csv"),
        "product": str(reference_root / "製品名順-表1.csv"),
        "pharmacological": str(reference_root / "薬効順-表1.csv"),
        "pharmacological_code": str(reference_root / "薬効コード-表1.csv"),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _require_path(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} が見つかりません: {path}")


def main() -> int:
    release_root = _release_root()
    workspace_root = _find_workspace_root(release_root)
    logs_dir = workspace_root / "audit-reports" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "pharmalist-standalone.log"
    target_dir = workspace_root / "260508_Musashino_採用医薬品" / "references"
    reference_dir = workspace_root / "旧採用医薬品リスト"
    template_config_path = _template_config_path(release_root)
    config_path = logs_dir / "runtime-defaults.json"
    audit_root = workspace_root / "audit-reports"
    latest_report = audit_root / "latest" / "diff-report.html"

    try:
        os.chdir(workspace_root)
        _require_path(target_dir, "変換対象ディレクトリ")
        _require_path(reference_dir, "旧採用医薬品リスト")
        _require_path(template_config_path, "設定ファイル")
        _prepare_runtime_config(template_config_path, workspace_root, config_path)
        _display_notification("変換を開始しました。")
        summary = render_publish_report(
            target_dir,
            reference_dir,
            "standalone-app",
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
        _display_alert(f"変換に失敗しました。\nログ: {log_path}")
        if log_path.exists():
            _open_path(log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())