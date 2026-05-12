from __future__ import annotations

import csv
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from pharmalist.encodings import detect_text_encoding


VIEW_FILES = {
    "worksheet": "■作業シート-表1.csv",
    "generic": "一般名順-表1.csv",
    "product": "製品名順-表1.csv",
    "pharmacological": "薬効順-表1.csv",
    "pharmacological_code": "薬効コード-表1.csv",
}


@dataclass(frozen=True)
class KeyedChange:
    key: str
    reasons: tuple[str, ...]
    expected_row: tuple[str, ...] | None
    actual_row: tuple[str, ...] | None
    actual_contributions: list[dict[str, object]]
    classification: str | None = None
    related_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ViewDiff:
    view_name: str
    expected_path: Path
    actual_path: Path
    header_matches: bool
    expected_row_count: int
    actual_row_count: int
    missing_row_count: int
    extra_row_count: int
    order_matches: bool
    first_missing_row: tuple[str, ...] | None
    first_extra_row: tuple[str, ...] | None
    first_order_mismatch_index: int | None
    expected_row_at_mismatch: tuple[str, ...] | None
    actual_row_at_mismatch: tuple[str, ...] | None
    reason_counts: dict[str, int]
    classification_counts: dict[str, int]
    keyed_changes: list[KeyedChange]

    @property
    def matches(self) -> bool:
        return (
            self.header_matches
            and self.expected_row_count == self.actual_row_count
            and self.missing_row_count == 0
            and self.extra_row_count == 0
            and self.order_matches
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["matches"] = self.matches
        payload["expected_path"] = str(self.expected_path)
        payload["actual_path"] = str(self.actual_path)
        payload["keyed_changes"] = [change.to_dict() for change in self.keyed_changes]
        return payload


@dataclass(frozen=True)
class DiffReport:
    expected_dir: Path
    actual_dir: Path
    views: list[ViewDiff]

    @property
    def matches(self) -> bool:
        return all(view.matches for view in self.views)

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_dir": str(self.expected_dir),
            "actual_dir": str(self.actual_dir),
            "matches": self.matches,
            "views": [view.to_dict() for view in self.views],
        }


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[tuple[str, ...]]]:
    encoding = detect_text_encoding(path)
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        header = tuple(next(reader, []))
        rows = [tuple(row) for row in reader]
    return header, rows


def _row_key(view_name: str, row: tuple[str, ...]) -> str:
    if view_name == "pharmacological_code":
        return (row[2] if len(row) > 2 else "").strip() or "<blank>"
    tensu_code = row[0].strip() if len(row) > 0 else ""
    yj_code = row[1].strip() if len(row) > 1 else ""
    display_name = row[5].strip() if len(row) > 5 else ""
    generic_name = row[6].strip() if len(row) > 6 else ""
    return tensu_code or yj_code or f"{display_name}|{generic_name}"


