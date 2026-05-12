from __future__ import annotations

import csv
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path

from pharmalist.config import (
    LegacyAliasRule,
    LegacyMatchRule,
    LegacyViewAdjustmentsConfig,
    LegacyViewOrderConfig,
    LegacyViewOverrideConfig,
    LegacyViewScopeConfig,
    PharmacologicalFillConfig,
    PharmacologicalHierarchyConfig,
    load_config,
)
from pharmalist.encodings import detect_text_encoding
from pharmalist.mapping import identify_source_schema, resolve_column_mapping
from pharmalist.models import StandardDrugRecord
from pharmalist.normalize import normalize_csv, normalize_target
from pharmalist.rules import should_include_in_adoption_views


WORKSHEET_HEADER = [
    "点数ｺｰﾄﾞ                                          ",
    "YJコード",
    "薬効コード",
    "薬効コード",
    "薬効",
    "表示用名称                                        ",
    "一般名称",
    "用事購入薬品",
]

SORTED_VIEW_HEADER = [
    "点数ｺｰﾄﾞ",
    "YJコード",
    "薬効コード",
    "薬効コード",
    "薬効",
    "表示用名称                                        ",
    "一般名称",
    "用事購入薬品",
]

PHARMACOLOGICAL_CODE_HEADER = ["大項目", "中項目", "コード", "", "名称"]

EMPTY_SORT_SENTINEL = chr(0x10FFFF)
TRACKED_FIELDS = (
    "tensu_code",
    "yj_code",
    "pharmacological_code",
    "pharmacological_name",
    "display_name",
    "generic_name",
    "unit",
    "adoption_flag",
    "adoption_status",
    "usage_purchase_flag",
    "extended_name",
)


@dataclass(frozen=True)
class FieldSource:
    source_schema: str
    source_file: Path
    source_row_number: int
    source_field: str
    value: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "source_schema": self.source_schema,
            "source_file": str(self.source_file),
            "source_row_number": self.source_row_number,
            "source_field": self.source_field,
            "value": self.value,
        }


@dataclass(frozen=True)
class ConsolidatedRecord:
    record: StandardDrugRecord
    order: int
    field_sources: dict[str, FieldSource]


@dataclass(frozen=True)
class PharmacologicalLookup:
    by_code: dict[str, tuple[str, FieldSource]]
    by_name: dict[str, tuple[str, FieldSource]]


@dataclass(frozen=True)
class SupplementLookup:
    by_field: dict[str, dict[str, tuple[str | None, str | None, FieldSource | None, FieldSource | None]]]


@dataclass(frozen=True)
class GeneratedViewsResult:
    outputs: dict[str, Path]
    contributions_by_view: dict[str, dict[str, list[dict[str, object]]]]


@dataclass(frozen=True)
class LegacyScopeLookup:
    by_field: dict[str, set[str]]


@dataclass(frozen=True)
class LegacyOverrideLookup:
    by_field: dict[str, dict[str, dict[str, str | int | Path | None]]]


def _row_key_for_view(view_name: str, row: tuple[str, ...] | list[str]) -> str:
    if view_name == "pharmacological_code":
        return (row[2] if len(row) > 2 else "").strip() or "<blank>"
    tensu_code = row[0].strip() if len(row) > 0 else ""
    yj_code = row[1].strip() if len(row) > 1 else ""
    display_name = row[5].strip() if len(row) > 5 else ""
    generic_name = row[6].strip() if len(row) > 6 else ""
    return tensu_code or yj_code or f"{display_name}|{generic_name}"


def _record_matches_rule(record: StandardDrugRecord, rule: LegacyMatchRule | LegacyAliasRule) -> bool:
    for field_name, expected_value in rule.match.items():
        actual_value = getattr(record, field_name, None)
        if _normalize_lookup_value(actual_value) != _normalize_lookup_value(expected_value):
            return False
    return True


def _reconsolidate_consolidated_records(
    records: list[ConsolidatedRecord],
    source_priority: dict[str, int],
) -> list[ConsolidatedRecord]:
    consolidated: dict[tuple[str, ...], ConsolidatedRecord] = {}
    for item in sorted(records, key=lambda current: current.order):
        key = _record_key(item.record)
        current = consolidated.get(key)
        if current is None:
            consolidated[key] = item
            continue

        current_priority = source_priority.get(current.record.source_schema, 0)
        next_priority = source_priority.get(item.record.source_schema, 0)
        if next_priority >= current_priority:
            consolidated[key] = _merge_consolidated_records(item, current)
        else:
            consolidated[key] = _merge_consolidated_records(current, item)

    return sorted(consolidated.values(), key=lambda item: item.order)


