from __future__ import annotations

from pathlib import Path

from pharmalist.models import ColumnMapping, HeaderSelector, SourceSchema


STANDARD_FIELDS = (
    "tensu_code",
    "yj_code",
    "pharmacological_code",
    "pharmacological_name",
    "display_name",
    "generic_name",
    "unit",
    "adoption_flag",
    "usage_purchase_flag",
    "extended_name",
)


SOURCE_SCHEMAS: tuple[SourceSchema, ...] = (
    SourceSchema(
        name="old_worksheet",
        file_patterns=("■作業シート-表1.csv",),
        field_selectors={
            "tensu_code": (HeaderSelector("点数ｺｰﾄﾞ"),),
            "yj_code": (HeaderSelector("YJコード"),),
            "pharmacological_code": (HeaderSelector("薬効コード"),),
            "pharmacological_name": (HeaderSelector("薬効"),),
            "display_name": (HeaderSelector("表示用名称"),),
            "generic_name": (HeaderSelector("一般名称"),),
            "usage_purchase_flag": (HeaderSelector("用事購入薬品"),),
        },
    ),
    SourceSchema(
        name="reference_main",
        file_patterns=("260508_musashino_pharm_list.csv",),
        field_selectors={
            "tensu_code": (HeaderSelector("点数ｺｰﾄﾞ"),),
            "yj_code": (HeaderSelector("YJコード"),),
            "pharmacological_name": (HeaderSelector("薬効"),),
            "display_name": (HeaderSelector("表示用名称"),),
            "generic_name": (HeaderSelector("一般名称"), HeaderSelector("拡張正式名称１")),
            "unit": (HeaderSelector("単位"),),
            "adoption_flag": (HeaderSelector("採用フラグ"),),
            "extended_name": (
                HeaderSelector("メモに使用：拡張正式名称４"),
                HeaderSelector("拡張正式名称１"),
            ),
        },
    ),
    SourceSchema(
        name="reference_gaiyou",
        file_patterns=("260508_musashino_pharm_list_gaiyou.csv",),
        field_selectors={
            "tensu_code": (HeaderSelector("点数ｺｰﾄﾞ"),),
            "yj_code": (HeaderSelector("YJコード"),),
            "display_name": (HeaderSelector("表示用名称"),),
            "generic_name": (
                HeaderSelector("一般名称"),
                HeaderSelector("院外処方箋一般名称"),
                HeaderSelector("拡張正式名称１"),
            ),
            "unit": (HeaderSelector("単位"),),
            "adoption_flag": (HeaderSelector("採用フラグ"),),
            "usage_purchase_flag": (HeaderSelector("用時購入薬"),),
            "extended_name": (
                HeaderSelector("表示名称(拡張)"),
                HeaderSelector("メモに使用：拡張正式名称４"),
                HeaderSelector("拡張正式名称１"),
            ),
        },
    ),
    SourceSchema(
        name="reference_chusya",
        file_patterns=("260508_musashino_pharm_list_.chusya.csv",),
        field_selectors={
            "tensu_code": (HeaderSelector("点数ｺｰﾄﾞ"),),
            "yj_code": (HeaderSelector("YJコード"),),
            "display_name": (HeaderSelector("表示用名称"),),
            "generic_name": (
                HeaderSelector("一般名称", occurrence=1),
                HeaderSelector("表示名称(拡張)"),
            ),
            "unit": (HeaderSelector("単位"),),
            "adoption_flag": (HeaderSelector("採用薬"),),
            "extended_name": (
                HeaderSelector("表示名称(拡張)"),
                HeaderSelector("メモに使用：拡張正式名称４"),
            ),
        },
    ),
)


def canonicalize_header(value: str) -> str:
    return value.replace("\u3000", " ").strip()


def identify_source_schema(path: Path) -> SourceSchema:
    for schema in SOURCE_SCHEMAS:
        if any(pattern in path.name for pattern in schema.file_patterns):
            return schema
    raise ValueError(f"No source schema definition for file: {path.name}")


def resolve_column_mapping(header: list[str], schema: SourceSchema) -> ColumnMapping:
    positions: dict[str, list[int]] = {}
    for index, raw_name in enumerate(header):
        positions.setdefault(canonicalize_header(raw_name), []).append(index)

    resolved_fields: dict[str, int] = {}
    missing_fields: list[str] = []

    for field_name, selectors in schema.field_selectors.items():
        resolved_index = None
        for selector in selectors:
            available = positions.get(canonicalize_header(selector.name), [])
            wanted = selector.occurrence - 1
            if wanted < len(available):
                resolved_index = available[wanted]
                break
        if resolved_index is None:
            missing_fields.append(field_name)
            continue
        resolved_fields[field_name] = resolved_index

    return ColumnMapping(
        source_schema=schema.name,
        resolved_fields=resolved_fields,
        missing_fields=tuple(missing_fields),
    )