def _reason_list_for_rows(
    view_name: str,
    expected_row: tuple[str, ...] | None,
    actual_row: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if expected_row is None:
        return ("extra_in_actual",)
    if actual_row is None:
        return ("missing_in_actual",)

    reasons: list[str] = []
    if view_name == "pharmacological_code":
        expected_name = expected_row[4].strip() if len(expected_row) > 4 else ""
        actual_name = actual_row[4].strip() if len(actual_row) > 4 else ""
        if expected_name != actual_name:
            reasons.append("pharmacological_name_changed")
        if not actual_name and expected_name:
            reasons.append("pharmacological_name_missing")
        if expected_row != actual_row and not reasons:
            reasons.append("hierarchy_row_changed")
        return tuple(dict.fromkeys(reasons or ["row_changed"]))

    compared_fields = {
        "yj_code_changed": (1, False),
        "pharmacological_code_changed": (2, True),
        "pharmacological_name_changed": (4, True),
        "display_name_changed": (5, False),
        "generic_name_changed": (6, False),
        "usage_purchase_flag_changed": (7, False),
    }
    for reason, (index, is_pharmacological) in compared_fields.items():
        expected_value = expected_row[index].strip() if len(expected_row) > index else ""
        actual_value = actual_row[index].strip() if len(actual_row) > index else ""
        if expected_value != actual_value:
            reasons.append(reason)
            if is_pharmacological and expected_value and not actual_value:
                reasons.append("pharmacological_missing")
    if expected_row != actual_row and not reasons:
        reasons.append("row_changed")
    return tuple(dict.fromkeys(reasons))


def _build_missing_lookup(
    view_name: str,
    missing_rows: list[tuple[str, ...]],
) -> dict[str, dict[str, list[str]]]:
    lookup = {
        "yj_code": {},
        "display_name": {},
        "generic_name": {},
    }
    for row in missing_rows:
        key = _row_key(view_name, row)
        if len(row) > 1 and row[1].strip():
            lookup["yj_code"].setdefault(row[1].strip(), []).append(key)
        if len(row) > 5 and row[5].strip():
            lookup["display_name"].setdefault(row[5].strip(), []).append(key)
        if len(row) > 6 and row[6].strip():
            lookup["generic_name"].setdefault(row[6].strip(), []).append(key)
    return lookup


def _classify_extra_change(
    view_name: str,
    actual_row: tuple[str, ...],
    missing_lookup: dict[str, dict[str, list[str]]],
) -> tuple[str, tuple[str, ...]]:
    if view_name == "pharmacological_code":
        return "legacy_scope_exclusion_candidate", ()

    yj_code = actual_row[1].strip() if len(actual_row) > 1 else ""
    display_name = actual_row[5].strip() if len(actual_row) > 5 else ""
    generic_name = actual_row[6].strip() if len(actual_row) > 6 else ""

    if yj_code and yj_code in missing_lookup["yj_code"]:
        return "name_variant_same_yj", tuple(missing_lookup["yj_code"][yj_code])
    if display_name and display_name in missing_lookup["display_name"]:
        return "name_variant_same_display_name", tuple(missing_lookup["display_name"][display_name])
    if generic_name and generic_name in missing_lookup["generic_name"]:
        return "name_variant_same_generic_name", tuple(missing_lookup["generic_name"][generic_name])
    return "legacy_scope_exclusion_candidate", ()


def _build_keyed_changes(
    view_name: str,
    expected_rows: list[tuple[str, ...]],
    actual_rows: list[tuple[str, ...]],
    actual_contributions_by_key: dict[str, list[dict[str, object]]] | None = None,
) -> tuple[list[KeyedChange], dict[str, int], dict[str, int]]:
    expected_by_key: dict[str, list[tuple[str, ...]]] = {}
    actual_by_key: dict[str, list[tuple[str, ...]]] = {}
    for row in expected_rows:
        expected_by_key.setdefault(_row_key(view_name, row), []).append(row)
    for row in actual_rows:
        actual_by_key.setdefault(_row_key(view_name, row), []).append(row)

    keyed_changes: list[KeyedChange] = []
    reason_counts: Counter[str] = Counter()
    unmatched_missing_rows: list[tuple[str, ...]] = []
    for key in sorted(set(expected_by_key) | set(actual_by_key)):
        remaining_expected = list(expected_by_key.get(key, []))
        remaining_actual = list(actual_by_key.get(key, []))
        for row in list(remaining_expected):
            if row in remaining_actual:
                remaining_expected.remove(row)
                remaining_actual.remove(row)

        paired_count = max(len(remaining_expected), len(remaining_actual))
        for index in range(paired_count):
            expected_row = remaining_expected[index] if index < len(remaining_expected) else None
            actual_row = remaining_actual[index] if index < len(remaining_actual) else None
            reasons = _reason_list_for_rows(view_name, expected_row, actual_row)
            change = KeyedChange(
                key=key,
                reasons=reasons,
                expected_row=expected_row,
                actual_row=actual_row,
                actual_contributions=(actual_contributions_by_key or {}).get(key, []),
            )
            keyed_changes.append(change)
            reason_counts.update(reasons)
            if reasons == ("missing_in_actual",) and expected_row is not None:
                unmatched_missing_rows.append(expected_row)

    classification_counts: Counter[str] = Counter()
    if unmatched_missing_rows:
        missing_lookup = _build_missing_lookup(view_name, unmatched_missing_rows)
        classified_changes: list[KeyedChange] = []
        for change in keyed_changes:
            if change.reasons == ("extra_in_actual",) and change.actual_row is not None:
                classification, related_keys = _classify_extra_change(
                    view_name,
                    change.actual_row,
                    missing_lookup,
                )
                classified_change = KeyedChange(
                    key=change.key,
                    reasons=change.reasons,
                    expected_row=change.expected_row,
                    actual_row=change.actual_row,
                    actual_contributions=change.actual_contributions,
                    classification=classification,
                    related_keys=related_keys,
                )
                classification_counts.update([classification])
                classified_changes.append(classified_change)
            else:
                classified_changes.append(change)
        keyed_changes = classified_changes

    return keyed_changes, dict(sorted(reason_counts.items())), dict(sorted(classification_counts.items()))


def compare_view_files(
    view_name: str,
    expected_path: Path,
    actual_path: Path,
    actual_contributions_by_key: dict[str, list[dict[str, object]]] | None = None,
) -> ViewDiff:
    expected_header, expected_rows = _read_csv(expected_path)
    actual_header, actual_rows = _read_csv(actual_path)

    missing = Counter(expected_rows) - Counter(actual_rows)
    extra = Counter(actual_rows) - Counter(expected_rows)

    first_order_mismatch_index = None
    expected_row_at_mismatch = None
    actual_row_at_mismatch = None
    if expected_rows != actual_rows:
        max_len = min(len(expected_rows), len(actual_rows))
        for index in range(max_len):
            if expected_rows[index] != actual_rows[index]:
                first_order_mismatch_index = index
                expected_row_at_mismatch = expected_rows[index]
                actual_row_at_mismatch = actual_rows[index]
                break
        else:
            first_order_mismatch_index = max_len
            expected_row_at_mismatch = expected_rows[max_len] if len(expected_rows) > max_len else None
            actual_row_at_mismatch = actual_rows[max_len] if len(actual_rows) > max_len else None

    keyed_changes, reason_counts, classification_counts = _build_keyed_changes(
        view_name,
        expected_rows,
        actual_rows,
        actual_contributions_by_key=actual_contributions_by_key,
    )

    return ViewDiff(
        view_name=view_name,
        expected_path=expected_path,
        actual_path=actual_path,
        header_matches=expected_header == actual_header,
        expected_row_count=len(expected_rows),
        actual_row_count=len(actual_rows),
        missing_row_count=sum(missing.values()),
        extra_row_count=sum(extra.values()),
        order_matches=expected_rows == actual_rows,
        first_missing_row=next(iter(missing.elements()), None),
        first_extra_row=next(iter(extra.elements()), None),
        first_order_mismatch_index=first_order_mismatch_index,
        expected_row_at_mismatch=expected_row_at_mismatch,
        actual_row_at_mismatch=actual_row_at_mismatch,
        reason_counts=reason_counts,
        classification_counts=classification_counts,
        keyed_changes=keyed_changes,
    )


def compare_view_directories(
    expected_dir: Path,
    actual_dir: Path,
    actual_contributions_by_view: dict[str, dict[str, list[dict[str, object]]]] | None = None,
) -> DiffReport:
    views = [
        compare_view_files(
            view_name,
            expected_dir / filename,
            actual_dir / filename,
            actual_contributions_by_key=(actual_contributions_by_view or {}).get(view_name),
        )
        for view_name, filename in VIEW_FILES.items()
    ]
    return DiffReport(expected_dir=expected_dir, actual_dir=actual_dir, views=views)