def _apply_legacy_view_adjustments_with_provenance(
    records: list[ConsolidatedRecord],
    adjustments: LegacyViewAdjustmentsConfig,
    source_priority: dict[str, int],
    config_path: Path | None,
) -> list[ConsolidatedRecord]:
    if not adjustments.explicit_exclusions and not adjustments.aliases:
        return records

    adjusted: list[ConsolidatedRecord] = []
    config_source = config_path or Path("config/defaults.json")
    for item in records:
        record = item.record
        if any(_record_matches_rule(record, rule) for rule in adjustments.explicit_exclusions):
            continue

        alias_rule = next((rule for rule in adjustments.aliases if _record_matches_rule(record, rule)), None)
        if alias_rule is None:
            adjusted.append(item)
            continue

        field_sources = dict(item.field_sources)
        overrides: dict[str, str | None] = {}
        for field_name, value in alias_rule.override.items():
            overrides[field_name] = value
            field_sources[field_name] = FieldSource(
                source_schema="legacy_view_adjustments",
                source_file=config_source,
                source_row_number=0,
                source_field=field_name,
                value=value,
            )

        adjusted.append(
            replace(
                item,
                record=replace(record, **overrides),
                field_sources=field_sources,
            )
        )

    return _reconsolidate_consolidated_records(adjusted, source_priority)


def _apply_legacy_duplicate_adjustments(
    records: list[ConsolidatedRecord],
    adjustments: LegacyViewAdjustmentsConfig,
) -> list[ConsolidatedRecord]:
    if not adjustments.explicit_duplicates:
        return records

    duplicated = list(records)
    for item in records:
        if any(_record_matches_rule(item.record, rule) for rule in adjustments.explicit_duplicates):
            duplicated.append(item)
    return duplicated


def _record_key(record: StandardDrugRecord) -> tuple[str, ...]:
    if record.tensu_code:
        return ("tensu", record.tensu_code)
    if record.yj_code:
        return ("yj", record.yj_code)
    return ("name", record.display_name or "", record.generic_name or "")


def _merge_record(preferred: StandardDrugRecord, other: StandardDrugRecord) -> StandardDrugRecord:
    def pick(field_name: str) -> str | None:
        preferred_value = getattr(preferred, field_name)
        return preferred_value if preferred_value not in (None, "") else getattr(other, field_name)

    return StandardDrugRecord(
        source_file=preferred.source_file,
        source_schema=preferred.source_schema,
        source_row_number=preferred.source_row_number,
        tensu_code=pick("tensu_code"),
        yj_code=pick("yj_code"),
        pharmacological_code=pick("pharmacological_code"),
        pharmacological_name=pick("pharmacological_name"),
        display_name=pick("display_name"),
        generic_name=pick("generic_name"),
        unit=pick("unit"),
        adoption_flag=pick("adoption_flag"),
        adoption_status=pick("adoption_status"),
        usage_purchase_flag=pick("usage_purchase_flag"),
        extended_name=pick("extended_name"),
    )


def _field_source_from_record(record: StandardDrugRecord, field_name: str) -> FieldSource | None:
    value = getattr(record, field_name)
    if value in (None, ""):
        return None
    return FieldSource(
        source_schema=record.source_schema,
        source_file=record.source_file,
        source_row_number=record.source_row_number,
        source_field=field_name,
        value=value,
    )


def _consolidated_record_from_record(record: StandardDrugRecord, order: int) -> ConsolidatedRecord:
    return ConsolidatedRecord(
        record=record,
        order=order,
        field_sources={
            field_name: source
            for field_name in TRACKED_FIELDS
            if (source := _field_source_from_record(record, field_name)) is not None
        },
    )


