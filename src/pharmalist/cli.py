from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from pharmalist.config import load_config
from pharmalist.diff import compare_view_directories
from pharmalist.normalize import normalize_target
from pharmalist.output import generate_views, generate_views_with_context
from pharmalist.profile import build_input_profile
from pharmalist.reporting import write_html_report, write_view_summary_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pharmalist",
        description="Deterministic tooling for profiling pharmaceutical CSV inputs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser(
        "profile",
        help="Inspect CSV files under a file or directory and report encoding and headers.",
    )
    profile_parser.add_argument("path", help="CSV file or directory to inspect")
    profile_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )

    normalize_parser = subparsers.add_parser(
        "normalize",
        help="Map source CSV rows into the standard schema and preview normalized rows.",
    )
    normalize_parser.add_argument("path", help="CSV file or directory to normalize")
    normalize_parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of rows to preview per file",
    )
    normalize_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )

    generate_parser = subparsers.add_parser(
        "generate-views",
        help="Generate the old adoption list style derivative CSV views from normalized data.",
    )
    generate_parser.add_argument("path", help="CSV file or directory to process")
    generate_parser.add_argument("output_dir", help="Directory where generated CSV files will be written")
    generate_parser.add_argument(
        "--config",
        help="Optional JSON config file overriding default priorities and masters.",
    )
    generate_parser.add_argument(
        "--pharmacological-code-master",
        help="Optional CSV master for pharmacological code hierarchy.",
    )

    compare_parser = subparsers.add_parser(
        "compare-views",
        help="Generate the 5 legacy-style views and compare them against an old reference directory.",
    )
    compare_parser.add_argument("path", help="CSV file or directory to process")
    compare_parser.add_argument("reference_dir", help="Directory containing the old 5 reference views")
    compare_parser.add_argument("output_dir", help="Directory where generated CSV files will be written")
    compare_parser.add_argument(
        "--config",
        help="Optional JSON config file overriding default priorities and masters.",
    )
    compare_parser.add_argument(
        "--pharmacological-code-master",
        help="Optional CSV master for pharmacological code hierarchy.",
    )
    compare_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    compare_parser.add_argument(
        "--json-output",
        help="Optional path to save the diff report as JSON.",
    )
    compare_parser.add_argument(
        "--html-output",
        help="Optional path to save the diff report as HTML.",
    )

    publish_parser = subparsers.add_parser(
        "publish-report",
        help="Write generated views and diff reports into docs/ under a standard audit folder.",
    )
    publish_parser.add_argument("path", help="CSV file or directory to process")
    publish_parser.add_argument("reference_dir", help="Directory containing the old 5 reference views")
    publish_parser.add_argument(
        "--config",
        help="Optional JSON config file overriding default priorities and masters.",
    )
    publish_parser.add_argument(
        "--name",
        default="audit",
        help="History folder suffix under docs/audit-reports/history/.",
    )
    publish_parser.add_argument(
        "--pharmacological-code-master",
        help="Optional CSV master for pharmacological code hierarchy.",
    )

    return parser


