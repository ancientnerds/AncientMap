# The residue rung: `period_name` undated - plan

Built 2026-10-04T19:16:40+00:00 by `scripts/remediation/mechanical/residue_period.py`. Lane `period-label-undated-2026-10-04e`: run stamp `2026-10-04e_period-label-undated`, journal test id `period-label/residue`, change keys `period-label-undated-2026-10-04e:<site_id>`, premise `CASE WHEN u.period_start IS NULL THEN 'no period_start' ELSE u.period_start::text END`.

**103 row(s) will be written, 4901 already carry this lane's label, 0 listed.** What this wave does: the rows that carry no year at all get the residue label, and only a NULL or empty label is written (the cell may be filled, never overwritten).

The rule is the owner's (`output/remediation/period_wave/residue_rule.json`, 2026-10-04):

> a curated site that carries no period after the sourced, structured and derived rungs gets
> `period_name = "Undated"` and no year - a visible entry that states the period is not
> established, no year invented, and the card takes no antiquity colour.

| stored period_name | written period_name | rows |
|---|---|---|
| `None` | `Undated` | 103 |

## Every row

| site | period_start | stored | written |
|---|---|---|---|
| Aboriginal Sites of New South Wales (`d7b8c0a6-0e25-4c12-b63e-1e7abd9af00f`) | no period_start | `None` | `Undated` |
| Auga Punta (`2dd6aaa9-95bb-4c96-a3e2-ae7864fb8748`) | no period_start | `None` | `Undated` |
| Auquilohuagra (`2c1c70ac-91df-4577-ac77-3bedd6c521ee`) | no period_start | `None` | `Undated` |
| Awkimarka, Huánuco (`454ecea0-4c69-48a1-8fb3-5e96b53f683c`) | no period_start | `None` | `Undated` |
| Aya Muqu (`134e6d5f-86de-4c3a-afc6-2959a360db15`) | no period_start | `None` | `Undated` |
| Balanced Rock, North Salem (`2fb4a171-fe52-40c9-8bcb-195cd068b55d`) | no period_start | `None` | `Undated` |
| Baltic Sea Anomaly (`c8d2c13e-fd9a-466c-9fdc-fc26ee798ded`) | no period_start | `None` | `Undated` |
| Bela Palanka (`5b27b64f-8c83-4685-8644-8a2076d83322`) | no period_start | `None` | `Undated` |
| Beşkardeşler Kaya Mezarları (`ee94fe5e-d975-4ed9-940d-16056532293e`) | no period_start | `None` | `Undated` |
| Bosnian Pyramid of Love (`8df8659c-49be-4a66-b25a-ecbf96541515`) | no period_start | `None` | `Undated` |
| Bosnian Pyramid of the Moon (`0fd636ac-1a80-4a77-b9d0-a065ae811656`) | no period_start | `None` | `Undated` |
| Bosnian Pyramid of the Sun (`3c466fde-b751-4065-8de2-bd5c9280afe5`) | no period_start | `None` | `Undated` |
| Casteddu di Puzzonu (`86383b38-f1a1-4f04-9b7e-8a49c3495829`) | no period_start | `None` | `Undated` |
| Cave of El Soplao (`f6daed37-710f-4512-a494-bb4ecddd4d2c`) | no period_start | `None` | `Undated` |
| Chaa Creek (`89bdbe2c-a19b-484d-b6ef-2ed464b1311b`) | no period_start | `None` | `Undated` |
| Chichakuri (`e59377f7-18eb-459e-adc4-b9c40274ddfa`) | no period_start | `None` | `Undated` |
| Chipaw Marka (`c4446aa8-4d88-4d40-be5b-129bca6a68aa`) | no period_start | `None` | `Undated` |
| Columbário Fenício (`03ebb1eb-834c-46f9-a038-9231d40f8072`) | no period_start | `None` | `Undated` |
| Currachjaghju (`09b07712-628c-4c14-bf87-62c586f1ced3`) | no period_start | `None` | `Undated` |
| Fort Abbas (`008ecaa5-ce9b-484d-9eb8-0f27659bc91d`) | no period_start | `None` | `Undated` |
| Giants' Graves (`78123025-5f8c-433a-9623-a60ea4105600`) | no period_start | `None` | `Undated` |
| Gritulu (`20f1479a-f1f8-46ce-b3a3-05a71847097e`) | no period_start | `None` | `Undated` |
| Għar il-Kbir (`dd6ec46e-813f-458a-a881-a5673ea8b839`) | no period_start | `None` | `Undated` |
| Hatun Misapata (`706c0a4d-f0ba-4970-8744-176841caae61`) | no period_start | `None` | `Undated` |
| Hatun Usnu (`21d9af3d-9d4e-4df0-beb1-268486146a61`) | no period_start | `None` | `Undated` |
| Hatunmarka (`2968fd35-9b61-4dfb-bb1b-cc4489827fd6`) | no period_start | `None` | `Undated` |
| Henmore Brook (`b67a72ea-cdd7-4feb-9847-aee79adcd9be`) | no period_start | `None` | `Undated` |
| Hoyo Negro Cenote (`82c9fb95-c776-4450-bb5c-93a70fdcb056`) | no period_start | `None` | `Undated` |
| Huankarán (`7e23ac5b-3d28-4004-842a-6d3514ddd5ed`) | no period_start | `None` | `Undated` |
| Huayrapongo (`04f2ddf1-3539-41e4-bea2-e0f1f9fa0476`) | no period_start | `None` | `Undated` |
| Huichún (`2a1d1dfb-474c-44db-a3ea-81758fadf851`) | no period_start | `None` | `Undated` |
| Hundersingen (`80c6aaab-af57-422f-9648-a47c7c51d09b`) | no period_start | `None` | `Undated` |
| Inka Murata (`8590c435-e895-4d7e-9b06-d0f2027c04d7`) | no period_start | `None` | `Undated` |
| Iskuqucha (`1be6202f-f47a-40f8-8b07-9fe22cc95000`) | no period_start | `None` | `Undated` |
| Isog (`28402a1d-9e31-4818-9790-783de876cecd`) | no period_start | `None` | `Undated` |
| Jannusan Burial Mound Field (`48e08ccf-7661-47c1-9a0e-ff9e205530e0`) | no period_start | `None` | `Undated` |
| Kamennyy Gorod (`8459f1d2-a96f-4c37-a1d3-fb4ebbe3fb2e`) | no period_start | `None` | `Undated` |
| Killarumiyoq (`69aaac26-9f4a-47da-beb4-d31ef8d4301f`) | no period_start | `None` | `Undated` |
| Killarumiyuq (`ddc0a0bf-1313-499a-8ec6-77839727afe1`) | no period_start | `None` | `Undated` |
| King Lud's Entrenchments and The Drift (`0b8a8edd-8a60-4758-985c-bf354de4a985`) | no period_start | `None` | `Undated` |
| Kirkdale Cave (`7155aa5a-4eff-4b1d-a105-b15d17b786c6`) | no period_start | `None` | `Undated` |
| Kunturmarka, Ayacucho (`facb2c7f-777a-4eb0-8036-731853847f07`) | no period_start | `None` | `Undated` |
| Kunturmarka, Pasco (`7bcdeff1-fd34-4c0d-a32e-d8f812e64a73`) | no period_start | `None` | `Undated` |
| Lakkos (`0e627b04-0c07-4967-9b94-0967a2eca175`) | no period_start | `None` | `Undated` |
| Llaqta Qulluy, Acoria (`c54e678e-8662-42cd-8875-fc387cc19fad`) | no period_start | `None` | `Undated` |
| Llaqta Qulluy, Tayacaja (`ec64fd4c-0fa2-4932-9a75-6756b90aed5b`) | no period_start | `None` | `Undated` |
| Llaqta Qulluy, Vilca (`bee72fdb-a761-4a79-90ee-9e98d1d5ad75`) | no period_start | `None` | `Undated` |
| Lygourio (`d6d67a37-3efa-44d4-9340-004a07a52ea8`) | no period_start | `None` | `Undated` |
| Mahkeme Ağacin Kültürel Jeositi (`1ac10af9-1ace-4be6-8e02-88dacc77b6c6`) | no period_start | `None` | `Undated` |
| Markansaya (`6098d612-4f78-437a-87cb-739b74f254a4`) | no period_start | `None` | `Undated` |
| Marpa, Peru (`648faca1-d0ae-4830-83f6-54efdf0231fe`) | no period_start | `None` | `Undated` |
| Mawk'allaqta, Sandia (`63b855c8-c281-42d8-87ea-58aeeec070ef`) | no period_start | `None` | `Undated` |
| Megalithic Wall, Gubbio (`a4d1130a-68fb-4acd-8b77-5088ace9a377`) | no period_start | `None` | `Undated` |
| Mirq'imarka (`df891fda-0a06-48a3-a265-97c9b3138d23`) | no period_start | `None` | `Undated` |
| Mookambika Wildlife Sanctuary Kodachadri (`2133d54c-f352-4325-ae0c-dd532f9a65d3`) | no period_start | `None` | `Undated` |
| Mount William Stone Axe Quarry (`bcc037db-7637-44c9-8204-3ce6d4370653`) | no period_start | `None` | `Undated` |
| Mulinuyuq (`c8855169-8cd1-40ae-9f2a-cfc8be715d8b`) | no period_start | `None` | `Undated` |
| Mullu Q'awa (`54e2461b-5a65-4da6-9e73-10b14a813736`) | no period_start | `None` | `Undated` |
| Natural Park Gradistea Muncelului - Cioclovina (`1c573084-c7d7-4072-84c3-30adc4b6c521`) | no period_start | `None` | `Undated` |
| Pagar Alam (`30cf4488-c74c-42d8-8e21-a017ca0bf921`) | no period_start | `None` | `Undated` |
| Paraccra Archaeological Site (`e1c3365d-f89e-468e-a928-8e5db1210844`) | no period_start | `None` | `Undated` |
| Península de Kola (`7bbee517-515c-4fe4-9271-036ea36791e1`) | no period_start | `None` | `Undated` |
| Pirca Pirca, La Libertad (`db9e04a9-afe5-4541-8ae4-0d7c5b14facc`) | no period_start | `None` | `Undated` |
| Popping Stone (`b89bd9e5-053b-4d85-a2a9-1f79a6c3b452`) | no period_start | `None` | `Undated` |
| Prebreza (`182f18fe-36ea-42c8-9a43-cbbc37d052a6`) | no period_start | `None` | `Undated` |
| Puka Urqu, Ayacucho (`0f32e3d9-176a-4860-afcf-3994d049b1b1`) | no period_start | `None` | `Undated` |
| Pukara, Coporaque (`64137ead-762b-4621-a59c-5c7395ef4826`) | no period_start | `None` | `Undated` |
| Pukara, Vilcas Huamán (`d1fd88e8-1e77-4bc2-859e-d72632d37500`) | no period_start | `None` | `Undated` |
| Pukara, Víctor Fajardo (`faf8f8ee-c092-48a8-a712-1133df65badd`) | no period_start | `None` | `Undated` |
| Pumamarka, San Sebastián (`58486903-37c4-4aa4-866f-f7f8d66205ac`) | no period_start | `None` | `Undated` |
| Puntay Urqu (`99328522-518c-40cd-94a1-b541906c3f00`) | no period_start | `None` | `Undated` |
| Puqin Kancha (`bc13a236-675e-46b4-8cb1-b5e86d9fbd97`) | no period_start | `None` | `Undated` |
| Purunllacta, Soloco (`ba2e3e1a-f3d0-4c41-9508-946ceced696a`) | no period_start | `None` | `Undated` |
| Q'asa Pata (`7959bac1-48f2-4648-b9fa-7b23847cd894`) | no period_start | `None` | `Undated` |
| Quishuar Archaeological Site (`517e41aa-be07-4b3b-9b44-1a6a77de304e`) | no period_start | `None` | `Undated` |
| Richat Structure (`84b456ff-0b44-4d75-92a4-5cbe22026b95`) | no period_start | `None` | `Undated` |
| Rock City (`d8888428-c233-4936-b1c4-7bfc8c4d5bed`) | no period_start | `None` | `Undated` |
| Rocks of Saskatchewan (`74c2c902-db56-411f-b98f-6711a6825b48`) | no period_start | `None` | `Undated` |
| Rodadero Slides (`ece7f01a-17bf-4b09-afc9-8368b323a88b`) | no period_start | `None` | `Undated` |
| Ruthergate (`82a98ba6-5bd5-4a0c-8170-5ac93df1a89b`) | no period_start | `None` | `Undated` |
| Singing Stones of Brittany (`045f1593-1dac-4504-9c53-ee8644a3134c`) | no period_start | `None` | `Undated` |
| Susupillo (`37d8c068-dfb3-4fc5-a99e-a09c4aad18d3`) | no period_start | `None` | `Undated` |
| Tahai Ceremonial Complex (`d972a5b7-866c-48d6-af54-d9ac91f00b0b`) | no period_start | `None` | `Undated` |
| Temple of Lemminkäinen (`79898fb7-ea09-4366-93ee-d87e379e1aca`) | no period_start | `None` | `Undated` |
| Templebryan Stone Circle (`c4bb47e2-6e2e-49e6-a17b-e9c2ad9c9129`) | no period_start | `None` | `Undated` |
| Tipu (`f42a2997-d354-48b1-99b5-1a38cef7d01c`) | no period_start | `None` | `Undated` |
| Titiqaqa, Cusco (`bb312418-3990-4a2a-86a3-5f3bc9c1c7b2`) | no period_start | `None` | `Undated` |
| Tupu Inka (`723dad90-4cd2-42ca-a8d1-9cf8fe11f1f0`) | no period_start | `None` | `Undated` |
| Usnu Muqu (`f057c595-7ea4-42ce-bf5d-734fad5a1e47`) | no period_start | `None` | `Undated` |
| Usqunta (`97e6920e-fb90-41d1-9e6c-38a76029e782`) | no period_start | `None` | `Undated` |
| Velika Humka (`46be23ba-b785-4a9f-bcd7-c98b01ff445f`) | no period_start | `None` | `Undated` |
| Waman Pirqa (`ddbaa0c7-7d30-45fa-ab80-71b0d49d8dec`) | no period_start | `None` | `Undated` |
| Wamanilla (`5169991f-862a-451b-b76f-9a49a8bc5f8b`) | no period_start | `None` | `Undated` |
| Waqutu (`84e58c4d-9c61-4454-b165-041371c9b2c1`) | no period_start | `None` | `Undated` |
| Waruq (`6dfdc2fb-802e-4193-b9c9-15684d50bea8`) | no period_start | `None` | `Undated` |
| Wat'a, Cusco (`0a6e70ea-022a-4035-a866-0e54efff533d`) | no period_start | `None` | `Undated` |
| Wilca (`47396b3b-88aa-4d18-a7ac-8bec4154c19d`) | no period_start | `None` | `Undated` |
| Yonaguni Monument (`01296632-a2a1-4610-a4a9-d0c3be77b788`) | no period_start | `None` | `Undated` |
| Ñawpallaqta, Fajardo (`2a7e3b61-6a76-4f1a-8c4a-e0d895a129a5`) | no period_start | `None` | `Undated` |
| Ñawpallaqta, Huanca Sancos (`9f5cf21d-173d-4387-bbf7-ac5b06ee134b`) | no period_start | `None` | `Undated` |
| Ñawpallaqta, Lucanas (`b54d2d6a-d3d4-442e-9cf4-1ddd1bf1073e`) | no period_start | `None` | `Undated` |
| Ñusta Hispana (`dafc7527-c6c8-45c3-8c7d-4813d20a4dcf`) | no period_start | `None` | `Undated` |
| Ġebel ġol-Baħar (`83d0776b-8f10-4009-85f3-842a03cb9c30`) | no period_start | `None` | `Undated` |

## What a reader must know afterwards

* The card generator reads `period_name` for `card_stats.mystery` and the rarity, so a card_stats wave follows this one (runbook 4.6 step 14); the `antiquity` stat reads `period_start` and is unchanged, because a row with no year already took its default.
* The frontend labels a site with `period_name` and colours it from `period_start`, so `Undated` shows as a grey badge with no antiquity colour - which is the rule's `why`.
* Qdrant's change hash includes `period_name`; the next nightly sync picks these rows up.

## Reproduce

```bash
./.venv/Scripts/python.exe scripts/remediation/mechanical/residue_period.py --wave 2026-10-04e --scope undated --write
./.venv/Scripts/python.exe -m pytest tests/remediation/test_residue_period.py -q -rs
```
