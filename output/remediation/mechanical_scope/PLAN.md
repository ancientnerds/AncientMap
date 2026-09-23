# E4 scope lane - plan

Built 2026-09-23T04:45:27+00:00 by `scripts/remediation/mechanical/scope.py` from the production export of 2026-09-23 04:13:08.925379+00. Lane `scope-e4`: run stamp `2026-09-23_mechanical-scope-e4`, journal test id `E4/scope-status`, change keys `scope-e4:<site_id>:<column>`, premise `concat_ws(' | ', coalesce(u.period_start::text, 'NULL'), coalesce(u.period_end::text, 'NULL'), u.lat::text, u.lon::text, coalesce(u.site_type, 'NULL'), u.name)`.

**98 site(s), 196 cell(s): 62 retired, 19 pending, 17 in_scope; 0 refused.** T11 found 95 site(s); 101 curated pair(s) within 100 m share a Wikidata item, 3 of them under two of its names.

| rule | status | sites |
|---|---|---|
| (a) outside the E3 window by the current period_start | pending | 8 |
| (a) outside the E3 window by the current period_start | retired | 54 |
| (b) no date | pending | 11 |
| (b) no date | retired | 2 |
| (c) true duplicates | retired | 3 |
| (d) Museum rows (plan section 8.2) | in_scope | 17 |
| (d) Museum rows (plan section 8.2) | retired | 3 |

The per-site decisions and their evidence are in `REVIEW.md`; the hand-reviewed entries in
`DECISIONS.json`. Reproduce:

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/scope.py --export --collect
./.venv/Scripts/python.exe scripts/remediation/mechanical/scope.py --write
./.venv/Scripts/python.exe scripts/remediation/mechanical/apply.py --lane scope-e4 --emit
```
