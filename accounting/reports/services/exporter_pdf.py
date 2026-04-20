"""
PDF export.

Try WeasyPrint for pixel-accurate multi-page output with proper page breaks.
If WeasyPrint isn't installed (common on Windows dev boxes — it needs GTK
runtime DLLs), raise :class:`PdfBackendUnavailable`. The view layer catches
this and returns HTTP 501 with a clear "use client-side html2pdf.js or
install WeasyPrint" message — better than a 500 or a silent fallback.

The HTML template is kept deliberately plain so future skinning is easy and
so a non-WeasyPrint fallback (reportlab, browserless Chrome, Gotenberg) can
drop in without changing the data shape.
"""

from __future__ import annotations

from html import escape
from typing import Any, Dict, List


class PdfBackendUnavailable(RuntimeError):
    """Raised when no server-side PDF renderer is installed."""


def build_pdf(result: Dict[str, Any], name: str = "Demonstrativo") -> bytes:
    """Render ``result`` to a PDF byte string.

    Raises :class:`PdfBackendUnavailable` when no server-side backend is
    available — the view turns this into a 501.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as exc:  # pragma: no cover — depends on host install
        raise PdfBackendUnavailable(
            "WeasyPrint is not installed. Install it on the server "
            "(`pip install weasyprint` + GTK runtime on Windows) or use "
            "the client-side PDF export (html2pdf.js) in the frontend."
        ) from exc

    html = _render_html(result, name)
    return HTML(string=html).write_pdf()


def _render_html(result: Dict[str, Any], name: str) -> str:
    periods: List[dict] = result.get("periods", [])
    lines: List[dict] = result.get("lines", [])
    template = result.get("template") or {}

    # Header row
    header_cells = ["<th class='label'>Linha</th>"] + [
        f"<th>{escape(p.get('label') or p['id'])}</th>" for p in periods
    ]

    # Body rows
    body_rows: List[str] = []
    for line in lines:
        if line["type"] == "spacer":
            body_rows.append("<tr class='spacer'><td colspan='99'>&nbsp;</td></tr>")
            continue

        classes = [f"type-{line['type']}"]
        if line.get("bold") or line["type"] in ("subtotal", "total", "header", "section"):
            classes.append("bold")
        indent = int(line.get("indent") or line.get("depth") or 0)

        cells: List[str] = []
        cells.append(
            f"<td class='label' style='padding-left:{indent * 16}px'>"
            f"{escape(line.get('label') or line['id'])}</td>"
        )
        for p in periods:
            val = line.get("values", {}).get(p["id"])
            if val is None:
                cells.append("<td></td>")
            elif p["type"] in ("variance_pct", "variance_pp"):
                cells.append(f"<td class='num'>{val:.2f}%</td>")
            else:
                cells.append(f"<td class='num'>{_fmt(val)}</td>")

        body_rows.append(f"<tr class=\"{ ' '.join(classes) }\">{''.join(cells)}</tr>")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<title>{escape(template.get("name", name))}</title>
<style>
  @page {{ size: A4; margin: 18mm 14mm; }}
  body {{ font-family: -apple-system, Segoe UI, sans-serif; color: #111; font-size: 10pt; }}
  h1 {{ font-size: 16pt; margin: 0 0 2mm 0; }}
  .subtitle {{ color: #666; margin-bottom: 6mm; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{ background: #1f2937; color: #fff; padding: 6px; font-weight: 600; }}
  thead th.label {{ text-align: left; }}
  thead th:not(.label) {{ text-align: right; }}
  tbody td {{ padding: 4px 6px; border-bottom: 1px solid #eee; }}
  tbody td.label {{ width: 40%; }}
  tbody td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.bold td {{ font-weight: 600; }}
  tr.type-total td {{ border-top: 2px solid #111; }}
  tr.type-subtotal td {{ border-top: 1px solid #999; }}
  tr.spacer td {{ border: none; height: 6px; }}
  tr.type-section td {{ background: #f3f4f6; }}
  tr.type-header td {{ background: #e5e7eb; font-weight: 600; }}
  footer {{ position: fixed; bottom: 6mm; right: 14mm; color: #999; font-size: 8pt; }}
</style>
</head>
<body>
<h1>{escape(template.get("name", name))}</h1>
<div class="subtitle">{escape(_format_report_type(template.get("report_type", "")))}</div>
<table>
  <thead><tr>{''.join(header_cells)}</tr></thead>
  <tbody>{''.join(body_rows)}</tbody>
</table>
</body>
</html>"""
    return html


def _fmt(v: Any) -> str:
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return escape(str(v))


def _format_report_type(rt: str) -> str:
    labels = {
        "income_statement": "Demonstração de Resultado",
        "balance_sheet": "Balanço Patrimonial",
        "cash_flow": "Fluxo de Caixa",
        "trial_balance": "Balancete",
        "general_ledger": "Razão",
        "custom": "Relatório Personalizado",
    }
    return labels.get(rt, rt.replace("_", " ").title())
