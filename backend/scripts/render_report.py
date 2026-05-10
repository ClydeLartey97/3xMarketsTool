from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment


REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17202a; }
    h1 { margin-bottom: 4px; }
    h2 { margin-top: 34px; border-bottom: 1px solid #d9e2ec; padding-bottom: 6px; }
    table { border-collapse: collapse; width: 100%; margin: 12px 0 22px; }
    th, td { border: 1px solid #d9e2ec; padding: 8px 10px; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    th { background: #f5f7fa; }
    .meta { color: #52616b; margin-top: 0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .metric { border: 1px solid #d9e2ec; padding: 12px; border-radius: 6px; }
    .metric span { display: block; color: #52616b; font-size: 12px; text-transform: uppercase; }
    .metric strong { display: block; font-size: 22px; margin-top: 4px; }
    .muted { color: #697985; }
    .ok { color: #0f766e; }
    .bad { color: #b42318; }
    svg { max-width: 100%; height: auto; }
  </style>
</head>
<body>
  <h1>{{ title }}</h1>
  <p class="meta">Generated {{ report.get("generated_at", "unknown") }} · Samples {{ report.get("sample_count", 0) }}</p>

  <h2>Headline Metrics</h2>
  <div class="grid">
    {% for key, value in report.get("metrics", {}).items() %}
      <div class="metric"><span>{{ key }}</span><strong>{{ value }}</strong></div>
    {% endfor %}
    <div class="metric"><span>Calibrated</span><strong class="{{ 'ok' if report.get('calibration', {}).get('well_calibrated') else 'bad' }}">{{ report.get("calibration", {}).get("well_calibrated", false) }}</strong></div>
  </div>

  <h2>Vs Baselines</h2>
  {{ metric_table(report.get("vs_baselines", {}))|safe }}

  <h2>Vs Forecasters</h2>
  {{ metric_table(report.get("vs_forecasters", {}))|safe }}

  <h2>Hour-Of-Day Breakdown</h2>
  {{ metric_table(sorted_metrics(report.get("metrics_by_hour", {})))|safe }}

  <h2>Regime Breakdown</h2>
  {{ metric_table(report.get("metrics_by_regime", {}))|safe }}

  <h2>PIT Histogram</h2>
  {{ pit_svg|safe }}

  <h2>LLM Ablation</h2>
  {% if ablation %}
    <div class="grid">
      <div class="metric"><span>Breach rate with LLM</span><strong>{{ ablation.get("breach_rate_with_llm") }}</strong></div>
      <div class="metric"><span>Breach rate without LLM</span><strong>{{ ablation.get("breach_rate_without_llm") }}</strong></div>
      <div class="metric"><span>Kupiec p-value with LLM</span><strong>{{ ablation.get("kupiec_p_value_with_llm") }}</strong></div>
      <div class="metric"><span>Kupiec p-value without LLM</span><strong>{{ ablation.get("kupiec_p_value_without_llm") }}</strong></div>
    </div>
    {{ metric_table(ablation.get("per_regime", {}))|safe }}
  {% else %}
    <p class="muted">No LLM ablation block is present in this JSON report.</p>
  {% endif %}
</body>
</html>
"""


def render_report(json_path: str | Path, output_path: str | Path | None = None) -> Path:
    source_path = Path(json_path)
    report = json.loads(source_path.read_text())
    output = Path(output_path) if output_path is not None else source_path.with_suffix(".html")
    ablation = report.get("llm_ablation")
    if ablation is None and "breach_rate_with_llm" in report:
        ablation = report

    env = Environment(autoescape=True)
    env.globals["metric_table"] = _metric_table
    env.globals["sorted_metrics"] = _sorted_metrics
    template = env.from_string(TEMPLATE)
    html = template.render(
        title=_title(report, source_path),
        report=report,
        ablation=ablation,
        pit_svg=_pit_histogram_svg(report.get("calibration", {})),
    )
    output.write_text(html)
    return output


def _title(report: dict[str, Any], source_path: Path) -> str:
    market = report.get("market_code") or report.get("market_name")
    if market:
        return f"Backtest Report - {market}"
    return f"Backtest Report - {source_path.stem}"


def _metric_table(rows: dict[str, Any]) -> str:
    if not rows:
        return '<p class="muted">No data.</p>'
    metric_names = sorted(
        {
            metric
            for values in rows.values()
            if isinstance(values, dict)
            for metric in values.keys()
        }
    )
    if not metric_names:
        return '<p class="muted">No metric table data.</p>'

    html = ["<table><thead><tr><th>name</th>"]
    html.extend(f"<th>{_escape(metric)}</th>" for metric in metric_names)
    html.append("</tr></thead><tbody>")
    for name, values in rows.items():
        html.append(f"<tr><td>{_escape(str(name))}</td>")
        for metric in metric_names:
            html.append(f"<td>{_escape(_format_value(values.get(metric) if isinstance(values, dict) else None))}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")
    return "".join(html)


def _sorted_metrics(rows: dict[str, Any]) -> dict[str, Any]:
    def sort_key(item: tuple[str, Any]) -> tuple[int, str]:
        key, _ = item
        try:
            return int(key), key
        except ValueError:
            return 999, key

    return dict(sorted(rows.items(), key=sort_key))


def _pit_histogram_svg(calibration: dict[str, Any]) -> str:
    shares = [float(value) for value in calibration.get("shares", [])]
    if not shares:
        return '<p class="muted">No PIT histogram data.</p>'
    expected = float(calibration.get("expected_share_per_bin", 1.0 / max(len(shares), 1)))
    width = 720
    height = 220
    margin = 32
    plot_width = width - 2 * margin
    plot_height = height - 2 * margin
    ymax = max(max(shares), expected, 0.01) * 1.15
    bar_gap = 4
    bar_width = (plot_width / len(shares)) - bar_gap
    expected_y = margin + plot_height - (expected / ymax) * plot_height

    parts = [
        f'<svg role="img" aria-label="PIT histogram" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<line x1="{margin}" x2="{width - margin}" y1="{height - margin}" y2="{height - margin}" stroke="#9aa6b2"/>',
        f'<line x1="{margin}" x2="{margin}" y1="{margin}" y2="{height - margin}" stroke="#9aa6b2"/>',
        f'<line x1="{margin}" x2="{width - margin}" y1="{expected_y:.2f}" y2="{expected_y:.2f}" stroke="#b42318" stroke-dasharray="5 5"/>',
        f'<text x="{width - margin}" y="{expected_y - 6:.2f}" text-anchor="end" fill="#b42318" font-size="12">expected {expected:.3f}</text>',
    ]
    for index, share in enumerate(shares):
        x = margin + index * (plot_width / len(shares)) + bar_gap / 2
        bar_height = (share / ymax) * plot_height
        y = margin + plot_height - bar_height
        parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{bar_height:.2f}" fill="#2f6fed"/>')
        parts.append(f'<text x="{x + bar_width / 2:.2f}" y="{height - 10}" text-anchor="middle" fill="#52616b" font-size="11">{index + 1}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a JSON backtest report to single-file HTML")
    parser.add_argument("report", help="Path to a JSON report under backend/reports")
    parser.add_argument("--output", help="Optional output HTML path")
    args = parser.parse_args()
    output = render_report(args.report, args.output)
    print(output)


if __name__ == "__main__":
    main()
