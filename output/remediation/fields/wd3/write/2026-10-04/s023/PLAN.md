# WD3 fields-wd3-2026-10-04-s023: plan

Built 2026-10-04T13:49:36+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-04_fields-wd3-s023`, test id `WD3/structured-fields`, change keys `fields-wd3-2026-10-04-s023:<site>:<column>`.

| counter | value |
|---|---|
| sites | 14 |
| cells | 18 |
| sites_written | 9 |
| refused | 9 |
| cells:period_name | 9 |
| cells:period_start | 9 |
| refused:coordinates-unresolved | 1 |
| refused:field-unresolved | 1 |
| refused:moved-since-classification | 7 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Barcelona | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Barcelona | period_start | `NULL` | `-500` | wd3-replace |
| Cardiccia | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Cardiccia | period_start | `NULL` | `-4000` | wd3-replace |
| Casterley Camp | period_name | `NULL` | `1500 - 500 BC` | wd3-derive-period-name |
| Casterley Camp | period_start | `NULL` | `-800` | wd3-replace |
| Five Marys | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Five Marys | period_start | `NULL` | `-4000` | wd3-replace |
| Foel Chwern | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Foel Chwern | period_start | `NULL` | `-4000` | wd3-replace |
| Kanichi | period_name | `NULL` | `500 - 1000 AD` | wd3-derive-period-name |
| Kanichi | period_start | `NULL` | `500` | wd3-replace |
| Leskernick Hill | period_name | `NULL` | `4500 - 3000 BC` | wd3-derive-period-name |
| Leskernick Hill | period_start | `NULL` | `-4500` | wd3-replace |
| Pumaq Hirka | period_name | `NULL` | `1 - 500 AD` | wd3-derive-period-name |
| Pumaq Hirka | period_start | `NULL` | `1` | wd3-replace |
| Roman Emperors Route | period_name | `NULL` | `500 BC - 1 AD` | wd3-derive-period-name |
| Roman Emperors Route | period_start | `NULL` | `-500` | wd3-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Herculaneum | period_start | `moved-since-classification` | decided about None, holds -700 |
| Roman Emperors Route | lat | `coordinates-unresolved` | Wikidata item Q7361956 carries no coordinate statement and the English article gives none. The Roman Emperors Route is ' |
| Roman Emperors Route | site_type | `field-unresolved` | The sources call it a tourism and archaeology project and an instance of scenic route, a modern itinerary of separate Ro |
| Kanichi | site_type | `moved-since-classification` | decided about None, holds 'Archaeological site' |
| Pumaq Hirka | site_type | `moved-since-classification` | decided about None, holds 'Archaeological site' |
| Cromlech de Mzoura | period_start | `moved-since-classification` | decided about None, holds -400 |
| Roman Villa of Outeiro de Polima | period_start | `moved-since-classification` | decided about None, holds -100 |
| Orchomenus, Boeotia | period_start | `moved-since-classification` | decided about None, holds -6000 |
| Woolsbarrow Hillfort | period_start | `moved-since-classification` | decided about None, holds -800 |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-04_fields-wd3-s023-rollback`; rehearse it with `apply.py --lane fields-wd3-2026-10-04-s023 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