def _merge_consolidated_records(preferred: ConsolidatedRecord, other: ConsolidatedRecord) -> ConsolidatedRecord:
    merged_record = _merge_record(preferred.record, other.record)
    merged_sources: dict[str, FieldSource] = {}
    for field_name in TRACKED_FIELDS:
        preferred_value = getattr(preferred.record, field_name)
        other_value = getattr(other.record, field_name)
        if preferred_value not in (None, ""):
            source = preferred.field_sources.get(field_name)
            if source is not None:
                merged_sources[field_name] = source
        elif other_value not in (None, ""):
            source = other.field_sources.get(field_name)
            if source is not None:
                merged_sources[field_name] = source
    return ConsolidatedRecord(record=merged_record, order=preferred.order, field_sources=merged_sources)


def consolidate_records_with_provenance(
    records: list[StandardDrugRecord],
    source_priority: dict[str, int],
) -> list[ConsolidatedRecord]:
    consolidated: dict[tuple[str, ...], ConsolidatedRecord] = {}

    for order, record in enumerate(records):
        key = _record_key(record)
        current = consolidated.get(key)
        next_item = _consolidated_record_from_record(record, order)
        if current is None:
            consolidated[key] = next_item
            continue

        current_priority = source_priority.get(current.record.source_schema, 0)
        next_priority = source_priority.get(record.source_schema, 0)
        if next_priority >= current_priority:
            consolidated[key] = _merge_consolidated_records(next_item, current)
        else:
            consolidated[key] = _merge_consolidated_records(current, next_item)

    return sorted(consolidated.values(), key=lambda item: item.order)


def consolidate_records(records: list[StandardDrugRecord], source_priority: dict[str, int]) -> list[StandardDrugRecord]:
    return [item.record for item in consolidate_records_with_provenance(records, source_priority)]


