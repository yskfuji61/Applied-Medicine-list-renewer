from __future__ import annotations

import unittest
import json
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from pharmalist.cli import render_compare_views, render_publish_report
from pharmalist.config import (
    LegacyAliasRule,
    LegacyMatchRule,
    LegacyViewAdjustmentsConfig,
    LegacyViewOrderConfig,
    LegacyViewOverrideConfig,
    LegacyViewScopeConfig,
    PharmacologicalFillConfig,
    load_config,
)
from pharmalist.diff import compare_view_directories
from pharmalist.encodings import detect_text_encoding
from pharmalist.mapping import identify_source_schema, resolve_column_mapping
from pharmalist.normalize import normalize_csv
from pharmalist.output import (
    SORTED_VIEW_HEADER,
    WORKSHEET_HEADER,
    apply_pharmacological_fill_rules,
    build_generic_name_rows,
    build_pharmacological_code_rows_from_master,
    build_pharmacological_code_rows,
    build_product_name_rows,
    generate_views,
)
from pharmalist.profile import build_input_profile, discover_csv_files
from pharmalist.rules import determine_adoption_status, should_include_in_adoption_views
from pharmalist.models import StandardDrugRecord


def write_local_profile_config(config_path: Path, reference_dir: Path) -> Path:
    defaults_path = Path(__file__).resolve().parents[1] / "config" / "defaults.json"
    payload = json.loads(defaults_path.read_text(encoding="utf-8"))
    worksheet_path = reference_dir / "■作業シート-表1.csv"
    source_files = {
        "worksheet": reference_dir / "■作業シート-表1.csv",
        "generic": reference_dir / "一般名順-表1.csv",
        "product": reference_dir / "製品名順-表1.csv",
        "pharmacological": reference_dir / "薬効順-表1.csv",
        "pharmacological_code": reference_dir / "薬効コード-表1.csv",
    }

    payload["masters"]["pharmacological_code"] = str(source_files["pharmacological_code"])
    payload["pharmacological_fill"]["supplement_sources"] = [str(worksheet_path)]
    payload["legacy_view_scope"]["reference_sources"] = [str(worksheet_path)]
    payload["legacy_view_overrides"]["reference_sources"] = [str(worksheet_path)]
    payload["legacy_view_order"]["source_files"] = {
        view_name: str(path) for view_name, path in source_files.items()
    }

    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return config_path


