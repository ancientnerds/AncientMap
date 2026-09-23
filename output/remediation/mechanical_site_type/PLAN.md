# Phase 6 item 1 - site_type values that are not site types: plan

Built 2026-09-22T22:28:06+00:00 by `scripts/remediation/mechanical/site_type_shape.py`. Lane `site-type-shape`: run stamp `2026-09-22_mechanical-site-type-shape`, journal test id `P6/site-type-shape`, change keys `site-type-shape:<site_id>`.

**3 row(s) will be restored to the value phase 3 replaced, 1 refused, 4 left for a vocabulary decision** (`REVIEW.md`). The lane restores; it does not judge whether the restored type is the best one.

| site | written by phase 3 | restored | shape |
|---|---|---|---|
| Library of Ashurbanipal (`bad314d6-47c3-457f-ab77-9600fe9b04d2`) | `suspect_modern` | `Monument` | restore-marker-token |
| Treasure of Osztrópataka (`99a98235-4cba-484b-b179-c3e34ed89908`) | `Grave (burial site) — not representable` | `Necropolis/tombs complex` | restore-model-refusal |
| Witham Shield (`c5c5f2da-a5ea-41c6-807d-4c8ad7af03ba`) | `suspect_modern` | `City/town/settlement` | restore-marker-token |

## Refused (see `REVIEW.md`)

| site | value | reason |
|---|---|---|
| Mookambika Wildlife Sanctuary Kodachadri | `suspect_modern` | `no-journal-row` |

## Reproduce

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/site_type_shape.py --write
./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_site_type.py -q -rs
```
