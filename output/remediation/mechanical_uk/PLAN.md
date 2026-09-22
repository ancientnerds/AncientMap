# B9 - the United Kingdom's parts, spelled by region: plan

Built 2026-09-22T21:45:08+00:00 by `scripts/remediation/mechanical/uk_parts.py`. Lane `uk-parts`: run stamp `2026-09-22_mechanical-uk-parts`, journal test id `B9/uk-country-part`, change keys `country-uk-part:<site_id>`, source `ancient_nerds`.

**23 row(s) will be written, 46 are already right, 0 refused.** 5 of the written rows supersede a phase-3 write (`Ireland -> United Kingdom`); their journal row is named in each record's evidence.

| stored value | written value | rows |
|---|---|---|
| `Ireland` | `Northern Ireland` | 17 |
| `United Kingdom` | `England` | 1 |
| `United Kingdom` | `Northern Ireland` | 5 |

## Every row

| site | stored | written | rule | witnesses | phase 3 |
|---|---|---|---|---|---|
| Aghanaglack (`74ea7fff-37dd-46f5-a3ca-2df0fdd65068`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Annaghmare Court Tomb (`3e7d6ad9-37c8-4899-9956-99088ff63c78`) | `Ireland` | `Northern Ireland` | geo-unit | enwiki category |  |
| Audleystown Court Tomb (`c0d78581-207b-4223-bcdf-680bd82bce83`) | `Ireland` | `Northern Ireland` | geo-unit | P17, P131* |  |
| Aughlish (`8f34775c-ca69-41e8-9517-35005cdc21b8`) | `Ireland` | `Northern Ireland` | geo-unit | P17, P131* |  |
| Ballykeel Dolmen (`f4e3fdef-07f1-4327-b0db-c01c671bfafc`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Ballylumford Dolmen (`3dd0bac8-4618-4f61-a2b2-4dd229a76e45`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Ballymacaldrack Court Tomb (`f6b6e039-36f1-4107-b730-dc2aa34b7a92`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Ballynoe Stone Circle (`ac2c74ff-d861-4609-8589-67a8c3eceb3c`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Beaghmore (`782afd80-c3e6-4678-99b0-adc7c3074b7f`) | `Ireland` | `Northern Ireland` | geo-unit | P17, P131* |  |
| Boa Island (`037e3715-f5f7-4345-8216-8aa26f404009`) | `Ireland` | `Northern Ireland` | geo-unit | P17, P131* |  |
| Corick (`a9c41392-165e-46fb-96e4-a9c2ea7ae8f3`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Drumskinny (`aaeff3cd-427c-4c89-83d6-c884495c0380`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Goward Dolmen (`355d25f2-d08d-44d5-8462-0238791d5c92`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Haughey's Fort (`eef7317f-a250-434f-b34d-7933fd546da7`) | `Ireland` | `Northern Ireland` | geo-unit | P17, P131* |  |
| Knockmany Passage Tomb (`ef7d92df-a76b-4c2c-8160-32ad83100a71`) | `Ireland` | `Northern Ireland` | geo-unit | P17 |  |
| Legananny Dolmen (`ec838509-a1e6-4f6a-b216-3f1791c16d67`) | `Ireland` | `Northern Ireland` | geo-unit | P17, P131* |  |
| Tievebulliagh (`fd94d469-92a0-4796-a7a8-64f925f01773`) | `Ireland` | `Northern Ireland` | geo-unit | P17, P131* |  |
| Annadorn Dolmen (`5b541553-60c7-469e-93f2-a0759ea72435`) | `United Kingdom` | `Northern Ireland` | geo-unit | P17 | yes |
| Craigs Dolmen (`fa245dcb-9b81-40b2-b221-b670d983549c`) | `United Kingdom` | `Northern Ireland` | geo-unit | P17 | yes |
| Dooey's Cairn (`f5ca382a-3725-4cbb-961a-6afbf5c21507`) | `United Kingdom` | `Northern Ireland` | geo-unit | P17 | yes |
| Eartham Pit, Boxgrove (`c070b6b0-3fd2-4d6c-acbe-105539188253`) | `United Kingdom` | `England` | geo-unit | P17, P131* |  |
| Giant's Ring (`e0d56737-6459-4329-9ef5-1a46e8d75f10`) | `United Kingdom` | `Northern Ireland` | geo-unit | P17 | yes |
| Moylehid (`0eaedf34-031e-4b8f-8fff-2db84a3e6da6`) | `United Kingdom` | `Northern Ireland` | geo-unit | P17, P131* | yes |

## The checks

See the module docstring of `uk_parts.py` for all fifteen, in order. The mandatory ones:

| check | source | what it proves |
|---|---|---|
| geo unit | naturalearth:ne_10m_admin_0_map_units v5.1.1 (GEOUNIT) | the point lies in that unit, or within 1000 m of it and of no other |
| vocabulary 1 | pipeline/utils/country_lookup.py | the value resolves to GB |
| vocabulary 2 | countryFlags.ts:COUNTRY_CODES | the value is a key with GB: the flag renders |
| fixed point | census T05 predicate | the census would not flag the written value |
| entity point | Wikidata P625 | an independent point lies in the same unit |
| external | Wikidata P17/P131*, enwiki categories | no contradiction; an IE -> GB row needs one positive witness |

## Witness coverage

Of 23 written rows: P17 -> GB 22, P131* -> the unit 9, enwiki category 1 (only for an entity that states neither P17 nor P131). Witnesses collected 2026-09-22T21:44:46+00:00 with the project's User-Agent; the queries are in the cache file.

## Residuals this write leaves (owner decisions, not this lane's)

* `card_stats.civilization` copies `country` and is not written here: the divergence grows by every written row whose card still says the old value (`APPLIED.md` of T05 names the check SQL). Re-running the card generator is the owner's call.
* `/sites/united-kingdom` matches no row after the write and answers 404, like `/sites/georgia-country` since the T05 lane; detail pages 301 to the new country segment.
* Until the vocabulary change (`'Northern Ireland': 'GB'`) is deployed, live pages show the Northern-Irish rows without a flag, under 'Other'.
* Dooey's Cairn and Ballymacaldrack Court Tomb share Wikidata Q1242421 and lie 7.1 m apart (a duplicate pair, B6-type); both get `Northern Ireland` either way.

## Reproduce

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/uk_parts.py --collect
./.venv/Scripts/python.exe scripts/remediation/mechanical/uk_parts.py --write
./.venv/Scripts/python.exe -m pytest tests/remediation/test_mechanical_uk.py -q -rs
```
