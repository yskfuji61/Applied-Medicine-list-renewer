from __future__ import annotations

import csv
from pathlib import Path

from pharmalist.encodings import detect_text_encoding
from pharmalist.models import CsvProfile, InputProfile


def discover_csv_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".csv" else []

    if not target.exists():
        raise FileNotFoundError(f"Target path does not exist: {target}")

    return sorted(path for path in target.rglob("*.csv") if path.is_file())


def profile_csv(path: Path) -> CsvProfile:
    encoding = detect_text_encoding(path)
    row_count = 0
    header: list[str] = []

    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        for index, row in enumerate(reader):
            if index == 0:
                header = row
                continue
            row_count += 1

    return CsvProfile(
        path=path,
        encoding=encoding,
        row_count=row_count,
        header=header,
        size_bytes=path.stat().st_size,
    )


def build_input_profile(target: Path) -> InputProfile:
    files = discover_csv_files(target)
    if not files:
        raise FileNotFoundError(f"No CSV files found under: {target}")

    return InputProfile(root=target, files=[profile_csv(path) for path in files])