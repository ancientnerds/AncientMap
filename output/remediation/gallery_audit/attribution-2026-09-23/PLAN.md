# Attribution backfill (img-attrib-2026-09-23)

527 curated live CC BY* image(s) without an author, read from production.
77 resolved (133 row change(s) over 53 site(s), 1 chunk(s)); 450 unresolved and listed in UNRESOLVED.jsonl.

| route | rows |
|---|---|
| A1 | 2 |
| A2 | 50 |
| A3 | 25 |
| A4 | 0 |
| unresolved | 450 |

Unresolved, by reason:

| reason | rows |
|---|---|
| -: no route applies: no Artist, no Attribution, no own-work user link, no {{Information}} author | 447 |
| A2: the span carries a replacement character (a broken encoding) | 2 |
| A1: the span carries an HTML entity parse_attribution does not decode | 1 |

## Chunks

| chunk | run stamp | sites | rows |
|---|---|---|---|
| 001 | img-attrib-2026-09-23-001 | 53 | 133 |

Per chunk: `chunk_writer.py <chunk> --check`, `--rehearse`, `--apply` (which reads back),
`--rehearse-rollback`. Before the first apply: `attribution.py --recheck`.
