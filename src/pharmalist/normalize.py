from __future__ import annotations

import csv
import re
from pathlib import Path

from pharmalist.encodings import detect_text_encoding
from pharmalist.mapping import identify_source_schema, resolve_column_mapping
from pharmalist.models import StandardDrugRecord
from pharmalist.profile import discover_csv_files
from pharmalist.rules import determine_adoption_status


PHARMACOLOGICAL_PATTERN = re.compile(r"^(?P<code>\d{4})[：:](?P<name>.+)$")


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.replace("\u3000", " ").strip()
    return cleaned or None


def _split_pharmacological_label(value: str | None) -> tuple[str | None, str | None]:
    cleaned = _clean_value(value)
    if cleaned is None:
        return None, None

    match = PHARMACOLOGICAL_PATTERN.match(cleaned)
    if not match:
        return None, cleaned

    return match.group("code"), _clean_value(match.group("name"))


def _build_record(
    path: Path,
    schema_name: str,
    row_number: int,
    row: list[str],
    resolved_fields: dict[str, int],
) -> StandardDrugRecord:
    def get_value(field_name: str) -> str | None:
        index = resolved_fields.get(field_name)
        if index is None or index >= len(row):
            return None
        return _clean_value(row[index])

    raw_pharmacological_code = get_value("pharmacological_code")
    raw_pharmacological_name = get_value("pharmacological_name")
    derived_pharmacological_code, derived_pharmacological_name = _split_pharmacological_label(
        raw_pharmacological_name
    )

    return StandardDrugRecord(
        source_file=path,
        source_schema=schema_name,
        source_row_number=row_number,
        tensu_code=get_value("tensu_code"),
        yj_code=get_value("yj_code"),
        pharmacological_code=raw_pharmacological_code or derived_pharmacological_code,
        pharmacological_name=derived_pharmacological_name or raw_pharmacological_name,
        display_name=get_value("display_name"),
        generic_name=get_value("generic_name"),
        unit=get_value("unit"),
        adoption_flag=get_value("adoption_flag"),
        adoption_status=determine_adoption_status(schema_name, get_value("adoption_flag")),
        usage_purchase_flag=get_value("usage_purchase_flag"),
        extended_name=get_value("extended_name"),
    )


def normalize_csv(path: Path, limit: int | None = None) -> tuple[list[StandardDrugRecord], tuple[str, ...]]:
    encoding = detect_text_encoding(path)
    schema = identify_source_schema(path)

    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        mapping = resolve_column_mapping(header, schema)

        records: list[StandardDrugRecord] = []
        for row_number, row in enumerate(reader, start=2):
            records.append(
                _build_record(
                    path=path,
                    schema_name=schema.name,
                    row_number=row_number,
                    row=row,
                    resolved_fields=mapping.resolved_fields,
                )
            )
            if limit is not None and len(records) >= limit:
                break

    return records, mapping.missing_fields


def normalize_target(target: Path, limit_per_file: int | None = None) -> list[tuple[Path, list[StandardDrugRecord], tuple[str, ...]]]:
    files = discover_csv_files(target)
    return [
        (path, *normalize_csv(path, limit=limit_per_file))
        for path in files
    ]