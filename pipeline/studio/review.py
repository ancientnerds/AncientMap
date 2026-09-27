"""`episode review`: review.html, the owner's script table (spec 4.3).

One row per beat: time (measured after the voice step, estimated before), chapter, what is
spoken (and the display text when it differs), the picture block, the evidence with its
source and verification, and the checker's findings for that beat.
"""

from __future__ import annotations

import html
from typing import Any

from pipeline.studio.casefile import CaseFile
from pipeline.studio.script import ScriptReport, scene_seconds, speech_seconds

STYLE = """
body{background:#0a0f0a;color:#d8e8d8;font:14px/1.45 'JetBrains Mono',monospace;margin:24px}
h1{font:600 20px Orbitron,sans-serif;color:#00cc66}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #1f3a1f;padding:6px 8px;vertical-align:top}
th{background:#102010;color:#00cc66;text-align:left}
.bad{color:#ff5555}.ok{color:#00cc66}.muted{color:#7a8f7a}
a{color:#66ccff}
"""


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def _evidence_cell(ids: list[str], cf: CaseFile) -> str:
    by_id = {e.id: e for e in cf.evidence}
    parts = []
    for eid in ids:
        e = by_id.get(eid)
        if e is None:
            parts.append(f'<div class="bad">{html.escape(eid)}: not in the case file</div>')
            continue
        cls = "ok" if e.verification.status == "verified" else "bad"
        parts.append(
            f"<div><b>{html.escape(e.id)}</b> {html.escape(e.statement)}<br>"
            f'<a href="{html.escape(e.source.url)}">{html.escape(e.source.title)}</a> '
            f'<span class="{cls}">{html.escape(e.verification.status)}</span></div>'
        )
    return "".join(parts) or '<span class="muted">none</span>'


def render_review(
    script: dict[str, Any], cf: CaseFile, words: dict[str, Any] | None, report: ScriptReport
) -> str:
    timing = "measured" if words is not None else "estimated"
    rows = []
    t = 0.0
    for beat in script["beats"]:
        bid = beat["id"]
        seconds = scene_seconds(beat, speech_seconds(beat, words))
        findings = [e for e in report.errors if e.startswith((f"{bid}:", f"{bid} cue"))]
        status = (
            "".join(f'<div class="bad">{html.escape(f)}</div>' for f in findings)
            or '<span class="ok">ok</span>'
        )
        display = (
            f'<div class="muted">shown: {html.escape(beat["display"])}</div>'
            if beat["display"] != beat["spoken"]
            else ""
        )
        rows.append(
            "<tr>"
            f"<td>{_clock(t)}–{_clock(t + seconds)}</td>"
            f"<td>{html.escape(str(beat.get('chapter', '')))}</td>"
            f"<td>{html.escape(bid)}{' (hook)' if beat.get('hook') else ''}</td>"
            f"<td>{html.escape(beat['spoken'])}{display}</td>"
            f"<td>{html.escape(beat['visual']['block'])}</td>"
            f"<td>{_evidence_cell(beat['evidence'], cf)}</td>"
            f"<td>{status}</td>"
            "</tr>"
        )
        t += seconds
    general = [e for e in report.errors if not any(e.startswith(b["id"]) for b in script["beats"])]
    summary = "".join(f'<li class="bad">{html.escape(e)}</li>' for e in general)
    summary += "".join(f'<li class="muted">{html.escape(d)}</li>' for d in report.deferred)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Review {html.escape(script['episode'])}</title><style>{STYLE}</style></head><body>"
        f"<h1>{html.escape(script['episode'])} · {_clock(t)} ({timing})</h1>"
        f"<ul>{summary}</ul>"
        "<table><tr><th>time</th><th>chapter</th><th>beat</th><th>spoken</th>"
        "<th>picture</th><th>evidence + source</th><th>check</th></tr>"
        + "".join(rows)
        + "</table></body></html>"
    )
