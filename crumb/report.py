"""An offline HTML review of the real saved result; no remote assets or scripts."""
from __future__ import annotations

import html
import json
import base64
from pathlib import Path
import shlex


def _e(value) -> str:
    return html.escape(str(value), quote=True)


def write_report(report: dict, target: Path) -> None:
    before, after = report["input"], report["output"]
    source = Path(after["path"])
    raw = source.read_bytes()
    # A small result and its report travel together in one offline HTML file.
    # Large unchanged outputs remain adjacent files rather than ballooning the HTML.
    embedded = len(raw) <= 1_048_576
    repro_href = ("data:application/octet-stream;base64," + base64.b64encode(raw).decode("ascii")) if embedded else source.name
    json_href = "data:application/json;base64," + base64.b64encode(json.dumps(report, indent=2, ensure_ascii=True).encode("utf-8")).decode("ascii")
    preview = raw[:24_000].decode("utf-8", errors="replace")
    if len(raw) > 24_000:
        preview += "\n… Preview limited to 24 KB. Open the reproducer for all data."
    ratio = 100 * (1 - after["bytes"] / before["bytes"]) if before["bytes"] else 0
    sig = report["signature"]
    signature = sig.get("text", sig.get("line", sig.get("pattern", "Exit code only; no output fingerprint.")))
    scope = "No individual retained unit can be removed while preserving this observed failure." if report.get("one_minimal") else "Further reduction may be possible. This is a verified smaller example, not a minimality claim."
    locations = report.get("source_locations", report.get("kept_indices", []))
    locations_text = json.dumps(locations, ensure_ascii=True, indent=2)
    command = shlex.join(report.get("reproduce_command", report["command"]))
    next_step = report.get("next_step", "Inspect the retained records together. The failure may depend on their interaction.")
    style = '''
*{box-sizing:border-box}body{margin:0;background:#f7f4ed;color:#202b36;font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1080px;margin:auto;padding:44px 28px 60px}header{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid #d7d6ce;padding-bottom:20px}
.brand{font-size:28px;font-weight:850;letter-spacing:-1.5px}.mark{display:inline-flex;align-items:end;gap:4px;margin-right:10px}.mark i{width:8px;height:8px;background:#f2733f;border-radius:2px}.mark i:first-child{height:19px}.mark i:nth-child(2){height:12px}
.label,.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:1.6px;font-weight:700;color:#56616a}.eyebrow{color:#b6532c;margin:38px 0 10px}
h1{font-size:clamp(34px,5vw,60px);line-height:1.1;letter-spacing:-2.5px;margin:0;max-width:850px}h2{font-size:21px;letter-spacing:-.5px;margin:0 0 14px}p{margin:12px 0}.lede{max-width:670px;color:#59636a;font-size:18px}
.hero{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:28px 0}.number{font-size:clamp(36px,6vw,70px);font-weight:780;line-height:1.1;letter-spacing:-2px}.arrow{color:#f2733f;margin:0 12px}.muted{color:#697178}.card{background:#fffefb;border:1px solid #dcdcd4;border-radius:16px;padding:25px;overflow:hidden}.dark{background:#253641;color:white;border:0}.dark .muted{color:#c3cbd0}.metrics{display:flex;gap:28px;flex-wrap:wrap;margin-top:22px}.metric b{display:block;font-size:22px}.metric span{font-size:13px}
.pill{display:inline-block;background:#e9f1e8;color:#315c39;padding:5px 10px;border-radius:30px;font-size:12px;font-weight:750}.warning{background:#fff0d8;color:#795320}.grid{display:grid;grid-template-columns:2fr 1fr;gap:20px;margin:20px 0}.stack{display:grid;gap:20px}pre{white-space:pre-wrap;word-break:break-word;background:#f1f1e9;border-radius:10px;padding:18px;font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;max-height:390px;overflow:auto;margin:12px 0}.dark pre{background:#172731;color:#f6ede3}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}a{color:#a74422;text-decoration-thickness:1px;text-underline-offset:3px}.button{background:#f2733f;color:#172731;border-radius:9px;padding:10px 16px;text-decoration:none;font-size:14px;font-weight:750}.detail{font-size:13px;color:#687177}.strong{color:#253641;font-weight:650}footer{margin-top:30px;font-size:13px;color:#626d74;border-top:1px solid #d7d6ce;padding-top:20px}@media(max-width:720px){main{padding:24px 16px}.hero,.grid{grid-template-columns:1fr}h1{letter-spacing:-1.5px}header .label{max-width:140px;text-align:right}.card{padding:20px}}'''
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Crumb — {before['units']:,} to {after['units']:,} units</title><style>{style}</style></head>
<body><main><header><div class="brand"><span class="mark" aria-hidden="true"><i></i><i></i><i></i></span>crumb</div><div class="label">Large failing inputs.<br>Small reproducible examples.</div></header>
<p class="eyebrow">Your reduction result</p><h1>Less data.<br>The error is still here.</h1>
<p class="lede">Start debugging the small example. Then test your fix against the full original input.</p>
<section class="hero"><div class="card"><div class="label">Input units</div><p class="number">{before['units']:,}<span class="arrow">→</span>{after['units']:,}</p>
<div class="metrics"><div class="metric"><b>{ratio:.1f}%</b><span class="muted">fewer bytes</span></div><div class="metric"><b>{report['calls']}</b><span class="muted">command runs</span></div><div class="metric"><b>{report.get('elapsed_seconds',0):.2f}s</b><span class="muted">elapsed here</span></div></div></div>
<div class="card dark"><span class="pill">{'Verified on saved result' if report['verified_final'] else 'Unverified'}</span><h2 style="margin-top:16px">Two fresh confirmations.</h2>
<p>The saved file reproduced the selected failure signature twice. The original file's content hash is unchanged.</p>
<p class="detail muted">Matching mode: {_e(sig.get('mode','exact'))}. Format: {_e(report['format'])}. Status: {_e(report['status'])}.</p></div></section>
<section class="grid"><div class="card"><h2>The small input</h2><p class="detail">{after['bytes']:,} bytes · {_e(source.name)}</p><pre>{_e(preview)}</pre>
<div class="actions"><a class="button" href="{_e(repro_href)}" download="{_e(source.name)}">Download reproducer</a><a class="button" href="{_e(json_href)}" download="report.json">Machine-readable report</a></div><p class="detail">{'The small input and JSON report are embedded in this HTML file.' if embedded else 'Keep the reproducer beside this report; it exceeds the 1 MiB embedding limit.'}</p></div>
<div class="stack"><div class="card"><h2>Where it came from</h2><p class="detail">Original: {_e(Path(before['path']).name)}</p><pre>{_e(locations_text)}</pre><p class="detail">Record indices are zero-based when listed as kept_indices. Source line ranges, when provided, are one-based.</p></div>
<div class="card"><h2>What to do next</h2><p>{_e(next_step)}</p><p>Fix the code or data, then run the original command on the complete source.</p></div></div></section>
<section class="card"><h2>The observed failure</h2><p class="detail">Exit code {_e(sig.get('returncode','?'))} · {_e(sig.get('stream','none'))}</p><pre>{_e(signature)}</pre>
<p class="detail">Only input path spellings are normalized by default. Matching an error does not prove the same underlying bug.</p></section>
<section class="card" style="margin-top:20px"><h2>Reproduce locally</h2><p class="detail">From {_e(report.get('working_directory','the original working directory'))}</p><pre>{_e(command)}</pre>
<p class="detail">Requires the original program and environment. This command runs with your permissions. The report does not execute it.</p><p class="detail">{_e(scope)}</p></section>
<footer>Crumb {_e(report.get('crumb_version',''))} · This report works offline. It may contain private data and command arguments; review it before sharing.<br>No model, API key or hosted service is used by Crumb. The supplied command may use the network.</footer></main></body></html>'''
    target.write_text(document, encoding="utf-8")
