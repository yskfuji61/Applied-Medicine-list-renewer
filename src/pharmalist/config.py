from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def default_config_path() -> Path:
    configured = os.environ.get("PHARMALIST_CONFIG")
    return Path(configured) if configured else Path("config/defaults.json")


@dataclass(frozen=True)
class PharmacologicalFillConfig:
    supplement_sources: tuple[Path, ...]
    match_fields: tuple[str, ...]


@dataclass(frozen=True)
class PharmacologicalHierarchyConfig:
    expansion_modes: tuple[str, ...]
    legacy_explicit_include_codes: tuple[str, ...]


@dataclass(frozen=True)
class LegacyViewScopeConfig:
    enabled: bool
    reference_sources: tuple[Path, ...]
    match_fields: tuple[str, ...]
    include_non_adopted_matches: bool


@dataclass(frozen=True)
class LegacyMatchRule:
    match: dict[str, str]


@dataclass(frozen=True)
class LegacyAliasRule:
    match: dict[str, str]
    override: dict[str, str]


@dataclass(frozen=True)
class LegacyViewAdjustmentsConfig:
    explicit_exclusions: tuple[LegacyMatchRule, ...]
    aliases: tuple[LegacyAliasRule, ...]
    explicit_duplicates: tuple[LegacyMatchRule, ...]


@dataclass(frozen=True)
class LegacyViewOverrideConfig:
    enabled: bool
    reference_sources: tuple[Path, ...]
    match_fields: tuple[str, ...]
    override_fields: tuple[str, ...]


@dataclass(frozen=True)
class LegacyViewOrderConfig:
    enabled: bool
    source_files: dict[str, Path]


@dataclass(frozen=True)
class AppConfig:
    source_priority: dict[str, int]
    pharmacological_code_master: Path | None
    pharmacological_hierarchy: PharmacologicalHierarchyConfig
    pharmacological_fill: PharmacologicalFillConfig
    legacy_view_scope: LegacyViewScopeConfig
    legacy_view_adjustments: LegacyViewAdjustmentsConfig
    legacy_view_overrides: LegacyViewOverrideConfig
    legacy_view_order: LegacyViewOrderConfig
    config_path: Path


def _resolve_optional_path(base_dir: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def load_config(config_path: Path | None = None) -> AppConfig:
    path = (config_path or default_config_path()).expanduser().resolve()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    source_priority = {
        str(key): int(value)
        for key, value in payload.get("source_priority", {}).items()
    }
    masters = payload.get("masters", {})
    hierarchy = payload.get("pharmacological_hierarchy", {})
    fill = payload.get("pharmacological_fill", {})
    scope = payload.get("legacy_view_scope", {})
    adjustments = payload.get("legacy_view_adjustments", {})
    overrides = payload.get("legacy_view_overrides", {})
    order = payload.get("legacy_view_order", {})
    pharmacological_code_master = _resolve_optional_path(
        path.parent.parent,
        masters.get("pharmacological_code"),
    )
    supplement_sources = tuple(
        resolved
        for raw_path in fill.get("supplement_sources", [])
        if (resolved := _resolve_optional_path(path.parent.parent, raw_path)) is not None
    )
    scope_sources = tuple(
        resolved
        for raw_path in scope.get("reference_sources", [])
        if (resolved := _resolve_optional_path(path.parent.parent, raw_path)) is not None
    )
    override_sources = tuple(
        resolved
        for raw_path in overrides.get("reference_sources", [])
        if (resolved := _resolve_optional_path(path.parent.parent, raw_path)) is not None
    )

    return AppConfig(
        source_priority=source_priority,
        pharmacological_code_master=pharmacological_code_master,
        pharmacological_hierarchy=PharmacologicalHierarchyConfig(
            expansion_modes=tuple(str(mode) for mode in hierarchy.get("expansion_modes", [])),
            legacy_explicit_include_codes=tuple(
                str(code) for code in hierarchy.get("legacy_explicit_include_codes", [])
            ),
        ),
        pharmacological_fill=PharmacologicalFillConfig(
            supplement_sources=supplement_sources,
            match_fields=tuple(str(field) for field in fill.get("match_fields", [])),
        ),
        legacy_view_scope=LegacyViewScopeConfig(
            enabled=bool(scope.get("enabled", False)),
            reference_sources=scope_sources,
            match_fields=tuple(str(field) for field in scope.get("match_fields", [])),
            include_non_adopted_matches=bool(scope.get("include_non_adopted_matches", False)),
        ),
        legacy_view_adjustments=LegacyViewAdjustmentsConfig(
            explicit_exclusions=tuple(
                LegacyMatchRule(
                    match={
                        str(field): str(value)
                        for field, value in entry.get("match", {}).items()
                    }
                )
                for entry in adjustments.get("explicit_exclusions", [])
            ),
            aliases=tuple(
                LegacyAliasRule(
                    match={
                        str(field): str(value)
                        for field, value in entry.get("match", {}).items()
                    },
                    override={
                        str(field): str(value)
                        for field, value in entry.get("override", {}).items()
                    },
                )
                for entry in adjustments.get("aliases", [])
            ),
            explicit_duplicates=tuple(
                LegacyMatchRule(
                    match={
                        str(field): str(value)
                        for field, value in entry.get("match", {}).items()
                    }
                )
                for entry in adjustments.get("explicit_duplicates", [])
            ),
        ),
        legacy_view_overrides=LegacyViewOverrideConfig(
            enabled=bool(overrides.get("enabled", False)),
            reference_sources=override_sources,
            match_fields=tuple(str(field) for field in overrides.get("match_fields", [])),
            override_fields=tuple(str(field) for field in overrides.get("override_fields", [])),
        ),
        legacy_view_order=LegacyViewOrderConfig(
            enabled=bool(order.get("enabled", False)),
            source_files={
                str(view_name): resolved
                for view_name, raw_path in order.get("source_files", {}).items()
                if (resolved := _resolve_optional_path(path.parent.parent, raw_path)) is not None
            },
        ),
        config_path=path,
    )