def render_profile_as_json(path: Path) -> str:
    profile = build_input_profile(path)
    payload = {
        "root": str(profile.root),
        "file_count": profile.file_count,
        "total_rows": profile.total_rows,
        "files": [
            {
                "path": str(file.path),
                "encoding": file.encoding,
                "row_count": file.row_count,
                "size_bytes": file.size_bytes,
                "header": file.header,
            }
            for file in profile.files
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_profile_as_text(path: Path) -> str:
    profile = build_input_profile(path)
    lines = [
        f"Root: {profile.root}",
        f"CSV files: {profile.file_count}",
        f"Total data rows: {profile.total_rows}",
        "",
    ]

    for file in profile.files:
        lines.extend(
            [
                f"- {file.path}",
                f"  encoding: {file.encoding}",
                f"  data rows: {file.row_count}",
                f"  size bytes: {file.size_bytes}",
                f"  header columns: {len(file.header)}",
                f"  header: {', '.join(file.header[:8])}",
            ]
        )

    return "\n".join(lines)


def render_normalized_as_json(path: Path, limit: int) -> str:
    normalized_files = normalize_target(path, limit_per_file=limit)
    payload = {
        "target": str(path),
        "files": [
            {
                "path": str(file_path),
                "missing_fields": list(missing_fields),
                "records": [record.to_dict() for record in records],
            }
            for file_path, records, missing_fields in normalized_files
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_normalized_as_text(path: Path, limit: int) -> str:
    normalized_files = normalize_target(path, limit_per_file=limit)
    lines = [f"Target: {path}", ""]
    for file_path, records, missing_fields in normalized_files:
        lines.append(f"- {file_path}")
        lines.append(f"  preview rows: {len(records)}")
        lines.append(
            "  missing mapped fields: "
            + (", ".join(missing_fields) if missing_fields else "none")
        )
        if records:
            sample = records[0]
            lines.append(
                "  sample: "
                + ", ".join(
                    f"{key}={value or '-'}"
                    for key, value in sample.to_dict().items()
                    if key
                    not in {"source_file", "source_schema", "source_row_number"}
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def render_generated_views(
    path: Path,
    output_dir: Path,
    config_path: Path | None = None,
    pharmacological_code_master: Path | None = None,
) -> str:
    config = load_config(config_path)
    master_path = pharmacological_code_master or config.pharmacological_code_master
    outputs = generate_views(
        path,
        output_dir,
        source_priority=config.source_priority,
        pharmacological_code_master=master_path,
        pharmacological_hierarchy=config.pharmacological_hierarchy,
        pharmacological_fill=config.pharmacological_fill,
        legacy_view_scope=config.legacy_view_scope,
        legacy_view_adjustments=config.legacy_view_adjustments,
        legacy_view_overrides=config.legacy_view_overrides,
        legacy_view_order=config.legacy_view_order,
    )
    lines = [f"Target: {path}", f"Output directory: {output_dir}", ""]
    lines.insert(2, f"Config: {config.config_path}")
    if master_path is not None:
        lines.insert(3, f"Pharmacological code master: {master_path}")
    for label, output_path in outputs.items():
        lines.append(f"- {label}: {output_path}")
    return "\n".join(lines)


def render_compare_views(
    path: Path,
    reference_dir: Path,
    output_dir: Path,
    config_path: Path | None = None,
    pharmacological_code_master: Path | None = None,
    as_json: bool = False,
    json_output_path: Path | None = None,
    html_output_path: Path | None = None,
) -> str:
    config = load_config(config_path)
    master_path = pharmacological_code_master or config.pharmacological_code_master
    generated = generate_views_with_context(
        path,
        output_dir,
        source_priority=config.source_priority,
        pharmacological_code_master=master_path,
        pharmacological_hierarchy=config.pharmacological_hierarchy,
        pharmacological_fill=config.pharmacological_fill,
        legacy_view_scope=config.legacy_view_scope,
        legacy_view_adjustments=config.legacy_view_adjustments,
        legacy_view_overrides=config.legacy_view_overrides,
        legacy_view_order=config.legacy_view_order,
    )
    report = compare_view_directories(
        reference_dir,
        output_dir,
        actual_contributions_by_view=generated.contributions_by_view,
    )
    report_json = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if json_output_path is not None:
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(report_json, encoding="utf-8")
        summary_paths = write_view_summary_files(report, json_output_path)
    else:
        summary_paths = {}
    if html_output_path is not None:
        write_html_report(report, html_output_path)
    if as_json:
        return report_json

    lines = [
        f"Target: {path}",
        f"Reference directory: {reference_dir}",
        f"Generated directory: {output_dir}",
        f"Config: {config.config_path}",
    ]
    if master_path is not None:
        lines.append(f"Pharmacological code master: {master_path}")
    if json_output_path is not None:
        lines.append(f"JSON report: {json_output_path}")
        lines.append(
            "JSON summaries: "
            + ", ".join(f"{view}={path}" for view, path in summary_paths.items())
        )
    if html_output_path is not None:
        lines.append(f"HTML report: {html_output_path}")
    lines.append(f"Overall match: {'yes' if report.matches else 'no'}")
    lines.append("")
    for view in report.views:
        lines.append(f"- {view.view_name}: {'match' if view.matches else 'diff'}")
        lines.append(
            f"  rows expected/actual: {view.expected_row_count}/{view.actual_row_count}"
        )
        lines.append(
            f"  missing/extra rows: {view.missing_row_count}/{view.extra_row_count}"
        )
        lines.append(f"  header match: {'yes' if view.header_matches else 'no'}")
        lines.append(f"  order match: {'yes' if view.order_matches else 'no'}")
        if view.reason_counts:
            lines.append(
                "  reason counts: "
                + ", ".join(f"{reason}={count}" for reason, count in view.reason_counts.items())
            )
        if view.classification_counts:
            lines.append(
                "  classification counts: "
                + ", ".join(
                    f"{classification}={count}"
                    for classification, count in view.classification_counts.items()
                )
            )
        if view.first_missing_row is not None:
            lines.append(f"  first missing row: {' | '.join(view.first_missing_row)}")
        if view.first_extra_row is not None:
            lines.append(f"  first extra row: {' | '.join(view.first_extra_row)}")
        if view.first_order_mismatch_index is not None:
            lines.append(f"  first order mismatch index: {view.first_order_mismatch_index}")
        if view.keyed_changes:
            sample = view.keyed_changes[0]
            lines.append(
                f"  first keyed change: key={sample.key}, reasons={','.join(sample.reasons)}"
            )
            if sample.actual_contributions:
                first_contribution = sample.actual_contributions[0]
                lines.append(
                    "  first contribution: "
                    + ", ".join(f"{key}={value}" for key, value in first_contribution.items())
                )
        lines.append("")
    return "\n".join(lines).rstrip()


def render_publish_report(
    path: Path,
    reference_dir: Path,
    report_name: str,
    config_path: Path | None = None,
    pharmacological_code_master: Path | None = None,
) -> str:
    audit_root = Path("docs").resolve() / "audit-reports"
    latest_root = audit_root / "latest"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_name = "-".join(part for part in report_name.replace("_", "-").split("-") if part) or "audit"
    history_root = audit_root / "history" / f"{timestamp}-{safe_name}"
    generated_dir = history_root / "generated-views"
    json_output_path = history_root / "diff-report.json"
    html_output_path = history_root / "diff-report.html"
    summary = render_compare_views(
        path,
        reference_dir,
        generated_dir,
        config_path=config_path,
        pharmacological_code_master=pharmacological_code_master,
        json_output_path=json_output_path,
        html_output_path=html_output_path,
    )
    latest_root.parent.mkdir(parents=True, exist_ok=True)
    if latest_root.exists():
        shutil.rmtree(latest_root)
    shutil.copytree(history_root, latest_root)
    return (
        summary
        + "\n\n"
        + f"Latest report directory: {latest_root}"
        + "\n"
        + f"History report directory: {history_root}"
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    target = Path(args.path).expanduser().resolve()

    if args.command == "profile":
        if args.json:
            print(render_profile_as_json(target))
        else:
            print(render_profile_as_text(target))
        return 0

    if args.command == "normalize":
        if args.json:
            print(render_normalized_as_json(target, args.limit))
        else:
            print(render_normalized_as_text(target, args.limit))
        return 0

    if args.command == "generate-views":
        output_dir = Path(args.output_dir).expanduser().resolve()
        config_path = Path(args.config).expanduser().resolve() if args.config else None
        master_path = (
            Path(args.pharmacological_code_master).expanduser().resolve()
            if args.pharmacological_code_master
            else None
        )
        print(
            render_generated_views(
                target,
                output_dir,
                config_path=config_path,
                pharmacological_code_master=master_path,
            )
        )
        return 0

    if args.command == "compare-views":
        reference_dir = Path(args.reference_dir).expanduser().resolve()
        output_dir = Path(args.output_dir).expanduser().resolve()
        config_path = Path(args.config).expanduser().resolve() if args.config else None
        json_output_path = Path(args.json_output).expanduser().resolve() if args.json_output else None
        html_output_path = Path(args.html_output).expanduser().resolve() if args.html_output else None
        master_path = (
            Path(args.pharmacological_code_master).expanduser().resolve()
            if args.pharmacological_code_master
            else None
        )
        print(
            render_compare_views(
                target,
                reference_dir,
                output_dir,
                config_path=config_path,
                pharmacological_code_master=master_path,
                as_json=args.json,
                json_output_path=json_output_path,
                html_output_path=html_output_path,
            )
        )
        return 0

    if args.command == "publish-report":
        reference_dir = Path(args.reference_dir).expanduser().resolve()
        config_path = Path(args.config).expanduser().resolve() if args.config else None
        master_path = (
            Path(args.pharmacological_code_master).expanduser().resolve()
            if args.pharmacological_code_master
            else None
        )
        print(
            render_publish_report(
                target,
                reference_dir,
                args.name,
                config_path=config_path,
                pharmacological_code_master=master_path,
            )
        )
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())