class ProfileTests(unittest.TestCase):
    def test_load_config_resolves_default_master_path(self) -> None:
        config = load_config()

        self.assertEqual(config.source_priority["reference_main"], 1)
        self.assertTrue(config.pharmacological_code_master is not None)
        self.assertIn("hundred_group_descendants", config.pharmacological_hierarchy.expansion_modes)
        self.assertEqual(config.pharmacological_fill.match_fields[0], "tensu_code")
        self.assertTrue(config.legacy_view_scope.enabled)
        self.assertEqual(len(config.legacy_view_adjustments.explicit_exclusions), 30)
        self.assertEqual(len(config.legacy_view_adjustments.aliases), 10)
        self.assertEqual(len(config.legacy_view_adjustments.explicit_duplicates), 2)
        self.assertTrue(config.legacy_view_overrides.enabled)
        self.assertTrue(config.legacy_view_order.enabled)
        self.assertEqual(len(config.legacy_view_order.source_files), 5)
        self.assertTrue(config.legacy_view_scope.include_non_adopted_matches)
        self.assertEqual(
            config.legacy_view_overrides.override_fields,
            ("yj_code", "pharmacological_code", "pharmacological_name", "display_name", "generic_name", "usage_purchase_flag"),
        )
        self.assertTrue(config.config_path.name.endswith("defaults.json"))

    def test_apply_pharmacological_fill_rules_uses_supplement_source(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            supplement = Path(tmp_dir) / "■作業シート-表1.csv"
            supplement.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )
            record = StandardDrugRecord(
                source_file=Path("source.csv"),
                source_schema="reference_gaiyou",
                source_row_number=2,
                tensu_code="1",
                yj_code="Y1",
                pharmacological_code=None,
                pharmacological_name=None,
                display_name="製品A",
                generic_name="一般名A",
                unit=None,
                adoption_flag="1 採用薬",
                adoption_status="adopted",
                usage_purchase_flag=None,
                extended_name=None,
            )

            completed = apply_pharmacological_fill_rules(
                [record],
                PharmacologicalFillConfig(
                    supplement_sources=(supplement,),
                    match_fields=("tensu_code", "yj_code", "display_name"),
                ),
                master_path=None,
            )

            self.assertEqual(completed[0].pharmacological_code, "1000")
            self.assertEqual(completed[0].pharmacological_name, "薬効A")

    def test_detect_text_encoding_supports_cp932(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "sample.csv"
            csv_path.write_bytes("列1,列2\nあ,い\n".encode("cp932"))

            self.assertEqual(detect_text_encoding(csv_path), "cp932")

    def test_discover_csv_files_recurses_directories(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            nested = root / "nested"
            nested.mkdir()
            first = root / "a.csv"
            second = nested / "b.csv"
            first.write_text("a,b\n1,2\n", encoding="utf-8")
            second.write_text("c,d\n3,4\n", encoding="utf-8")

            self.assertEqual(discover_csv_files(root), [first, second])

    def test_build_input_profile_reports_row_counts(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "sample.csv"
            csv_path.write_text("col1,col2\n1,2\n3,4\n", encoding="utf-8")

            profile = build_input_profile(root)

            self.assertEqual(profile.file_count, 1)
            self.assertEqual(profile.total_rows, 2)
            self.assertEqual(profile.files[0].header, ["col1", "col2"])

    def test_resolve_column_mapping_for_old_worksheet(self) -> None:
        header = [
            "点数ｺｰﾄﾞ                                          ",
            "YJコード",
            "薬効コード",
            "薬効コード",
            "薬効",
            "表示用名称                                        ",
            "一般名称",
            "用事購入薬品",
        ]
        schema = identify_source_schema(Path("■作業シート-表1.csv"))

        mapping = resolve_column_mapping(header, schema)

        self.assertEqual(mapping.source_schema, "old_worksheet")
        self.assertEqual(mapping.resolved_fields["tensu_code"], 0)
        self.assertEqual(mapping.resolved_fields["pharmacological_code"], 2)
        self.assertEqual(mapping.resolved_fields["display_name"], 5)
        self.assertEqual(mapping.missing_fields, ())

    def test_normalize_csv_maps_rows_into_standard_schema(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "260508_musashino_pharm_list_gaiyou.csv"
            csv_path.write_bytes(
                (
                    "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,表示名称(拡張),拡張正式名称１,採用フラグ,一般名称,用時購入薬\n"
                    "123456,薬剤A,拡張名A,9876543210,錠,表示名A,正式名A,1,一般名A,0\n"
                ).encode("cp932")
            )

            records, missing_fields = normalize_csv(csv_path)

            self.assertEqual(missing_fields, ())
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].tensu_code, "123456")
            self.assertEqual(records[0].display_name, "薬剤A")
            self.assertEqual(records[0].generic_name, "一般名A")
            self.assertEqual(records[0].extended_name, "表示名A")
            self.assertEqual(records[0].adoption_status, "adopted")

    def test_normalize_csv_derives_pharmacological_code_from_label(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "260508_musashino_pharm_list.csv"
            csv_path.write_bytes(
                (
                    "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,セット区分,採用フラグ,薬効,拡張正式名称１\n"
                    "123456,薬剤A,,9876543210,錠,0 単品,1 採用薬,2190：その他の循環器官用薬,一般名A\n"
                ).encode("cp932")
            )

            records, missing_fields = normalize_csv(csv_path)

            self.assertEqual(missing_fields, ())
            self.assertEqual(records[0].pharmacological_code, "2190")
            self.assertEqual(records[0].pharmacological_name, "その他の循環器官用薬")

    def test_determine_adoption_status_maps_known_flags(self) -> None:
        self.assertEqual(determine_adoption_status("reference_main", "1 採用薬"), "adopted")
        self.assertEqual(determine_adoption_status("reference_chusya", "2 採用後中止薬"), "discontinued")
        self.assertEqual(determine_adoption_status("reference_gaiyou", "3 非採用薬（持参薬用）"), "excluded")
        self.assertEqual(determine_adoption_status("reference_gaiyou", "0 未入力（採用薬フラグ）"), "pending")
        self.assertEqual(determine_adoption_status("old_worksheet", None), "legacy")

    def test_adoption_views_exclude_non_adopted_reference_rows(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "260508_musashino_pharm_list_gaiyou.csv"
            csv_path.write_bytes(
                (
                    "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,表示名称(拡張),拡張正式名称１,採用フラグ,一般名称,用時購入薬\n"
                    "100001,非採：薬剤X,拡張名X,111,錠,表示名X,正式名X,3 非採用薬（持参薬用）,一般名X,0 未入力（用時購入薬・臨時購入薬）\n"
                    "100002,薬剤Y,拡張名Y,222,錠,表示名Y,正式名Y,1 採用薬,一般名Y,0 未入力（用時購入薬・臨時購入薬）\n"
                ).encode("cp932")
            )

            outputs = generate_views(
                csv_path,
                Path(tmp_dir) / "generated",
                legacy_view_scope=LegacyViewScopeConfig(
                    enabled=False,
                    reference_sources=(),
                    match_fields=(),
                    include_non_adopted_matches=False,
                ),
            )
            worksheet = outputs["worksheet"].read_text(encoding="utf-8")

            self.assertNotIn("非採：薬剤X", worksheet)
            self.assertIn("薬剤Y", worksheet)
            self.assertTrue(should_include_in_adoption_views("adopted"))
            self.assertFalse(should_include_in_adoption_views("excluded"))

    def test_view_rows_are_sorted_by_expected_keys(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "■作業シート-表1.csv"
            csv_path.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "2,Y2,2000,2000,薬効B,製品B,一般名B,\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )

            records, _ = normalize_csv(csv_path)

            generic_rows = build_generic_name_rows(records)
            product_rows = build_product_name_rows(records)
            pharmacological_code_rows = build_pharmacological_code_rows(records)

            self.assertEqual(generic_rows[0][5], "製品A")
            self.assertEqual(product_rows[0][5], "製品A")
            self.assertEqual(pharmacological_code_rows[0][2], "1000")

    def test_generate_views_writes_expected_files(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "■作業シート-表1.csv"
            out_dir = root / "generated"
            source.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )

            outputs = generate_views(source, out_dir)

            self.assertTrue(outputs["worksheet"].exists())
            self.assertTrue(outputs["generic"].exists())
            self.assertTrue(outputs["product"].exists())
            self.assertTrue(outputs["pharmacological"].exists())
            self.assertTrue(outputs["pharmacological_code"].exists())
            self.assertEqual(outputs["worksheet"].read_text(encoding="utf-8").splitlines()[0], ",".join(WORKSHEET_HEADER))
            self.assertEqual(outputs["generic"].read_text(encoding="utf-8").splitlines()[0], ",".join(SORTED_VIEW_HEADER))

    def test_generate_views_applies_legacy_scope(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "260508_musashino_pharm_list.csv"
            scope = root / "■作業シート-表1.csv"
            out_dir = root / "generated"
            source.write_text(
                "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,セット区分,採用フラグ,薬効,拡張正式名称１\n"
                "1,製品A,,Y1,錠,0 単品,1 採用薬,1000：薬効A,一般名A\n"
                "2,製品B,,Y2,錠,0 単品,1 採用薬,1000：薬効A,一般名B\n",
                encoding="utf-8",
            )
            scope.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )

            outputs = generate_views(
                source,
                out_dir,
                legacy_view_scope=load_config().legacy_view_scope.__class__(
                    enabled=True,
                    reference_sources=(scope,),
                    match_fields=("tensu_code", "yj_code"),
                    include_non_adopted_matches=True,
                ),
            )

            worksheet = outputs["worksheet"].read_text(encoding="utf-8")
            self.assertIn("製品A", worksheet)
            self.assertNotIn("製品B", worksheet)

    def test_generate_views_applies_legacy_explicit_exclusions(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "260508_musashino_pharm_list.csv"
            out_dir = root / "generated"
            source.write_text(
                "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,セット区分,採用フラグ,薬効,拡張正式名称１\n"
                "1,製品A,,Y1,錠,0 単品,1 採用薬,1000：薬効A,一般名A\n"
                "2,製品B,,Y2,錠,0 単品,1 採用薬,1000：薬効A,一般名B\n",
                encoding="utf-8",
            )

            outputs = generate_views(
                source,
                out_dir,
                legacy_view_scope=LegacyViewScopeConfig(enabled=False, reference_sources=(), match_fields=(), include_non_adopted_matches=False),
                legacy_view_adjustments=LegacyViewAdjustmentsConfig(
                    explicit_exclusions=(LegacyMatchRule(match={"tensu_code": "2"}),),
                    aliases=(),
                    explicit_duplicates=(),
                ),
            )

            worksheet = outputs["worksheet"].read_text(encoding="utf-8")
            self.assertIn("製品A", worksheet)
            self.assertNotIn("製品B", worksheet)

    def test_generate_views_applies_legacy_aliases_and_reconsolidates(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "260508_musashino_pharm_list.csv"
            out_dir = root / "generated"
            source.write_text(
                "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,セット区分,採用フラグ,薬効,拡張正式名称１\n"
                "9,新名称A,,Y1,錠,0 単品,1 採用薬,1000：薬効A,一般名A\n"
                "10,新名称B,,Y1,錠,0 単品,1 採用薬,1000：薬効A,一般名A\n",
                encoding="utf-8",
            )

            outputs = generate_views(
                source,
                out_dir,
                legacy_view_scope=LegacyViewScopeConfig(enabled=False, reference_sources=(), match_fields=(), include_non_adopted_matches=False),
                legacy_view_adjustments=LegacyViewAdjustmentsConfig(
                    explicit_exclusions=(),
                    aliases=(
                        LegacyAliasRule(
                            match={"tensu_code": "9"},
                            override={
                                "tensu_code": "1",
                                "yj_code": "Y1",
                                "pharmacological_code": "1000",
                                "pharmacological_name": "薬効A",
                                "display_name": "旧名称A",
                                "generic_name": "一般名A",
                                "usage_purchase_flag": "",
                            },
                        ),
                        LegacyAliasRule(
                            match={"tensu_code": "10"},
                            override={
                                "tensu_code": "1",
                                "yj_code": "Y1",
                                "pharmacological_code": "1000",
                                "pharmacological_name": "薬効A",
                                "display_name": "旧名称A",
                                "generic_name": "一般名A",
                                "usage_purchase_flag": "",
                            },
                        ),
                    ),
                    explicit_duplicates=(),
                ),
            )

            worksheet_lines = outputs["worksheet"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(worksheet_lines), 2)
            self.assertIn("1,Y1,1000,1000,薬効A,旧名称A,一般名A,", worksheet_lines[1])

    def test_generate_views_applies_legacy_view_overrides_from_old_worksheet(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "260508_musashino_pharm_list.csv"
            legacy = root / "■作業シート-表1.csv"
            out_dir = root / "generated"
            source.write_text(
                "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,セット区分,採用フラグ,薬効,拡張正式名称１\n"
                "1,新名称A,,Y1,錠,0 単品,1 採用薬,1000：薬効A,新一般名A\n",
                encoding="utf-8",
            )
            legacy.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1000,1000,薬効A,旧名称A,旧一般名A,2　用時購入（在庫なし）\n",
                encoding="utf-8",
            )

            outputs = generate_views(
                source,
                out_dir,
                legacy_view_scope=LegacyViewScopeConfig(enabled=False, reference_sources=(), match_fields=(), include_non_adopted_matches=False),
                legacy_view_adjustments=LegacyViewAdjustmentsConfig(explicit_exclusions=(), aliases=(), explicit_duplicates=()),
                legacy_view_overrides=LegacyViewOverrideConfig(
                    enabled=True,
                    reference_sources=(legacy,),
                    match_fields=("tensu_code", "yj_code"),
                    override_fields=("yj_code", "pharmacological_code", "pharmacological_name", "display_name", "generic_name", "usage_purchase_flag"),
                ),
            )

            worksheet_lines = outputs["worksheet"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(worksheet_lines), 2)
            self.assertIn("1,Y1,1000,1000,薬効A,旧名称A,旧一般名A,", worksheet_lines[1])
            self.assertIn("用時購入（在庫なし）", worksheet_lines[1])

    def test_generate_views_scope_can_force_include_old_matches(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "260508_musashino_pharm_list.csv"
            legacy = root / "■作業シート-表1.csv"
            out_dir = root / "generated"
            source.write_text(
                "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,セット区分,採用フラグ,薬効,拡張正式名称１\n"
                "1,製品A,,Y1,錠,0 単品,3 非採用薬（持参薬用）,1000：薬効A,一般名A\n",
                encoding="utf-8",
            )
            legacy.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )

            outputs = generate_views(
                source,
                out_dir,
                legacy_view_scope=LegacyViewScopeConfig(
                    enabled=True,
                    reference_sources=(legacy,),
                    match_fields=("tensu_code", "yj_code"),
                    include_non_adopted_matches=True,
                ),
                legacy_view_adjustments=LegacyViewAdjustmentsConfig(explicit_exclusions=(), aliases=(), explicit_duplicates=()),
                legacy_view_overrides=LegacyViewOverrideConfig(
                    enabled=True,
                    reference_sources=(legacy,),
                    match_fields=("tensu_code", "yj_code"),
                    override_fields=("yj_code", "pharmacological_code", "pharmacological_name", "display_name", "generic_name", "usage_purchase_flag"),
                ),
            )

            worksheet = outputs["worksheet"].read_text(encoding="utf-8")
            self.assertIn("製品A", worksheet)

    def test_generate_views_can_duplicate_legacy_rows(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "260508_musashino_pharm_list.csv"
            out_dir = root / "generated"
            source.write_text(
                "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,セット区分,採用フラグ,薬効,拡張正式名称１\n"
                "1,製品A,,Y1,錠,0 単品,1 採用薬,1000：薬効A,一般名A\n",
                encoding="utf-8",
            )

            outputs = generate_views(
                source,
                out_dir,
                legacy_view_scope=LegacyViewScopeConfig(enabled=False, reference_sources=(), match_fields=(), include_non_adopted_matches=False),
                legacy_view_adjustments=LegacyViewAdjustmentsConfig(
                    explicit_exclusions=(),
                    aliases=(),
                    explicit_duplicates=(LegacyMatchRule(match={"tensu_code": "1"}),),
                ),
            )

            worksheet_lines = outputs["worksheet"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(worksheet_lines), 3)
            self.assertEqual(worksheet_lines[1], worksheet_lines[2])

    def test_generate_views_applies_legacy_view_order(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "260508_musashino_pharm_list.csv"
            order_source = root / "■作業シート-表1.csv"
            out_dir = root / "generated"
            source.write_text(
                "点数ｺｰﾄﾞ,表示用名称,メモに使用：拡張正式名称４,YJコード,単位,セット区分,採用フラグ,薬効,拡張正式名称１\n"
                "1,製品A,,Y1,錠,0 単品,1 採用薬,1000：薬効A,一般名A\n"
                "2,製品B,,Y2,錠,0 単品,1 採用薬,1000：薬効A,一般名B\n",
                encoding="utf-8",
            )
            order_source.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "2,Y2,1000,1000,薬効A,製品B,一般名B,\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )

            outputs = generate_views(
                source,
                out_dir,
                legacy_view_scope=LegacyViewScopeConfig(enabled=False, reference_sources=(), match_fields=(), include_non_adopted_matches=False),
                legacy_view_adjustments=LegacyViewAdjustmentsConfig(explicit_exclusions=(), aliases=(), explicit_duplicates=()),
                legacy_view_overrides=LegacyViewOverrideConfig(enabled=False, reference_sources=(), match_fields=(), override_fields=()),
                legacy_view_order=LegacyViewOrderConfig(
                    enabled=True,
                    source_files={"worksheet": order_source},
                ),
            )

            worksheet_lines = outputs["worksheet"].read_text(encoding="utf-8").splitlines()
            self.assertIn("2,Y2,1000,1000,薬効A,製品B,一般名B,", worksheet_lines[1])
            self.assertIn("1,Y1,1000,1000,薬効A,製品A,一般名A,", worksheet_lines[2])

    def test_pharmacological_code_master_filters_to_used_hierarchy(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "■作業シート-表1.csv"
            master = root / "薬効コード-表1.csv"

            source.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,2123,2123,β－遮断剤,製品A,一般名A,\n",
                encoding="utf-8",
            )
            master.write_text(
                "大項目,中項目,コード,,名称\n"
                ",,2000,,循環器官用薬\n"
                ",,2100,,循環器官用薬詳細\n"
                ",,2120,,β遮断剤群\n"
                ",,2123,,β－遮断剤\n"
                ",,3999,,別分類\n",
                encoding="utf-8",
            )

            records, _ = normalize_csv(source)
            rows = build_pharmacological_code_rows_from_master(records, master)

            self.assertEqual([row[2] for row in rows], ["2000", "2100", "2120", "2123"])

    def test_pharmacological_code_master_expands_hundred_group_descendants(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "■作業シート-表1.csv"
            master = root / "薬効コード-表1.csv"

            source.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1124,1124,ベンゾジアゼピン系製剤,製品A,一般名A,\n",
                encoding="utf-8",
            )
            master.write_text(
                "大項目,中項目,コード,,名称\n"
                ",,1100,,中枢神経系用薬\n"
                ",,1110,,全身麻酔剤\n"
                ",,1120,,催眠鎮静剤、抗不安剤\n"
                ",,1121,,有機ブロム化合物製剤\n"
                ",,1122,,メプロバメート系製剤\n"
                ",,1123,,抱水クロラール系製剤\n"
                ",,1124,,ベンゾジアゼピン系製剤\n"
                ",,1125,,バルビツール酸系、チオバルビツール酸系\n"
                ",,1126,,ブロム塩製剤\n"
                ",,1129,,催眠鎮静剤、抗不安剤その他\n",
                encoding="utf-8",
            )

            records, _ = normalize_csv(source)
            rows = build_pharmacological_code_rows_from_master(records, master)

            self.assertEqual(
                [row[2].strip() for row in rows],
                ["1100", "1110", "1120", "1121", "1122", "1123", "1124", "1125", "1126", "1129"],
            )

    def test_generate_views_accepts_external_pharmacological_master(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "■作業シート-表1.csv"
            master = root / "薬効コード-表1.csv"
            out_dir = root / "generated"

            source.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,2123,2123,β－遮断剤,製品A,一般名A,\n",
                encoding="utf-8",
            )
            master.write_text(
                "大項目,中項目,コード,,名称\n"
                ",,2000,,循環器官用薬\n"
                ",,2100,,循環器官用薬詳細\n"
                ",,2120,,β遮断剤群\n"
                ",,2123,,β－遮断剤\n",
                encoding="utf-8",
            )

            outputs = generate_views(source, out_dir, pharmacological_code_master=master)

            pharmacological_code_file = outputs["pharmacological_code"]
            contents = pharmacological_code_file.read_text(encoding="utf-8")
            self.assertIn("2000,,循環器官用薬", contents)
            self.assertIn("2123,,β－遮断剤", contents)

    def test_compare_view_directories_detects_row_differences(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            expected_dir = root / "expected"
            actual_dir = root / "actual"
            expected_dir.mkdir()
            actual_dir.mkdir()

            filenames = [
                "■作業シート-表1.csv",
                "一般名順-表1.csv",
                "製品名順-表1.csv",
                "薬効順-表1.csv",
                "薬効コード-表1.csv",
            ]
            for filename in filenames:
                (expected_dir / filename).write_text("a,b\n1,2\n", encoding="utf-8")
                (actual_dir / filename).write_text("a,b\n1,2\n", encoding="utf-8")

            (actual_dir / "製品名順-表1.csv").write_text("a,b\n9,9\n", encoding="utf-8")

            report = compare_view_directories(expected_dir, actual_dir)

            self.assertFalse(report.matches)
            product_view = next(view for view in report.views if view.view_name == "product")
            self.assertEqual(product_view.missing_row_count, 1)
            self.assertEqual(product_view.extra_row_count, 1)
            self.assertEqual(product_view.first_missing_row, ("1", "2"))
            self.assertEqual(product_view.first_extra_row, ("9", "9"))
            self.assertIn("missing_in_actual", product_view.reason_counts)
            self.assertIn("extra_in_actual", product_view.reason_counts)

    def test_compare_view_directories_reports_order_mismatch(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            expected_dir = root / "expected"
            actual_dir = root / "actual"
            expected_dir.mkdir()
            actual_dir.mkdir()

            filenames = [
                "■作業シート-表1.csv",
                "一般名順-表1.csv",
                "製品名順-表1.csv",
                "薬効順-表1.csv",
                "薬効コード-表1.csv",
            ]
            for filename in filenames:
                (expected_dir / filename).write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
                (actual_dir / filename).write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

            (actual_dir / "一般名順-表1.csv").write_text("a,b\n3,4\n1,2\n", encoding="utf-8")

            report = compare_view_directories(expected_dir, actual_dir)

            generic_view = next(view for view in report.views if view.view_name == "generic")
            self.assertFalse(generic_view.matches)
            self.assertEqual(generic_view.missing_row_count, 0)
            self.assertEqual(generic_view.extra_row_count, 0)
            self.assertFalse(generic_view.order_matches)
            self.assertEqual(generic_view.first_order_mismatch_index, 0)

    def test_compare_view_directories_classifies_keyed_reason(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            expected_dir = root / "expected"
            actual_dir = root / "actual"
            expected_dir.mkdir()
            actual_dir.mkdir()

            common_header = ",".join(SORTED_VIEW_HEADER) + "\n"
            filenames = [
                "■作業シート-表1.csv",
                "一般名順-表1.csv",
                "製品名順-表1.csv",
                "薬効順-表1.csv",
            ]
            for filename in filenames:
                (expected_dir / filename).write_text(common_header + "1,Y1,1000,1000,薬効A,製品A,一般名A,\n", encoding="utf-8")
                (actual_dir / filename).write_text(common_header + "1,Y1,,, ,製品A,一般名A,\n", encoding="utf-8")
            (expected_dir / "薬効コード-表1.csv").write_text("大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n", encoding="utf-8")
            (actual_dir / "薬効コード-表1.csv").write_text("大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n", encoding="utf-8")

            report = compare_view_directories(expected_dir, actual_dir)

            worksheet_view = next(view for view in report.views if view.view_name == "worksheet")
            self.assertGreaterEqual(worksheet_view.reason_counts.get("pharmacological_missing", 0), 1)
            self.assertEqual(worksheet_view.keyed_changes[0].key, "1")
            self.assertIn("pharmacological_code_changed", worksheet_view.keyed_changes[0].reasons)

    def test_compare_view_directories_includes_actual_contributions(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            expected_dir = root / "expected"
            actual_dir = root / "actual"
            expected_dir.mkdir()
            actual_dir.mkdir()

            common_header = ",".join(SORTED_VIEW_HEADER) + "\n"
            for filename in [
                "■作業シート-表1.csv",
                "一般名順-表1.csv",
                "製品名順-表1.csv",
                "薬効順-表1.csv",
            ]:
                (expected_dir / filename).write_text(common_header + "1,Y1,1000,1000,薬効A,製品A,一般名A,\n", encoding="utf-8")
                (actual_dir / filename).write_text(common_header + "1,Y1,,, ,製品A,一般名A,\n", encoding="utf-8")
            (expected_dir / "薬効コード-表1.csv").write_text("大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n", encoding="utf-8")
            (actual_dir / "薬効コード-表1.csv").write_text("大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n", encoding="utf-8")

            report = compare_view_directories(
                expected_dir,
                actual_dir,
                actual_contributions_by_view={
                    "worksheet": {
                        "1": [
                            {
                                "field": "display_name",
                                "source_schema": "reference_main",
                                "source_file": "/tmp/source.csv",
                                "source_row_number": 10,
                                "source_field": "display_name",
                                "value": "製品A",
                            }
                        ]
                    }
                },
            )

            worksheet_view = next(view for view in report.views if view.view_name == "worksheet")
            self.assertEqual(worksheet_view.keyed_changes[0].actual_contributions[0]["source_schema"], "reference_main")

    def test_compare_view_directories_classifies_extra_rows(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            expected_dir = root / "expected"
            actual_dir = root / "actual"
            expected_dir.mkdir()
            actual_dir.mkdir()

            expected_rows = (
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n"
                "2,Y2,1000,1000,薬効A,製品B,一般名B,\n"
            )
            actual_rows = (
                "9,Y1,1000,1000,薬効A,製品X,一般名X,\n"
                "8,Y8,1000,1000,薬効A,製品Z,一般名Z,\n"
            )
            for filename in [
                "■作業シート-表1.csv",
                "一般名順-表1.csv",
                "製品名順-表1.csv",
                "薬効順-表1.csv",
            ]:
                header = WORKSHEET_HEADER if filename == "■作業シート-表1.csv" else SORTED_VIEW_HEADER
                (expected_dir / filename).write_text(
                    ",".join(header) + "\n" + expected_rows,
                    encoding="utf-8",
                )
                (actual_dir / filename).write_text(
                    ",".join(header) + "\n" + actual_rows,
                    encoding="utf-8",
                )
            (expected_dir / "薬効コード-表1.csv").write_text("大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n", encoding="utf-8")
            (actual_dir / "薬効コード-表1.csv").write_text("大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n", encoding="utf-8")

            report = compare_view_directories(expected_dir, actual_dir)

            worksheet_view = next(view for view in report.views if view.view_name == "worksheet")
            extra_changes = {
                change.key: change
                for change in worksheet_view.keyed_changes
                if change.reasons == ("extra_in_actual",)
            }
            self.assertEqual(extra_changes["9"].classification, "name_variant_same_yj")
            self.assertEqual(extra_changes["9"].related_keys, ("1",))
            self.assertEqual(extra_changes["8"].classification, "legacy_scope_exclusion_candidate")
            self.assertEqual(worksheet_view.classification_counts["name_variant_same_yj"], 1)
            self.assertEqual(worksheet_view.classification_counts["legacy_scope_exclusion_candidate"], 1)

    def test_render_compare_views_writes_json_output(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "■作業シート-表1.csv"
            reference_dir = root / "reference"
            output_dir = root / "generated"
            json_path = root / "report" / "diff.json"
            config_path = root / "config.json"
            reference_dir.mkdir()

            source.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )
            for filename in [
                "■作業シート-表1.csv",
                "一般名順-表1.csv",
                "製品名順-表1.csv",
                "薬効順-表1.csv",
            ]:
                (reference_dir / filename).write_text(
                    ",".join(SORTED_VIEW_HEADER) + "\n1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                    encoding="utf-8",
                )
            (reference_dir / "■作業シート-表1.csv").write_text(
                ",".join(WORKSHEET_HEADER) + "\n1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )
            (reference_dir / "薬効コード-表1.csv").write_text(
                "大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n",
                encoding="utf-8",
            )
            write_local_profile_config(config_path, reference_dir)

            render_compare_views(
                source,
                reference_dir,
                output_dir,
                config_path=config_path,
                json_output_path=json_path,
            )

            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("views", payload)

            summary_dir = json_path.parent / f"{json_path.stem}-views"
            self.assertTrue((summary_dir / "worksheet-summary.json").exists())

    def test_render_compare_views_writes_html_output(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "■作業シート-表1.csv"
            reference_dir = root / "reference"
            output_dir = root / "generated"
            html_path = root / "report" / "diff.html"
            config_path = root / "config.json"
            reference_dir.mkdir()

            source.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )
            for filename in [
                "■作業シート-表1.csv",
                "一般名順-表1.csv",
                "製品名順-表1.csv",
                "薬効順-表1.csv",
            ]:
                (reference_dir / filename).write_text(
                    ",".join(SORTED_VIEW_HEADER) + "\n1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                    encoding="utf-8",
                )
            (reference_dir / "■作業シート-表1.csv").write_text(
                ",".join(WORKSHEET_HEADER) + "\n1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )
            (reference_dir / "薬効コード-表1.csv").write_text(
                "大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n",
                encoding="utf-8",
            )
            write_local_profile_config(config_path, reference_dir)

            render_compare_views(
                source,
                reference_dir,
                output_dir,
                config_path=config_path,
                html_output_path=html_path,
            )

            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("<html", html_text)
            self.assertIn("worksheet", html_text)
            self.assertIn("search", html_text)
            self.assertIn("keySearch", html_text)
            self.assertIn("reason counts", html_text)
            self.assertIn("keyed changes", html_text)

    def test_render_publish_report_writes_docs_structure(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "■作業シート-表1.csv"
            reference_dir = root / "reference"
            docs_dir = root / "docs"
            config_path = root / "config.json"
            reference_dir.mkdir()
            docs_dir.mkdir()

            source.write_text(
                "点数ｺｰﾄﾞ,YJコード,薬効コード,薬効コード,薬効,表示用名称,一般名称,用事購入薬品\n"
                "1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )
            for filename in [
                "■作業シート-表1.csv",
                "一般名順-表1.csv",
                "製品名順-表1.csv",
                "薬効順-表1.csv",
            ]:
                (reference_dir / filename).write_text(
                    ",".join(SORTED_VIEW_HEADER) + "\n1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                    encoding="utf-8",
                )
            (reference_dir / "■作業シート-表1.csv").write_text(
                ",".join(WORKSHEET_HEADER) + "\n1,Y1,1000,1000,薬効A,製品A,一般名A,\n",
                encoding="utf-8",
            )
            (reference_dir / "薬効コード-表1.csv").write_text(
                "大項目,中項目,コード,,名称\n,,1000 ,,薬効A\n",
                encoding="utf-8",
            )
            write_local_profile_config(config_path, reference_dir)

            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                summary = render_publish_report(
                    source,
                    reference_dir,
                    "latest",
                    config_path=config_path,
                )
            finally:
                os.chdir(original_cwd)

            self.assertTrue((docs_dir / "audit-reports" / "latest" / "diff-report.json").exists())
            self.assertTrue((docs_dir / "audit-reports" / "latest" / "diff-report.html").exists())
            history_dir = docs_dir / "audit-reports" / "history"
            history_children = [path for path in history_dir.iterdir() if path.is_dir()]
            self.assertEqual(len(history_children), 1)
            self.assertTrue(history_children[0].name.startswith(datetime.now().strftime("%Y%m%d")))
            self.assertTrue((history_children[0] / "diff-report.json").exists())
            self.assertIn("Latest report directory:", summary)
            self.assertIn("History report directory:", summary)


if __name__ == "__main__":
    unittest.main()