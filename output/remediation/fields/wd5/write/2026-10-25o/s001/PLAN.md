# WD5 fields-wd5-2026-10-25o-s001: plan

Built 2026-10-25T07:32:58+00:00 by `scripts/remediation/fields/plan.py`. Run stamp `2026-10-25o_fields-wd5-s001`, test id `WD5/structured-fields`, change keys `fields-wd5-2026-10-25o-s001:<site>:<column>`.

| counter | value |
|---|---|
| sites | 25 |
| cells | 2 |
| sites_written | 1 |
| refused | 24 |
| cells:period_name | 1 |
| cells:period_start | 1 |
| refused:moved-since-classification | 24 |

## Cells

| site | column | old | new | rule |
|---|---|---|---|---|
| Shypyntsi | period_name | `Undated` | `< 4500 BC` | wd5-derive-period-name |
| Shypyntsi | period_start | `NULL` | `-5000` | wd5-replace |

## Refused

| site | column | reason | note |
|---|---|---|---|
| Dumat al-Jandal Wall | period_start | `moved-since-classification` | decided about None, holds -400 |
| Castallack Round | period_start | `moved-since-classification` | decided about None, holds -100 |
| Tomba dei Giganti e Nuraghe Imbertighe | period_start | `moved-since-classification` | decided about None, holds -2000 |
| Dolmen of Carapito I | period_start | `moved-since-classification` | decided about None, holds -3998 |
| Caer Bach | period_start | `moved-since-classification` | decided about None, holds -800 |
| Brown Willy Cairns | period_start | `moved-since-classification` | decided about None, holds -2500 |
| Scholes Coppice | period_start | `moved-since-classification` | decided about None, holds -800 |
| Oddendale Stone Circle | period_start | `moved-since-classification` | decided about None, holds -2500 |
| Lauriacum | period_start | `moved-since-classification` | decided about None, holds 1 |
| Carn Menyn | period_start | `moved-since-classification` | decided about None, holds -7000 |
| Padderbury Top | period_start | `moved-since-classification` | decided about None, holds -800 |
| Abbatija Tad-Dejr Hypogeal Complex | period_start | `moved-since-classification` | decided about None, holds 330 |
| Antik Barajı | period_start | `moved-since-classification` | decided about None, holds 1 |
| Olympe | period_start | `moved-since-classification` | decided about None, holds -700 |
| Camboglanna | period_start | `moved-since-classification` | decided about None, holds 101 |
| La Noce de Pierres | period_start | `moved-since-classification` | decided about None, holds -4000 |
| Acumincum | period_start | `moved-since-classification` | decided about None, holds -1600 |
| Nine Stones, Altarnun | period_start | `moved-since-classification` | decided about None, holds -2500 |
| Allahdino | period_start | `moved-since-classification` | decided about None, holds -2600 |
| Verziau of Gargantua | period_start | `moved-since-classification` | decided about None, holds -4000 |
| Fernacre | period_start | `moved-since-classification` | decided about None, holds -2500 |
| Tomb of the Scene | period_start | `moved-since-classification` | decided about None, holds -485 |
| Carnedd y Saeson and Neighbouring Cairns North-West of Foel Dduarth | period_start | `moved-since-classification` | decided about None, holds -2500 |
| Calcaria | period_start | `moved-since-classification` | decided about None, holds 43 |

## Undo

`ROLLBACK.sql` restores every old value under the stamp `2026-10-25o_fields-wd5-s001-rollback`; rehearse it with `apply.py --lane fields-wd5-2026-10-25o-s001 --rehearse-rollback`, run it deliberately with `psql < ROLLBACK.sql`.
