# The residue rung: `period_name` bucket - plan

Built 2026-10-04T19:12:54+00:00 by `scripts/remediation/mechanical/residue_period.py`. Lane `period-label-bucket-2026-10-04d`: run stamp `2026-10-04d_period-label-bucket`, journal test id `period-label/residue`, change keys `period-label-bucket-2026-10-04d:<site_id>`, premise `u.period_start::text`.

**1 row(s) will be written, 4900 already carry this lane's label, 103 listed.** What this wave does: the rows whose label contradicts the year they sit on get the bucket of that year.

The rule is the owner's (`output/remediation/period_wave/residue_rule.json`, 2026-10-04):

> a curated site that carries no period after the sourced, structured and derived rungs gets
> `period_name = "Undated"` and no year - a visible entry that states the period is not
> established, no year invented, and the card takes no antiquity colour.

| stored period_name | written period_name | rows |
|---|---|---|
| `1 - 500 AD` | `500 - 1000 AD` | 1 |

## Every row

| site | period_start | stored | written |
|---|---|---|---|
| Prambanan Temple (`21bd525e-fe10-40dd-96be-32d3c8d36d26`) | 850 | `1 - 500 AD` | `500 - 1000 AD` |

## Not written by this wave

| site | reason | note |
|---|---|---|
| Fort Abbas | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Yonaguni Monument | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Columbário Fenício | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Singing Stones of Brittany | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Huayrapongo | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Currachjaghju | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Wat'a, Cusco | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| King Lud's Entrenchments and The Drift | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Lakkos | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Puka Urqu, Ayacucho | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Bosnian Pyramid of the Moon | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Aya Muqu | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Prebreza | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Mahkeme Ağacin Kültürel Jeositi | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Iskuqucha | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Natural Park Gradistea Muncelului - Cioclovina | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Gritulu | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Mookambika Wildlife Sanctuary Kodachadri | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Hatun Usnu | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Isog | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Hatunmarka | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Huichún | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Ñawpallaqta, Fajardo | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Auquilohuagra | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Auga Punta | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Balanced Rock, North Salem | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Pagar Alam | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Susupillo | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Bosnian Pyramid of the Sun | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Awkimarka, Huánuco | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Velika Humka | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Wilca | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Jannusan Burial Mound Field | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Wamanilla | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Quishuar Archaeological Site | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Mullu Q'awa | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Pumamarka, San Sebastián | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Bela Palanka | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Markansaya | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Mawk'allaqta, Sandia | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Pukara, Coporaque | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Marpa, Peru | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Killarumiyoq | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Waruq | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Hatun Misapata | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Kirkdale Cave | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Tupu Inka | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Rocks of Saskatchewan | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Giants' Graves | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Q'asa Pata | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Temple of Lemminkäinen | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Península de Kola | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Kunturmarka, Pasco | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Huankarán | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Hundersingen | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Ruthergate | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Hoyo Negro Cenote | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Ġebel ġol-Baħar | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Kamennyy Gorod | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Richat Structure | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Waqutu | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Inka Murata | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Casteddu di Puzzonu | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Chaa Creek | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Bosnian Pyramid of Love | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Usqunta | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Puntay Urqu | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Ñawpallaqta, Huanca Sancos | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Megalithic Wall, Gubbio | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Ñawpallaqta, Lucanas | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Henmore Brook | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Popping Stone | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Purunllacta, Soloco | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Titiqaqa, Cusco | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Puqin Kancha | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Mount William Stone Axe Quarry | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Llaqta Qulluy, Vilca | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Chipaw Marka | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Templebryan Stone Circle | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Llaqta Qulluy, Acoria | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Mulinuyuq | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Baltic Sea Anomaly | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Pukara, Vilcas Huamán | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Lygourio | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Aboriginal Sites of New South Wales | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Rock City | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Tahai Ceremonial Complex | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Ñusta Hispana | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Pirca Pirca, La Libertad | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Għar il-Kbir | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Waman Pirqa | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Killarumiyuq | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Mirq'imarka | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Paraccra Archaeological Site | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Chichakuri | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Llaqta Qulluy, Tayacaja | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Rodadero Slides | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Beşkardeşler Kaya Mezarları | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Usnu Muqu | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Tipu | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Cave of El Soplao | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Kunturmarka, Ayacucho | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |
| Pukara, Víctor Fajardo | `not-this-lane` | no year: the residue label is the `undated` lane's write, not this lane's |

## What a reader must know afterwards

* The card generator reads `period_name` for `card_stats.mystery` and the rarity, so a card_stats wave follows this one (runbook 4.6 step 14); the `antiquity` stat reads `period_start` and is unchanged, because a row with no year already took its default.
* The frontend labels a site with `period_name` and colours it from `period_start`, so `Undated` shows as a grey badge with no antiquity colour - which is the rule's `why`.
* Qdrant's change hash includes `period_name`; the next nightly sync picks these rows up.

## Reproduce

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/residue_period.py --wave 2026-10-04d --scope bucket --write
./.venv/Scripts/python.exe -m pytest tests/remediation/test_residue_period.py -q -rs
```
