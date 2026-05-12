from __future__ import annotations

import html
import json
from pathlib import Path

from pharmalist.diff import DiffReport, ViewDiff


def build_view_summary(view: ViewDiff) -> dict[str, object]:
    return {
        "view_name": view.view_name,
        "matches": view.matches,
        "expected_path": str(view.expected_path),
        "actual_path": str(view.actual_path),
        "header_matches": view.header_matches,
        "order_matches": view.order_matches,
        "expected_row_count": view.expected_row_count,
        "actual_row_count": view.actual_row_count,
        "missing_row_count": view.missing_row_count,
        "extra_row_count": view.extra_row_count,
        "reason_counts": view.reason_counts,
        "classification_counts": view.classification_counts,
        "first_missing_row": list(view.first_missing_row) if view.first_missing_row is not None else None,
        "first_extra_row": list(view.first_extra_row) if view.first_extra_row is not None else None,
        "first_order_mismatch_index": view.first_order_mismatch_index,
        "first_keyed_change": view.keyed_changes[0].to_dict() if view.keyed_changes else None,
    }


def write_view_summary_files(report: DiffReport, report_json_path: Path) -> dict[str, Path]:
    summary_dir = report_json_path.parent / f"{report_json_path.stem}-views"
    summary_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for view in report.views:
        summary_path = summary_dir / f"{view.view_name}-summary.json"
        summary_path.write_text(
            json.dumps(build_view_summary(view), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        written[view.view_name] = summary_path
    return written


def render_html_report(report: DiffReport, title: str = "差分レポート") -> str:
    overall_reason_counts: dict[str, int] = {}
    for view in report.views:
        for reason, count in view.reason_counts.items():
            overall_reason_counts[reason] = overall_reason_counts.get(reason, 0) + count

    overall_reason_badges = "".join(
        f'<span class="badge">{html.escape(reason)} <strong>{count}</strong></span>'
        for reason, count in sorted(overall_reason_counts.items())
    ) or '<span class="badge">reason なし</span>'

    view_options = "".join(
        f'<option value="{html.escape(view.view_name)}">{html.escape(view.view_name)}</option>'
        for view in report.views
    )

    cards: list[str] = []
    for view in report.views:
        first_change = view.keyed_changes[0] if view.keyed_changes else None
        reasons_html = "<br>".join(
            f"{html.escape(reason)}: {count}" for reason, count in view.reason_counts.items()
        ) or "-"
        reason_text = ", ".join(f"{reason}:{count}" for reason, count in view.reason_counts.items())
        reason_badges = "".join(
            f'<span class="badge">{html.escape(reason)} <strong>{count}</strong></span>'
            for reason, count in view.reason_counts.items()
        ) or '<span class="badge">reason なし</span>'
        classification_badges = "".join(
            f'<span class="badge alt">{html.escape(classification)} <strong>{count}</strong></span>'
            for classification, count in view.classification_counts.items()
        ) or '<span class="badge alt">分類なし</span>'

        contribution_html = "-"
        if first_change is not None and first_change.actual_contributions:
            contribution_html = "<br>".join(
                html.escape(
                    f"{item.get('field')} / {item.get('source_schema')} / {item.get('source_file')} / {item.get('source_row_number')}"
                )
                for item in first_change.actual_contributions[:5]
            )

        change_rows: list[str] = []
        for change in view.keyed_changes:
            reasons_label = ", ".join(change.reasons)
            classification_label = change.classification or "-"
            related_label = ", ".join(change.related_keys) if change.related_keys else "-"
            change_rows.append(
                "".join(
                    [
                        f'<tr class="change-row" data-key="{html.escape(change.key.lower())}">',
                        f"<td>{html.escape(change.key)}</td>",
                        f"<td>{html.escape(reasons_label)}</td>",
                        f"<td>{html.escape(classification_label)}</td>",
                        f"<td>{html.escape(related_label)}</td>",
                        "</tr>",
                    ]
                )
            )

        cards.append(
            "".join(
                [
                    f'<section class="card" data-view="{html.escape(view.view_name)}" data-status="{"match" if view.matches else "diff"}" data-reasons="{html.escape(reason_text)}">',
                    f"<h2>{html.escape(view.view_name)}</h2>",
                    f"<p class=\"status {'ok' if view.matches else 'diff'}\">{'match' if view.matches else 'diff'}</p>",
                    f'<div class="badge-row">{reason_badges}</div>',
                    f'<div class="badge-row">{classification_badges}</div>',
                    "<dl>",
                    f"<dt>header</dt><dd>{'yes' if view.header_matches else 'no'}</dd>",
                    f"<dt>order</dt><dd>{'yes' if view.order_matches else 'no'}</dd>",
                    f"<dt>rows</dt><dd>{view.expected_row_count} / {view.actual_row_count}</dd>",
                    f"<dt>missing / extra</dt><dd>{view.missing_row_count} / {view.extra_row_count}</dd>",
                    f"<dt>reasons</dt><dd>{reasons_html}</dd>",
                    f"<dt>first key</dt><dd>{html.escape(first_change.key) if first_change is not None else '-'}</dd>",
                    f"<dt>first contribution</dt><dd>{contribution_html}</dd>",
                    "</dl>",
                    '<details class="changes"><summary>keyed changes</summary>',
                    '<div class="table-wrap"><table><thead><tr><th>key</th><th>reasons</th><th>classification</th><th>related keys</th></tr></thead><tbody>',
                    "".join(change_rows),
                    "</tbody></table></div>",
                    "</details>",
                    "</section>",
                ]
            )
        )

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f4ee;
      --panel: #fffdf8;
      --ink: #1f2328;
      --muted: #6a6f76;
      --line: #d7cfbf;
      --ok: #2f6b3b;
      --diff: #9c3d1e;
    }}
    body {{ margin: 0; font-family: "Hiragino Sans", "Yu Gothic", sans-serif; background: linear-gradient(180deg, #efe5d1 0%, var(--bg) 35%, #f8f7f2 100%); color: var(--ink); }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 32px; }}
    h2 {{ margin: 0 0 8px; font-size: 20px; }}
    .meta {{ color: var(--muted); margin-bottom: 24px; }}
    .summary-panel {{ background: rgba(255, 253, 248, 0.78); border: 1px solid var(--line); border-radius: 16px; padding: 16px; margin: 0 0 16px; }}
    .toolbar {{ display: grid; grid-template-columns: minmax(220px, 1fr) minmax(220px, 1fr) 180px 220px; gap: 12px; margin: 0 0 18px; }}
    .toolbar input, .toolbar select {{ width: 100%; border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; font: inherit; background: #fff; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 18px; box-shadow: 0 10px 24px rgba(50, 44, 32, 0.06); }}
    .status {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 700; margin: 0 0 12px; }}
    .status.ok {{ background: #e6f3e7; color: var(--ok); }}
    .status.diff {{ background: #fde9e2; color: var(--diff); }}
    .badge-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 12px; }}
    .badge {{ display: inline-flex; gap: 6px; align-items: center; border-radius: 999px; padding: 5px 10px; background: #efe6d6; color: #5d4a1f; font-size: 13px; }}
    .badge.alt {{ background: #e8eef7; color: #234f78; }}
    dl {{ margin: 0; display: grid; grid-template-columns: 140px 1fr; gap: 8px 12px; }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; line-height: 1.5; word-break: break-word; }}
    .changes {{ margin-top: 14px; }}
    .changes summary {{ cursor: pointer; font-weight: 700; }}
    .table-wrap {{ overflow: auto; margin-top: 10px; border: 1px solid var(--line); border-radius: 12px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 640px; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #ece3d4; font-size: 14px; vertical-align: top; }}
    tbody tr:last-child td {{ border-bottom: none; }}
    .hidden {{ display: none; }}
    .row-hidden {{ display: none; }}
    @media (max-width: 900px) {{
      .toolbar {{ grid-template-columns: 1fr; }}
      dl {{ grid-template-columns: 120px 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p class="meta">Overall match: {'yes' if report.matches else 'no'} / expected: {html.escape(str(report.expected_dir))} / actual: {html.escape(str(report.actual_dir))}</p>
    <section class="summary-panel">
      <h2>reason counts</h2>
      <div class="badge-row">{overall_reason_badges}</div>
    </section>
    <div class="toolbar">
      <input id="search" type="search" placeholder="view名・理由・寄与元で検索">
      <input id="keySearch" type="search" placeholder="key を直接検索">
      <select id="statusFilter">
        <option value="all">全ステータス</option>
        <option value="diff">diff のみ</option>
        <option value="match">match のみ</option>
      </select>
      <select id="viewFilter">
        <option value="all">全view</option>
        {view_options}
      </select>
    </div>
    <div class="grid">{''.join(cards)}</div>
  </main>
  <script>
    const search = document.getElementById('search');
    const keySearch = document.getElementById('keySearch');
    const statusFilter = document.getElementById('statusFilter');
    const viewFilter = document.getElementById('viewFilter');
    const cards = Array.from(document.querySelectorAll('.card'));

    function applyFilters() {{
      const q = search.value.trim().toLowerCase();
      const keyQuery = keySearch.value.trim().toLowerCase();
      const status = statusFilter.value;
      const view = viewFilter.value;
      for (const card of cards) {{
        const text = card.textContent.toLowerCase();
        const matchesQuery = !q || text.includes(q);
        const matchesStatus = status === 'all' || card.dataset.status === status;
        const matchesView = view === 'all' || card.dataset.view === view;
        const rows = Array.from(card.querySelectorAll('.change-row'));
        let visibleRows = 0;
        for (const row of rows) {{
          const rowMatchesKey = !keyQuery || row.dataset.key.includes(keyQuery);
          row.classList.toggle('row-hidden', !rowMatchesKey);
          if (rowMatchesKey) {{
            visibleRows += 1;
          }}
        }}
        const matchesKey = !keyQuery || visibleRows > 0;
        card.classList.toggle('hidden', !(matchesQuery && matchesStatus && matchesView && matchesKey));
      }}
    }}

    search.addEventListener('input', applyFilters);
    keySearch.addEventListener('input', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    viewFilter.addEventListener('change', applyFilters);
  </script>
</body>
</html>
'''


def write_html_report(report: DiffReport, html_output_path: Path, title: str = "差分レポート") -> Path:
    html_output_path.parent.mkdir(parents=True, exist_ok=True)
    html_output_path.write_text(render_html_report(report, title=title), encoding="utf-8")
    return html_output_path
