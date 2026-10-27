"""Render a single self-contained HTML dashboard (no JavaScript, no external assets).

Status is never conveyed by colour alone: every badge and heatmap cell also carries the
words Red / Amber / Green, so the page is readable in greyscale and by colour-blind users.
"""
from datetime import date
from html import escape

from . import report

COLORS = {"Green": ("#e6f4ea", "#1e7e34"), "Amber": ("#fff4d6", "#9a6700"), "Red": ("#fde7e9", "#b3261e")}

CSS = """
body{margin:0;padding:24px 16px 48px;background:#f4f6f9;color:#1f2933;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;line-height:1.45}
.wrap{max-width:1040px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:30px 0 10px;border-bottom:2px solid #d5dbe3;padding-bottom:5px}
.sub{color:#52606d;font-size:14px;margin:0 0 14px}
.banner{background:#fff4d6;border:1px solid #e8cf84;border-radius:6px;padding:8px 12px;font-size:13px;margin:12px 0}
.sum{margin:14px 0}.pill{display:inline-block;margin:0 8px 6px 0;padding:6px 12px;border-radius:16px;font-weight:600;font-size:14px}
.cards{margin:0 -6px}.card{display:inline-block;vertical-align:top;box-sizing:border-box;width:33.33%;padding:6px}
.card .in{background:#fff;border:1px solid #d5dbe3;border-radius:8px;padding:12px 14px}
.card .nm{font-size:13px;color:#52606d;min-height:34px}.card .val{font-size:30px;font-weight:700;margin:2px 0}
.card .unit{font-size:14px;font-weight:400;color:#52606d}.badge{display:inline-block;padding:2px 9px;border-radius:10px;font-size:12px;font-weight:700}
.chg{font-size:12px;color:#52606d;margin:4px 0}.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;background:#fff;font-size:13px}th,td{border:1px solid #d5dbe3;padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef1f5}.c{text-align:center;white-space:nowrap}.na{color:#7b8794;text-align:center}
ul{margin:6px 0;padding-left:20px}li{margin:4px 0;font-size:14px}.ok{color:#1e7e34;font-weight:600}.bad{color:#b3261e;font-weight:600}
.foot{margin-top:30px;font-size:12px;color:#52606d}svg{display:block;margin-top:6px}
@media (max-width:760px){.card{width:100%}h1{font-size:20px}}
@media (prefers-color-scheme:dark){body{background:#111820;color:#e4e8ee}h2{border-color:#33404f}.sub,.card .nm,.card .unit,.chg,.foot{color:#a5b1c0}
.card .in,table{background:#1a232e;border-color:#33404f}th,td{border-color:#33404f}th{background:#222d3a}.banner{background:#3a3217;border-color:#6b5b24;color:#f1e3b0}}
"""

DARK_BADGE_NOTE = ""


def fmt(value, unit):
    if value is None:
        return "n/a"
    if unit == "count":
        return f"{value:.0f}"
    return f"{value:.1f}"


def badge(status):
    bg, fg = COLORS[status]
    return f'<span class="badge" style="background:{bg};color:{fg}">{status}</span>'


def sparkline(series, amber, red, w=250, h=58, pad=6):
    vals = [v for _, v in series]
    lo, hi = min(vals + [amber, red]), max(vals + [amber, red])
    span = (hi - lo) or 1.0

    def xy(i, v):
        x = pad + i * (w - 2 * pad) / max(len(vals) - 1, 1)
        y = h - pad - (v - lo) / span * (h - 2 * pad)
        return x, y

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, v) for i, v in enumerate(vals)))
    lines = "".join(f'<line x1="0" x2="{w}" y1="{xy(0, t)[1]:.1f}" y2="{xy(0, t)[1]:.1f}" stroke="{c}" stroke-dasharray="3 3" stroke-width="1"/>'
                    for t, c in ((amber, "#c98a00"), (red, "#c0392b")))
    ex, ey = xy(len(vals) - 1, vals[-1])
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="12-month trend">{lines}'
            f'<polyline fill="none" stroke="#3b6ea5" stroke-width="2" points="{pts}"/>'
            f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3.5" fill="#3b6ea5"/></svg>')


def change_text(r):
    prev = r["value_3m_ago"]
    if prev is None:
        return "No value 3 months ago"
    delta = r["value"] - prev
    if abs(delta) < 0.05:
        return "Unchanged vs 3 months ago"
    worse = (delta > 0) == (r["direction"] == "higher_is_worse")
    arrow = "&#9650;" if delta > 0 else "&#9660;"
    unit = " pts" if r["unit"] == "%" else (" " + escape(r["unit"]) if r["unit"] != "count" else "")
    word = "worse" if worse else "better"
    return f"{arrow} {abs(delta):.1f}{unit} {word} vs 3 months ago"


