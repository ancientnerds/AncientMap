# Census of the curated sites

Snapshot `output\remediation\snapshot`, exported 2026-09-20T20:20:01+02:00 - `5004` sites.

Every site is accounted for in every test: `applicable = pass + flagged`, and
`applicable + not_applicable + errors = sites`. A non-zero `errors` column means
that test's result is unknown, not clean.

## Tests

| test | dimension | sites | applicable | flagged | n/a | errors | findings | applicable findings | s |
|---|---|---|---|---|---|---|---|---|---|
| T03 text years vs period bucket | period / description text | 5004 | 4989 | 873 | 15 | 0 | 873 | 0 | 2.71 |

## Findings by severity, field and proposal

| severity | field | proposal | count |
|---|---|---|---|
| moderate | description | review | 542 |
| severe | description | review | 183 |
| severe | card_description | review | 148 |

## Provenance

Reproducible from the snapshot plus the HTTP cache; no test reads the
database. `applicable findings` carry the evidence their confidence
demands - the rest are proposals for human review.
