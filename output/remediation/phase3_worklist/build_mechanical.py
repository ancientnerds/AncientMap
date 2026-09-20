"""Emit MECHANICAL.md: the factual-flagged sites a script can settle (T05 set), read-only."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
recs = [
    json.loads(line)
    for line in (OUT / "WORKLIST.jsonl").open(encoding="utf-8")
    if line.strip()
]
mech = sorted(
    (r for r in recs if r["mechanically_settable"] and not r["phase3"]),
    key=lambda x: x["name"] or "",
)
rows = []
for r in mech:
    deps = "; ".join(
        f"`{f['current_value']}` -> `{f['proposed_value']}`"
        for f in r["findings"]
        if f["applicable"]
    )
    rows.append(f"| {r['name']} | {r['site_id']} | {deps} |")

body = (
    "# Mechanically settable factual findings (27 sites)\n\n"
    "These T05 sites carry only `proposal=set` / `confidence=authoritative` findings\n"
    "(`applicable=true`). A script applies them with a conditional `WHERE country = '<old>'`\n"
    "and a journal entry. **Not Phase 3, not LLM work.**\n\n"
    "| Site | site_id | change |\n|---|---|---|\n" + "\n".join(rows) + "\n"
)
(OUT / "MECHANICAL.md").write_text(body, encoding="utf-8")
print(f"wrote {len(rows)} rows")
