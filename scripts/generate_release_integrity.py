from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_platform(name: str) -> str:
    lowered = name.lower()
    if "windows" in lowered:
        return "windows"
    if "macos" in lowered:
        return "macos"
    return "unknown"


def parse_published_name_overrides(values: list[str]) -> dict[Path, str]:
    overrides: dict[Path, str] = {}
    for value in values:
        raw_path, separator, published_name = value.partition("=")
        if not separator or not raw_path or not published_name:
            raise SystemExit(
                f"invalid --published-name value: {value!r}; expected /path/to/asset=published-name"
            )
        asset_path = Path(raw_path).expanduser().resolve()
        overrides[asset_path] = published_name
    return overrides


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--checksum-name", required=True)
    parser.add_argument("--manifest-name", required=True)
    parser.add_argument("--release-tag", default="")
    parser.add_argument("--commit", default="")
    parser.add_argument("--asset", action="append", required=True)
    parser.add_argument(
        "--published-name",
        action="append",
        default=[],
        help="override checksum/manifest name for an asset using /path/to/asset=published-name",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    published_name_overrides = parse_published_name_overrides(args.published_name)

    assets: list[dict[str, object]] = []
    checksum_lines: list[str] = []

    for raw_asset in args.asset:
        asset_path = Path(raw_asset).expanduser().resolve()
        if not asset_path.is_file():
            raise SystemExit(f"missing asset: {asset_path}")
        digest = sha256_file(asset_path)
        published_name = published_name_overrides.get(asset_path, asset_path.name)
        checksum_lines.append(f"{digest}  {published_name}")
        assets.append(
            {
                "name": published_name,
                "source_name": asset_path.name,
                "sha256": digest,
                "size": asset_path.stat().st_size,
                "platform": infer_platform(published_name),
            }
        )

    checksum_path = output_dir / args.checksum_name
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    manifest_path = output_dir / args.manifest_name
    manifest_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_tag": args.release_tag or None,
        "commit": args.commit or None,
        "assets": assets,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())