from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CsvProfile:
    path: Path
    encoding: str
    row_count: int
    header: list[str]
    size_bytes: int


@dataclass(frozen=True)
class InputProfile:
    root: Path
    files: list[CsvProfile]

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_rows(self) -> int:
        return sum(file.row_count for file in self.files)


@dataclass(frozen=True)
class HeaderSelector:
    name: str
    occurrence: int = 1


@dataclass(frozen=True)
class SourceSchema:
    name: str
    file_patterns: tuple[str, ...]
    field_selectors: dict[str, tuple[HeaderSelector, ...]]


@dataclass(frozen=True)
class StandardDrugRecord:
    source_file: Path
    source_schema: str
    source_row_number: int
    tensu_code: str | None
    yj_code: str | None
    pharmacological_code: str | None
    pharmacological_name: str | None
    display_name: str | None
    generic_name: str | None
    unit: str | None
    adoption_flag: str | None
    adoption_status: str | None
    usage_purchase_flag: str | None
    extended_name: str | None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "source_file": str(self.source_file),
            "source_schema": self.source_schema,
            "source_row_number": self.source_row_number,
            "tensu_code": self.tensu_code,
            "yj_code": self.yj_code,
            "pharmacological_code": self.pharmacological_code,
            "pharmacological_name": self.pharmacological_name,
            "display_name": self.display_name,
            "generic_name": self.generic_name,
            "unit": self.unit,
            "adoption_flag": self.adoption_flag,
            "adoption_status": self.adoption_status,
            "usage_purchase_flag": self.usage_purchase_flag,
            "extended_name": self.extended_name,
        }


@dataclass(frozen=True)
class ColumnMapping:
    source_schema: str
    resolved_fields: dict[str, int]
    missing_fields: tuple[str, ...]