"""Post-apply HTML report generation (NEXT-25).

After each apply run, generates an HTML report showing what changed:
items moved, categories applied, confidence scores, errors, and timing.
Auto-opens in the default browser or displays inline.
"""
import html
import os
import tempfile
import webbrowser
from datetime import datetime
from typing import Dict, List, Optional


def generate_html_report(
    run_id: str,
    undo_ops: List[Dict],
    ok_count: int,
    err_count: int,
    timing_summary: Optional[Dict[str, int]] = None,
    auto_open: bool = True,
) -> str:
    """Generate an HTML report of the apply run.

    Args:
        run_id: Unique run identifier
        undo_ops: List of undo operation dicts from ApplyWorker
        ok_count: Number of successful moves
        err_count: Number of failed moves
        timing_summary: Optional {phase_name: elapsed_ms} dict
        auto_open: If True, open the report in the default browser

    Returns:
        Path to the generated HTML file
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    categories: Dict[str, int] = {}
    for op in undo_ops:
        cat = op.get("category", "Unknown")
        categories[cat] = categories.get(cat, 0) + 1

    rows_html = []
    for i, op in enumerate(undo_ops, 1):
        status = op.get("status", "")
        status_class = "success" if status == "Done" else "error"
        conf = op.get("confidence", "?")
        rows_html.append(
            f'<tr class="{status_class}">'
            f"<td>{i}</td>"
            f"<td>{_esc(os.path.basename(op.get('dst', '')))}</td>"
            f"<td>{_esc(op.get('category', ''))}</td>"
            f"<td>{conf}</td>"
            f"<td>{_esc(status)}</td>"
            f"</tr>"
        )

    cat_rows = []
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        cat_rows.append(f"<tr><td>{_esc(cat)}</td><td>{count}</td></tr>")

    timing_html = ""
    if timing_summary:
        timing_rows = []
        for phase, ms in timing_summary.items():
            if ms < 1000:
                timing_rows.append(f"<tr><td>{_esc(phase)}</td><td>{ms}ms</td></tr>")
            else:
                timing_rows.append(f"<tr><td>{_esc(phase)}</td><td>{ms / 1000:.1f}s</td></tr>")
        timing_html = f"""
        <h2>Timing</h2>
        <table><thead><tr><th>Phase</th><th>Duration</th></tr></thead>
        <tbody>{''.join(timing_rows)}</tbody></table>
        """

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FileOrganizer Report — {_esc(run_id)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #1e1e2e; color: #cdd6f4; margin: 2rem; }}
  h1 {{ color: #cba6f7; margin-bottom: 0.5rem; }}
  h2 {{ color: #89b4fa; border-bottom: 1px solid #313244; padding-bottom: 0.5rem; }}
  .stats {{ display: flex; gap: 2rem; margin: 1rem 0; }}
  .stat {{ background: #313244; padding: 1rem 1.5rem; border-radius: 8px; }}
  .stat .value {{ font-size: 2rem; font-weight: bold; color: #a6e3a1; }}
  .stat.errors .value {{ color: #f38ba8; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th {{ background: #313244; padding: 0.75rem; text-align: left; color: #89b4fa; }}
  td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid #313244; }}
  tr.success td {{ color: #a6e3a1; }}
  tr.error td {{ color: #f38ba8; }}
  .meta {{ color: #6c7086; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>FileOrganizer Apply Report</h1>
<p class="meta">Run: {_esc(run_id)} | Generated: {timestamp}</p>

<div class="stats">
  <div class="stat"><div class="value">{ok_count}</div>Moved</div>
  <div class="stat errors"><div class="value">{err_count}</div>Errors</div>
  <div class="stat"><div class="value">{len(categories)}</div>Categories</div>
  <div class="stat"><div class="value">{ok_count + err_count}</div>Total</div>
</div>

<h2>Category Distribution</h2>
<table>
<thead><tr><th>Category</th><th>Count</th></tr></thead>
<tbody>{''.join(cat_rows)}</tbody>
</table>

{timing_html}

<h2>Move Details</h2>
<table>
<thead><tr><th>#</th><th>Item</th><th>Category</th><th>Confidence</th><th>Status</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>

</body></html>"""

    report_dir = os.path.join(
        os.environ.get("APPDATA", tempfile.gettempdir()),
        "FileOrganizer", "reports"
    )
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(
        report_dir, f"report_{run_id.replace(':', '-')}.html"
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    if auto_open:
        try:
            webbrowser.open(f"file:///{report_path.replace(os.sep, '/')}")
        except Exception:
            pass

    return report_path


def _esc(text: str) -> str:
    return html.escape(str(text or ""))
