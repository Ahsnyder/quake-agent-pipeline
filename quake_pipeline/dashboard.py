"""Generate a standalone HTML report with no CDN or JavaScript dependency."""

from html import escape


def render_dashboard(data: dict, provenance: dict, local: bool) -> str:
    e = lambda value: escape(str(value), quote=True)
    s, q = data["summary"], data["quality"]

    def bars(values, color):
        maximum = max(values.values(), default=1) or 1
        return "".join(
            f'<div class="bar-row"><span>{e(label)}</span><div class="track"><div class="bar {color}" style="width:{count / maximum * 100:.2f}%"></div></div><strong>{count:,}</strong></div>'
            for label, count in values.items()) or '<p class="muted">No matching events.</p>'

    def metric(label, value, unit=""):
        value = "N/A" if value is None else value
        return f'<div class="metric"><span>{e(label)}</span><strong>{e(value)}<small>{e(unit)}</small></strong></div>'

    event_rows = "".join(
        f'<tr><td><span class="mag">{r["magnitude"]:.1f}</span></td><td>{e(r["place"])}</td><td>{e(r["time_utc"][:19].replace("T", " "))}</td><td>{r["depth_km"]:.1f}</td></tr>'
        for r in data["events"][:20]) or '<tr><td colspan="4">No events meet the selected threshold.</td></tr>'
    mode = "Local preview - cloud storage not used" if local else "Cloud workflow - see manifest.json for upload results"
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seismic / Earthquake activity report</title><style>
:root{{--ink:#132a30;--muted:#526970;--paper:#f3f6f4;--line:#dce6e2;--teal:#087f75;--orange:#c65d36}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}}main{{max-width:1140px;margin:auto;padding:34px 28px 50px}}header{{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:18px}}.brand{{font-weight:800;letter-spacing:3px}}.brand b{{color:var(--teal)}}.badge{{background:#deeee8;color:#136458;border-radius:20px;padding:6px 12px;font-size:12px}}.eyebrow{{font-size:12px;letter-spacing:2px;text-transform:uppercase;font-weight:700;color:var(--teal);margin-top:36px}}h1{{font-size:clamp(32px,5vw,52px);letter-spacing:-2px;line-height:1.08;margin:12px 0 16px}}.intro{{color:var(--muted);max-width:720px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:28px 0}}.metric,.panel{{background:white;border:1px solid var(--line);border-radius:12px;padding:22px}}.metric span{{display:block;color:var(--muted);font-size:13px}}.metric strong{{font-size:32px;display:block;margin-top:8px}}small{{font-size:13px;font-weight:500;margin-left:6px}}.grid{{display:grid;grid-template-columns:1.2fr 1fr;gap:18px}}h2{{font-size:18px;margin:0 0 4px}}.muted{{font-size:13px;color:var(--muted);margin:0 0 20px}}.bar-row{{display:grid;grid-template-columns:105px 1fr 42px;gap:10px;align-items:center;font-size:12px;margin:14px 0}}.track{{height:16px;background:#edf3f1;border-radius:3px;overflow:hidden}}.bar{{height:100%;min-width:0;border-radius:3px;background:var(--teal)}}.bar.orange{{background:var(--orange)}}.bar-row strong{{text-align:right}}.table-panel{{margin-top:18px}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}}th{{text-align:left;text-transform:uppercase;letter-spacing:1px;font-size:10px;color:var(--muted);padding:14px 10px;border-bottom:2px solid var(--line)}}td{{padding:12px 10px;border-bottom:1px solid var(--line)}}.mag{{font-weight:800;color:var(--teal)}}.quality{{display:flex;flex-wrap:wrap;gap:8px 24px;font-size:12px;margin-top:16px;color:var(--muted)}}footer{{font-size:12px;color:var(--muted);margin-top:28px}}a{{color:var(--teal)}}.run{{word-break:break-all}}@media(max-width:720px){{main{{padding:20px 16px}}.metrics{{grid-template-columns:1fr 1fr}}.grid{{grid-template-columns:1fr}}header{{align-items:flex-start;gap:15px}}.badge{{max-width:210px}}.metric{{padding:16px}}}}
</style></head><body><main>
<header><div class="brand"><b>◉</b> SEISMIC</div><span class="badge">{e(mode)}</span></header>
<div class="eyebrow">USGS data / ADK agent workflow</div>
<h1>A week in seismic activity.</h1>
<p class="intro">Earthquakes of magnitude {e(data["minimum_magnitude"])} and above, filtered from the USGS past-seven-days feed. Counts describe recorded events in this snapshot; they do not predict future activity.</p>
<div class="metrics">{metric("Earthquakes retained", f'{s["count"]:,}')}{metric("Largest magnitude", s["max_magnitude"])}{metric("Average magnitude", s["mean_magnitude"])}{metric("Average depth", s["mean_depth_km"], "km")}</div>
<div class="grid"><section class="panel"><h2>Daily activity</h2><p class="muted">Events per UTC date with matching records; partial boundary days.</p>{bars(data["daily_counts"], "teal")}</section>
<section class="panel"><h2>Magnitude distribution</h2><p class="muted">Count of retained earthquakes by magnitude band.</p>{bars(data["magnitude_counts"], "orange")}<h2 style="margin-top:25px">Depth distribution</h2><p class="muted">Count of retained earthquakes by depth band.</p>{bars(data["depth_counts"], "teal")}</section></div>
<section class="panel table-panel"><h2>Strongest recorded events</h2><p class="muted">Up to 20 events, ordered by magnitude. All times are UTC.</p><div class="scroll"><table><thead><tr><th scope="col">Magnitude</th><th scope="col">Location</th><th scope="col">Time (UTC)</th><th scope="col">Depth (km)</th></tr></thead><tbody>{event_rows}</tbody></table></div></section>
<section class="panel table-panel"><h2>Data quality ledger</h2><div class="quality">{''.join(f'<span>{e(k.replace("_", " ").title())}: <strong>{v:,}</strong></span>' for k,v in q.items())}</div><p class="muted" style="margin:14px 0 0">Invalid records are excluded. Duplicate IDs use the latest valid revision. These categories reconcile to the input record count. Magnitudes can use different USGS magnitude scales; their mean is descriptive.</p></section>
<footer><p>Source: <a href="https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php">USGS GeoJSON summary feed</a>. {e(provenance["source_kind"])} snapshot retrieved {e(provenance["retrieved_at_utc"])}.</p><p class="run">Run: {e(provenance["run_id"])}<br>Raw snapshot SHA-256: {e(provenance["raw_sha256"])}</p><p>Built by four Google ADK agents: ingest → transform → visualize → store. No external assets are needed to view this report.</p></footer>
</main></body></html>'''