def _sort_key(*values: str | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        if value is None or not value.strip():
            normalized.append(EMPTY_SORT_SENTINEL)
            continue
        normalized.append(value.replace("\u3000", " ").strip().casefold())
    return tuple(normalized)


def _normalize_lookup_value(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\u3000", " ").strip().casefold()


def _build_legacy_scope_lookup(scope_config: LegacyViewScopeConfig) -> LegacyScopeLookup:
    by_field = {field_name: set() for field_name in scope_config.match_fields}
    for source_path in scope_config.reference_sources:
        if not source_path.exists():
            continue
        records, _ = normalize_csv(source_path)
        for record in records:
            for field_name in scope_config.match_fields:
                value = getattr(record, field_name, None)
                normalized = _normalize_lookup_value(value)
                if normalized:
                    by_field[field_name].add(normalized)
    return LegacyScopeLookup(by_field=by_field)


def _build_legacy_override_lookup(override_config: LegacyViewOverrideConfig) -> LegacyOverrideLookup:
    by_field = {field_name: {} for field_name in override_config.match_fields}
    for source_path in override_config.reference_sources:
        if not source_path.exists():
            continue
        encoding = detect_text_encoding(source_path)
        schema = identify_source_schema(source_path)
        with source_path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            mapping = resolve_column_mapping(header, schema)
            for row_number, row in enumerate(reader, start=2):
                values = {
                    field_name: (
                        row[mapping.resolved_fields[field_name]]
                        if field_name in mapping.resolved_fields and mapping.resolved_fields[field_name] < len(row)
                        else None
                    )
                    for field_name in (*override_config.match_fields, *override_config.override_fields)
                }
                payload: dict[str, str | int | Path | None] = {
                    "source_file": source_path,
                    "source_row_number": row_number,
                    **values,
                }
                for field_name in override_config.match_fields:
                    value = values.get(field_name)
                    normalized = _normalize_lookup_value(value if isinstance(value, str) else None)
                    if normalized and normalized not in by_field[field_name]:
                        by_field[field_name][normalized] = payload
    return LegacyOverrideLookup(by_field=by_field)


def _apply_legacy_view_overrides_with_provenance(
    records: list[ConsolidatedRecord],
    override_config: LegacyViewOverrideConfig,
) -> list[ConsolidatedRecord]:
    if not override_config.enabled or not override_config.match_fields or not override_config.override_fields:
        return records

    lookup = _build_legacy_override_lookup(override_config)
    if not any(lookup.by_field.values()):
        return records

    overridden: list[ConsolidatedRecord] = []
    for item in records:
        matched_record = None
        for field_name in override_config.match_fields:
            value = getattr(item.record, field_name, None)
            normalized = _normalize_lookup_value(value)
            if normalized and normalized in lookup.by_field.get(field_name, {}):
                matched_record = lookup.by_field[field_name][normalized]
                break

        if matched_record is None:
            overridden.append(item)
            continue

        field_sources = dict(item.field_sources)
        overrides: dict[str, str | None] = {}
        for field_name in override_config.override_fields:
            value = matched_record.get(field_name)
            overrides[field_name] = value if isinstance(value, str) else None
            field_sources[field_name] = FieldSource(
                source_schema="old_worksheet",
                source_file=matched_record["source_file"],
                source_row_number=int(matched_record["source_row_number"]),
                source_field=field_name,
                value=overrides[field_name],
            )

        overridden.append(
            replace(
                item,
                record=replace(item.record, **overrides),
                field_sources=field_sources,
            )
        )
    return overridden


def apply_legacy_view_scope(
    records: list[StandardDrugRecord],
    scope_config: LegacyViewScopeConfig,
) -> list[StandardDrugRecord]:
    if not scope_config.enabled or not scope_config.match_fields:
        return records

    lookup = _build_legacy_scope_lookup(scope_config)
    if not any(lookup.by_field.values()):
        return records
    scoped: list[StandardDrugRecord] = []
    for record in records:
        include = False
        matched_field_name = None
        for field_name in scope_config.match_fields:
            value = getattr(record, field_name, None)
            normalized = _normalize_lookup_value(value)
            if normalized and normalized in lookup.by_field.get(field_name, set()):
                include = True
                matched_field_name = field_name
                break
        if not include:
            continue
        if should_include_in_adoption_views(record.adoption_status):
            scoped.append(record)
            continue
        if scope_config.include_non_adopted_matches and matched_field_name == "tensu_code":
            scoped.append(replace(record, adoption_status="legacy"))
    return scoped


def _normalize_code(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()


def _build_master_lookup(master_path: Path | None) -> PharmacologicalLookup:
    if master_path is None or not master_path.exists():
        return PharmacologicalLookup(by_code={}, by_name={})

    encoding = detect_text_encoding(master_path)
    by_code: dict[str, tuple[str, FieldSource]] = {}
    by_name: dict[str, tuple[str, FieldSource]] = {}
    with master_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row_number, row in enumerate(reader, start=2):
            if len(row) < 5:
                continue
            code = _normalize_code(row[2])
            name = (row[4] or "").strip()
            code_source = FieldSource(
                source_schema="pharmacological_code_master",
                source_file=master_path,
                source_row_number=row_number,
                source_field="code",
                value=code or None,
            )
            name_source = FieldSource(
                source_schema="pharmacological_code_master",
                source_file=master_path,
                source_row_number=row_number,
                source_field="name",
                value=name or None,
            )
            if code and name and code not in by_code:
                by_code[code] = (name, name_source)
            normalized_name = _normalize_lookup_value(name)
            if code and normalized_name and normalized_name not in by_name:
                by_name[normalized_name] = (code, code_source)
    return PharmacologicalLookup(by_code=by_code, by_name=by_name)


def _build_supplement_lookup(fill_config: PharmacologicalFillConfig) -> SupplementLookup:
    by_field: dict[str, dict[str, tuple[str | None, str | None, FieldSource | None, FieldSource | None]]] = {
        field_name: {} for field_name in fill_config.match_fields
    }
    for source_path in fill_config.supplement_sources:
        if not source_path.exists():
            continue
        records, _ = normalize_csv(source_path)
        for record in records:
            if not record.pharmacological_code and not record.pharmacological_name:
                continue
            for field_name in fill_config.match_fields:
                value = getattr(record, field_name, None)
                normalized = _normalize_lookup_value(value)
                if normalized and normalized not in by_field[field_name]:
                    by_field[field_name][normalized] = (
                        record.pharmacological_code,
                        record.pharmacological_name,
                        _field_source_from_record(record, "pharmacological_code"),
                        _field_source_from_record(record, "pharmacological_name"),
                    )
    return SupplementLookup(by_field=by_field)


def _fill_from_master(
    pharmacological_code: str | None,
    pharmacological_name: str | None,
    master_lookup: PharmacologicalLookup,
) -> tuple[str | None, str | None, FieldSource | None, FieldSource | None]:
    code = pharmacological_code
    name = pharmacological_name
    code_source = None
    name_source = None
    if code and not name:
        matched = master_lookup.by_code.get(_normalize_code(code))
        if matched is not None:
            name, name_source = matched
    if name and not code:
        matched = master_lookup.by_name.get(_normalize_lookup_value(name))
        if matched is not None:
            code, code_source = matched
    return code, name, code_source, name_source


def _apply_pharmacological_fill_rules_with_provenance(
    records: list[ConsolidatedRecord],
    fill_config: PharmacologicalFillConfig,
    master_path: Path | None,
) -> list[ConsolidatedRecord]:
    if not fill_config.match_fields and master_path is None:
        return records

    supplement_lookup = _build_supplement_lookup(fill_config)
    master_lookup = _build_master_lookup(master_path)
    completed: list[ConsolidatedRecord] = []

    for consolidated in records:
        record = consolidated.record
        field_sources = dict(consolidated.field_sources)
        code, name, code_source, name_source = _fill_from_master(
            record.pharmacological_code,
            record.pharmacological_name,
            master_lookup,
        )

        if not code or not name:
            for field_name in fill_config.match_fields:
                value = getattr(record, field_name, None)
                normalized = _normalize_lookup_value(value)
                if not normalized:
                    continue
                supplemented = supplement_lookup.by_field.get(field_name, {}).get(normalized)
                if supplemented is None:
                    continue
                supplemented_code, supplemented_name, supplemented_code_source, supplemented_name_source = supplemented
                if not code and supplemented_code:
                    code = supplemented_code
                    if supplemented_code_source is not None:
                        field_sources["pharmacological_code"] = supplemented_code_source
                if not name and supplemented_name:
                    name = supplemented_name
                    if supplemented_name_source is not None:
                        field_sources["pharmacological_name"] = supplemented_name_source
                if code and name:
                    break

        code, name, filled_code_source, filled_name_source = _fill_from_master(code, name, master_lookup)
        if code_source is not None and "pharmacological_code" not in field_sources:
            field_sources["pharmacological_code"] = code_source
        if name_source is not None and "pharmacological_name" not in field_sources:
            field_sources["pharmacological_name"] = name_source
        if filled_code_source is not None and "pharmacological_code" not in field_sources:
            field_sources["pharmacological_code"] = filled_code_source
        if filled_name_source is not None and "pharmacological_name" not in field_sources:
            field_sources["pharmacological_name"] = filled_name_source

        completed.append(
            replace(
                consolidated,
                record=replace(record, pharmacological_code=code, pharmacological_name=name),
                field_sources=field_sources,
            )
        )

    return completed


def apply_pharmacological_fill_rules(
    records: list[StandardDrugRecord],
    fill_config: PharmacologicalFillConfig,
    master_path: Path | None,
) -> list[StandardDrugRecord]:
    consolidated = [_consolidated_record_from_record(record, order) for order, record in enumerate(records)]
    return [
        item.record
        for item in _apply_pharmacological_fill_rules_with_provenance(
            consolidated,
            fill_config,
            master_path,
        )
    ]


def _record_to_view_row(record: StandardDrugRecord) -> list[str]:
    pharmacological_code = record.pharmacological_code or ""
    return [
        record.tensu_code or "",
        record.yj_code or "",
        pharmacological_code,
        pharmacological_code,
        record.pharmacological_name or "",
        record.display_name or "",
        record.generic_name or "",
        record.usage_purchase_flag or "",
    ]


def build_worksheet_rows(records: list[StandardDrugRecord]) -> list[list[str]]:
    return [
        _record_to_view_row(record)
        for record in records
        if record.display_name and should_include_in_adoption_views(record.adoption_status)
    ]


def build_generic_name_rows(records: list[StandardDrugRecord]) -> list[list[str]]:
    ordered = sorted(
        (
            record
            for record in records
            if record.display_name and should_include_in_adoption_views(record.adoption_status)
        ),
        key=lambda record: _sort_key(record.generic_name, record.display_name, record.tensu_code),
    )
    return [_record_to_view_row(record) for record in ordered]


def build_product_name_rows(records: list[StandardDrugRecord]) -> list[list[str]]:
    ordered = sorted(
        (
            record
            for record in records
            if record.display_name and should_include_in_adoption_views(record.adoption_status)
        ),
        key=lambda record: _sort_key(record.display_name, record.generic_name, record.tensu_code),
    )
    return [_record_to_view_row(record) for record in ordered]


def build_pharmacological_rows(records: list[StandardDrugRecord]) -> list[list[str]]:
    ordered = sorted(
        (
            record
            for record in records
            if record.display_name and should_include_in_adoption_views(record.adoption_status)
        ),
        key=lambda record: _sort_key(
            record.pharmacological_name,
            record.display_name,
            record.generic_name,
            record.tensu_code,
        ),
    )
    return [_record_to_view_row(record) for record in ordered]


def build_pharmacological_code_rows(records: list[StandardDrugRecord]) -> list[list[str]]:
    seen: set[tuple[str, str]] = set()
    rows: list[list[str]] = []
    unique_pairs = sorted(
        {
            (record.pharmacological_code or "", record.pharmacological_name or "")
            for record in records
            if should_include_in_adoption_views(record.adoption_status)
            and (record.pharmacological_code or record.pharmacological_name)
        },
        key=lambda item: _sort_key(item[0], item[1]),
    )

    for code, name in unique_pairs:
        if (code, name) in seen:
            continue
        seen.add((code, name))
        rows.append(["", "", code, "", name])
    return rows


def _is_matching_hierarchy_code(master_code: str, used_code: str) -> bool:
    master_code = _normalize_code(master_code)
    used_code = _normalize_code(used_code)
    if not master_code or not used_code:
        return False
    significant_prefix = master_code.rstrip("0") or master_code
    return used_code.startswith(significant_prefix)


def _hierarchy_prefix(code: str) -> str:
    normalized = _normalize_code(code)
    if normalized.endswith("00"):
        return normalized[:2]
    if normalized.endswith("0"):
        return normalized[:3]
    return normalized


def _is_descendant_of(code: str, ancestor_code: str) -> bool:
    code = _normalize_code(code)
    ancestor_code = _normalize_code(ancestor_code)
    if not code or not ancestor_code or code == ancestor_code:
        return False
    return code.startswith(_hierarchy_prefix(ancestor_code))


def build_pharmacological_code_rows_from_master(
    records: list[StandardDrugRecord],
    master_path: Path,
    hierarchy_config: PharmacologicalHierarchyConfig | None = None,
) -> list[list[str]]:
    if hierarchy_config is None:
        hierarchy_config = load_config().pharmacological_hierarchy

    used_codes = {
        _normalize_code(record.pharmacological_code)
        for record in records
        if should_include_in_adoption_views(record.adoption_status)
        and _normalize_code(record.pharmacological_code)
    }
    if not used_codes:
        return []

    encoding = detect_text_encoding(master_path)
    with master_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        master_rows = [row[:5] for row in reader if len(row) >= 5 and _normalize_code(row[2])]

    selected_codes: set[str] = set()
    if "prefix_ancestors" in hierarchy_config.expansion_modes:
        selected_codes.update(
            _normalize_code(row[2])
            for row in master_rows
            if any(_is_matching_hierarchy_code(_normalize_code(row[2]), used_code) for used_code in used_codes)
        )
    if "hundred_group_descendants" in hierarchy_config.expansion_modes:
        hundred_groups = {code for code in selected_codes if code.endswith("00")}
        for row in master_rows:
            code = _normalize_code(row[2])
            if any(_is_descendant_of(code, group_code) for group_code in hundred_groups):
                selected_codes.add(code)
    selected_codes.update(
        _normalize_code(code)
        for code in hierarchy_config.legacy_explicit_include_codes
        if _normalize_code(code)
    )

    return [row for row in master_rows if _normalize_code(row[2]) in selected_codes]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _build_legacy_view_order_sequences(
    order_config: LegacyViewOrderConfig,
) -> dict[str, list[tuple[str, ...]]]:
    if not order_config.enabled:
        return {}

    sequences: dict[str, list[tuple[str, ...]]] = {}
    for view_name, source_path in order_config.source_files.items():
        if not source_path.exists():
            continue
        encoding = detect_text_encoding(source_path)
        with source_path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            sequences[view_name] = [tuple(row) for row in reader]
    return sequences


def _apply_legacy_view_order(
    view_name: str,
    rows: list[list[str]],
    reference_rows: list[tuple[str, ...]] | None,
) -> list[list[str]]:
    if not reference_rows:
        return rows

    exact_buckets: dict[tuple[str, ...], deque[list[str]]] = {}
    key_buckets: dict[str, deque[list[str]]] = {}
    for row in rows:
        exact_buckets.setdefault(tuple(row), deque()).append(row)
        key_buckets.setdefault(_row_key_for_view(view_name, row), deque()).append(row)

    ordered: list[list[str]] = []
    consumed_ids: set[int] = set()

    def take_from(bucket: deque[list[str]] | None) -> list[str] | None:
        if bucket is None:
            return None
        while bucket:
            candidate = bucket.popleft()
            marker = id(candidate)
            if marker in consumed_ids:
                continue
            consumed_ids.add(marker)
            return candidate
        return None

    for reference_row in reference_rows:
        matched = take_from(exact_buckets.get(reference_row))
        if matched is None:
            matched = take_from(key_buckets.get(_row_key_for_view(view_name, reference_row)))
        if matched is not None:
            ordered.append(matched)

    for row in rows:
        if id(row) not in consumed_ids:
            ordered.append(row)
    return ordered


def _contribution_list_for_record(consolidated: ConsolidatedRecord) -> list[dict[str, object]]:
    return [
        {"field": field_name, **source.to_dict()}
        for field_name, source in sorted(consolidated.field_sources.items())
    ]


def _build_view_contributions(consolidated: list[ConsolidatedRecord]) -> dict[str, dict[str, list[dict[str, object]]]]:
    contributions_by_view = {view_name: {} for view_name in ("worksheet", "generic", "product", "pharmacological")}
    for item in consolidated:
        record = item.record
        if not record.display_name or not should_include_in_adoption_views(record.adoption_status):
            continue
        row = _record_to_view_row(record)
        key = row[0].strip() or row[1].strip() or f"{row[5].strip()}|{row[6].strip()}"
        payload = _contribution_list_for_record(item)
        for view_name in contributions_by_view:
            contributions_by_view[view_name][key] = payload
    return contributions_by_view


def _build_pharmacological_code_contributions(
    master_path: Path | None,
    rows: list[list[str]],
) -> dict[str, list[dict[str, object]]]:
    if master_path is None or not master_path.exists():
        return {}
    encoding = detect_text_encoding(master_path)
    contributions: dict[str, list[dict[str, object]]] = {}
    with master_path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row_number, row in enumerate(reader, start=2):
            if len(row) < 5:
                continue
            code = _normalize_code(row[2])
            if not code:
                continue
            contributions[code] = [
                {
                    "field": "pharmacological_code_row",
                    **FieldSource(
                        source_schema="pharmacological_code_master",
                        source_file=master_path,
                        source_row_number=row_number,
                        source_field="row",
                        value=code,
                    ).to_dict(),
                }
            ]
    return {
        _normalize_code(row[2]): contributions.get(_normalize_code(row[2]), [])
        for row in rows
        if len(row) > 2 and _normalize_code(row[2])
    }


def generate_views(
    target: Path,
    output_dir: Path,
    source_priority: dict[str, int] | None = None,
    pharmacological_code_master: Path | None = None,
    pharmacological_hierarchy: PharmacologicalHierarchyConfig | None = None,
    pharmacological_fill: PharmacologicalFillConfig | None = None,
    legacy_view_scope: LegacyViewScopeConfig | None = None,
    legacy_view_adjustments: LegacyViewAdjustmentsConfig | None = None,
    legacy_view_overrides: LegacyViewOverrideConfig | None = None,
    legacy_view_order: LegacyViewOrderConfig | None = None,
) -> dict[str, Path]:
    return generate_views_with_context(
        target,
        output_dir,
        source_priority=source_priority,
        pharmacological_code_master=pharmacological_code_master,
        pharmacological_hierarchy=pharmacological_hierarchy,
        pharmacological_fill=pharmacological_fill,
        legacy_view_scope=legacy_view_scope,
        legacy_view_adjustments=legacy_view_adjustments,
        legacy_view_overrides=legacy_view_overrides,
        legacy_view_order=legacy_view_order,
    ).outputs


def generate_views_with_context(
    target: Path,
    output_dir: Path,
    source_priority: dict[str, int] | None = None,
    pharmacological_code_master: Path | None = None,
    pharmacological_hierarchy: PharmacologicalHierarchyConfig | None = None,
    pharmacological_fill: PharmacologicalFillConfig | None = None,
    legacy_view_scope: LegacyViewScopeConfig | None = None,
    legacy_view_adjustments: LegacyViewAdjustmentsConfig | None = None,
    legacy_view_overrides: LegacyViewOverrideConfig | None = None,
    legacy_view_order: LegacyViewOrderConfig | None = None,
) -> GeneratedViewsResult:
    config = None
    if (
        source_priority is None
        or pharmacological_hierarchy is None
        or pharmacological_fill is None
        or legacy_view_scope is None
        or legacy_view_adjustments is None
        or legacy_view_overrides is None
        or legacy_view_order is None
    ):
        config = load_config()
    if source_priority is None:
        source_priority = config.source_priority
    if pharmacological_hierarchy is None:
        pharmacological_hierarchy = config.pharmacological_hierarchy
    if pharmacological_fill is None:
        pharmacological_fill = config.pharmacological_fill
    if legacy_view_scope is None:
        legacy_view_scope = config.legacy_view_scope
    if legacy_view_adjustments is None:
        legacy_view_adjustments = config.legacy_view_adjustments
    if legacy_view_overrides is None:
        legacy_view_overrides = config.legacy_view_overrides
    if legacy_view_order is None:
        legacy_view_order = config.legacy_view_order

    normalized_batches = normalize_target(target)
    all_records: list[StandardDrugRecord] = []
    for _, records, _ in normalized_batches:
        all_records.extend(records)

    consolidated = consolidate_records_with_provenance(all_records, source_priority)
    consolidated = _apply_pharmacological_fill_rules_with_provenance(
        consolidated,
        pharmacological_fill,
        pharmacological_code_master,
    )
    consolidated = _apply_legacy_view_overrides_with_provenance(
        consolidated,
        legacy_view_overrides,
    )
    consolidated = _apply_legacy_view_adjustments_with_provenance(
        consolidated,
        legacy_view_adjustments,
        source_priority,
        config.config_path if config is not None else None,
    )
    consolidated = _apply_legacy_duplicate_adjustments(
        consolidated,
        legacy_view_adjustments,
    )
    consolidated_records = [item.record for item in consolidated]
    scoped_records = apply_legacy_view_scope(consolidated_records, legacy_view_scope)

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "worksheet": output_dir / "■作業シート-表1.csv",
        "generic": output_dir / "一般名順-表1.csv",
        "product": output_dir / "製品名順-表1.csv",
        "pharmacological": output_dir / "薬効順-表1.csv",
        "pharmacological_code": output_dir / "薬効コード-表1.csv",
    }

    legacy_view_order_sequences = _build_legacy_view_order_sequences(legacy_view_order)
    worksheet_rows = _apply_legacy_view_order(
        "worksheet",
        build_worksheet_rows(scoped_records),
        legacy_view_order_sequences.get("worksheet"),
    )
    generic_rows = _apply_legacy_view_order(
        "generic",
        build_generic_name_rows(scoped_records),
        legacy_view_order_sequences.get("generic"),
    )
    product_rows = _apply_legacy_view_order(
        "product",
        build_product_name_rows(scoped_records),
        legacy_view_order_sequences.get("product"),
    )
    pharmacological_rows = _apply_legacy_view_order(
        "pharmacological",
        build_pharmacological_rows(scoped_records),
        legacy_view_order_sequences.get("pharmacological"),
    )

    _write_csv(outputs["worksheet"], WORKSHEET_HEADER, worksheet_rows)
    _write_csv(outputs["generic"], SORTED_VIEW_HEADER, generic_rows)
    _write_csv(outputs["product"], SORTED_VIEW_HEADER, product_rows)
    _write_csv(outputs["pharmacological"], SORTED_VIEW_HEADER, pharmacological_rows)
    pharmacological_code_rows = (
        build_pharmacological_code_rows_from_master(
            consolidated_records,
            pharmacological_code_master,
            hierarchy_config=pharmacological_hierarchy,
        )
        if pharmacological_code_master is not None
        else build_pharmacological_code_rows(consolidated_records)
    )
    pharmacological_code_rows = _apply_legacy_view_order(
        "pharmacological_code",
        pharmacological_code_rows,
        legacy_view_order_sequences.get("pharmacological_code"),
    )
    _write_csv(outputs["pharmacological_code"], PHARMACOLOGICAL_CODE_HEADER, pharmacological_code_rows)

    contributions_by_view = _build_view_contributions(consolidated)
    contributions_by_view["pharmacological_code"] = _build_pharmacological_code_contributions(
        pharmacological_code_master,
        pharmacological_code_rows,
    )
    return GeneratedViewsResult(outputs=outputs, contributions_by_view=contributions_by_view)