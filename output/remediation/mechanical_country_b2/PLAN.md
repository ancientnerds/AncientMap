# B2-L - the two decided country cells: plan

Built 2026-09-26T00:31:04+00:00 by `scripts/remediation/mechanical/country_b2.py`. Lane `country-b2`, run stamp `2026-09-26_mechanical-country-b2`, journal test id `B2/country`. Decision: `output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md`, B2-L (O9, 2026-09-26). Witnesses: Wikidata, 2026-09-26T00:30:06+00:00, User-Agent `AncientMapRemediation/1.0 (research)`.

**2 row(s) will be written, 0 refused.**

| site | stored | written | premise (the stored point) |
|---|---|---|---|
| Delphinion (`6aa4c8de-3794-42fe-b68e-6b6ab77bd8ed`) | `Greece` | `Türkiye` | `37.53012087208033,27.280715854142734` |
| Achladia (`74145e9b-76a6-48de-a902-08ecb2f1f7bb`) | `Germany` | `Greece` | `35.16680700239597,26.050032182871053` |

## Evidence per row

* **Delphinion**
  * output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md: B2-L: Delphinion Greece -> Türkiye (O9, 2026-09-26)
  * naturalearth:ne_10m_admin_0_countries (Turkey): point (37.53012, 27.28072) inside the 'Türkiye' polygon
* **Achladia**
  * output/remediation/HUMAN_ONLY_DECISIONS_2026-09-26.md: B2-L: Achladia Germany -> Greece (O9, 2026-09-26)
  * naturalearth:ne_10m_admin_0_countries (Greece): point (35.16681, 26.05003) inside the 'Greece' polygon
  * wikidata:Q28791168:P17 -> Q41:P297: Q28791168 P17 only: Q41 Greece (GR) -> ISO 3166-1 alpha-2 GR ('Greece'); anchor via site_external_ids:wikidata_qid
  * wikidata:Q28791168:P625: Q28791168 P625 (35.1692, 26.0719) lies in Greece, 2005 m from the stored point

## Run it (the orchestrator's job, in this order)

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/mechanical/country_b2.py --collect   # read-only + Wikidata
$PY scripts/remediation/mechanical/country_b2.py --write     # read-only
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --emit
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --rehearse
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --probe-guards
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --apply
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --verify
$PY scripts/remediation/mechanical/apply.py --lane country-b2 --rehearse-rollback
```
