# Attribution backfill (attribution-2026-11-07)

423 curated live image(s) whose licence asks for an author and that have none, read from production.
73 resolved (146 row change(s) over 57 site(s), 1 chunk(s)); 350 unresolved and listed in UNRESOLVED.jsonl.

| route | rows |
|---|---|
| A1 | 0 |
| A2 | 0 |
| A3 | 0 |
| A4 | 0 |
| A5 | 73 |
| unresolved | 350 |

Unresolved, by reason:

| reason | rows |
|---|---|
| -: no route applies: no Artist, no Attribution, no own-work user link, no {{Information}} author, no {{self}} licence | 339 |
| A2: the link 'https://commons.wikimedia.org/wiki/Main_Page' is a Wikimedia page, not a user page | 3 |
| A2: the span carries a replacement character (a broken encoding) | 2 |
| A3: the own-work credit carries 0 user links, not exactly one | 2 |
| A2: wiki markup, not a name | 2 |
| A1: the span carries an HTML entity parse_attribution does not decode | 1 |
| A5: the first version was uploaded by 'BetacommandBot', a bot account | 1 |

## Chunks

| chunk | run stamp | sites | rows |
|---|---|---|---|
| 001 | attribution-2026-11-07-001 | 57 | 146 |

Per chunk: `chunk_writer.py <chunk> --check`, `--rehearse`, `--apply` (which reads back),
`--rehearse-rollback`. Before the first apply: `attribution.py --recheck`.