def month_label(iso):
    d = date.fromisoformat(iso)
    return d.strftime("%B %Y")


def build_html(conn, check_results):
    month = report.latest_month(conn)
    snap = report.enterprise_snapshot(conn, month)
    series = report.enterprise_series(conn)
    counts = report.status_counts(snap)
    grid = report.heatmap(conn, month)
    movers = report.movers(conn, month)
    defs = report.definitions(conn)
    kri_ids = [d["kri_id"] for d in defs]
    short = {d["kri_id"]: d["name"] for d in defs}

    pills = "".join(f'<span class="pill" style="background:{COLORS[s][0]};color:{COLORS[s][1]}">{counts[s]} {s}</span>'
                    for s in ("Red", "Amber", "Green"))

    cards = ""
    for r in snap:
        cards += (f'<div class="card"><div class="in"><div class="nm">{escape(r["kri_id"])} &middot; {escape(r["name"])}</div>'
                  f'<div class="val">{fmt(r["value"], r["unit"])} <span class="unit">{escape(r["unit"])}</span></div>'
                  f'{badge(r["status"])}<div class="chg">{change_text(r)}</div>'
                  f'{sparkline(series[r["kri_id"]], r["amber"], r["red"])}</div></div>')

    head = "".join(f'<th class="c">{escape(k)}</th>' for k in kri_ids)
    body = ""
    for bu in sorted(grid):
        cells = ""
        for k in kri_ids:
            c = grid[bu].get(k)
            if c is None:
                cells += '<td class="na">n/a</td>'
            else:
                bg, fg = COLORS[c["status"]]
                unit = next(d["unit"] for d in defs if d["kri_id"] == k)
                cells += f'<td class="c" style="background:{bg};color:{fg}"><b>{fmt(c["value"], unit)}</b> {c["status"][0]}</td>'
        body += f"<tr><th>{escape(bu)}</th>{cells}</tr>"

    if movers:
        notes = "".join(
            f'<li><b>{escape(m["business_unit"])}</b>: {escape(short[m["kri_id"]])} moved {m["status_before"]} &rarr; {m["status"]} '
            f'({fmt(m["value_3m_ago"], m["unit"])} &rarr; {fmt(m["value"], m["unit"])} {escape(m["unit"])})</li>' for m in movers)
    else:
        notes = "<li>No business-unit KRI worsened in status over the last three months.</li>"

    method = ""
    for d in defs:
        worse = "higher is worse" if d["direction"] == "higher_is_worse" else "lower is worse"
        method += (f'<tr><td>{escape(d["kri_id"])}</td><td><b>{escape(d["name"])}</b><br>{escape(d["description"])}</td>'
                   f'<td>{worse}</td><td>Amber {d["bu_amber"]:g} / Red {d["bu_red"]:g}</td>'
                   f'<td>Amber {d["ent_amber"]:g} / Red {d["ent_red"]:g}</td></tr>')

    passed = sum(r["passed"] for r in check_results)
    checks = "".join(f'<li><span class="{"ok" if r["passed"] else "bad"}">{"PASS" if r["passed"] else "FAIL"}</span> '
                     f'{escape(r["description"])}</li>' for r in check_results)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Technology Risk KRI Dashboard (synthetic data)</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Technology Risk: KRI Dashboard</h1>
<p class="sub">Reporting month: <b>{escape(month_label(month))}</b> &middot; 7 business units &middot; 6 KRIs</p>
<div class="banner"><b>Synthetic data.</b> Every number on this page was generated for demonstration. It does not describe any real organisation.</div>
<div class="sum">{pills}</div>

<h2>Enterprise KRIs</h2>
<div class="cards">{cards}</div>
<p class="sub">Sparklines show the last 12 months. Dashed lines mark the amber and red thresholds.</p>

<h2>What changed in the last three months</h2>
<ul>{notes}</ul>

<h2>Business unit heatmap, {escape(month_label(month))}</h2>
<div class="scroll"><table><tr><th>Business unit</th>{head}</tr>{body}</table></div>
<p class="sub">G / A / R = Green / Amber / Red. n/a = no events in the period (for example, no incidents to measure detection time).</p>

<h2>Methodology</h2>
<div class="scroll"><table><tr><th>ID</th><th>KRI and definition</th><th>Direction</th><th>Business unit thresholds</th><th>Enterprise thresholds</th></tr>{method}</table></div>
<p class="sub">Enterprise ratios are <b>pooled</b> (total numerator over total denominator), not an average of business-unit percentages, so large units carry proportionate weight. A value exactly on a threshold takes the worse status.</p>

<h2>Data integrity: {passed} of {len(check_results)} reconciliation checks passed</h2>
<ul>{checks}</ul>

<p class="foot">Generated by the kri-reporting project. KRIs are calculated in SQL (see sql/kri_views.sql) and this page is built from those views.</p>
</div></body></html>"""
