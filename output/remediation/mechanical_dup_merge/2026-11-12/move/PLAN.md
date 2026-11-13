# D14 duplicate merge `dup-merge-move-2026-11-12`: plan

Built 2026-11-12T11:38:33+00:00 by `scripts/remediation/mechanical/dup_merge.py` from the read-only production read of 2026-11-12 11:32:28.917941+00 (`READ.jsonl`). Lane `dup-merge-move-2026-11-12`: run stamp `2026-11-12_mechanical-dup-merge-move`, journal test id `D14/dup-merge-move`, premise `u.name || ' | ' || coalesce((SELECT string_agg(e.kind || '=' || e.value, ', ' ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = u.id), '') || ' | ' || coalesce(u.scope_status, 'NULL') || ' | ' || coalesce(u.scope_reason, 'NULL') || ' | survivor ' || coalesce((SELECT s.name || ' | ' || coalesce((SELECT string_agg(e.kind || '=' || e.value, ', ' ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = s.id), '') FROM unified_sites s WHERE CAST(s.id AS text) = CASE CAST(u.id AS text) WHEN 'ddc0a0bf-1313-499a-8ec6-77839727afe1' THEN '69aaac26-9f4a-47da-beb4-d31ef8d4301f' WHEN '37008e3f-056c-43dc-81c2-74904cacdb4e' THEN 'a50cf939-77f1-489c-82f7-93b07b2bc5ae' WHEN '63d4e2b3-4dad-438d-be14-34bd79cf9842' THEN 'bf0d9250-fe2f-4f04-9dc7-28bcbfd6da20' WHEN '1758f6e8-4518-43fb-a14a-1ce52caca683' THEN '4200b0d7-2aae-4e07-acf3-a342b0c468ac' WHEN '0abaf157-35d2-478f-8b19-c142f67aa8c7' THEN '1c93058e-d647-4f04-8aba-297c20ad41f2' WHEN 'a2ddd76f-1c37-4ac9-971b-d9682384141d' THEN '03d63367-fb7a-4014-b1db-a704e99a10f3' WHEN '0d7c325a-5370-4a95-b048-8e599f69892c' THEN '9ba7c034-6aec-492e-b66e-4541ce3c987c' WHEN '7814f888-d384-442b-8b6b-72c1b209d1d5' THEN '56836aa2-1680-43fb-aeef-1edcc33e2c91' WHEN '1a76bfc9-7056-4848-ac12-d24016a923bb' THEN 'fe61c9c4-97dc-4478-93f8-5cd4a44d8ec2' WHEN '3bb2d9e1-7e77-4582-8b28-92ab27133a9a' THEN 'b319970d-efcd-4f5c-9d9b-55535771676b' WHEN '434c9060-4b58-46a0-94f4-63a85b7133b9' THEN 'efe2bc83-83cc-4393-b725-a18543dc9d5f' WHEN '5d8a914c-d69d-409c-9713-588113811da5' THEN '3911fbf9-3c1c-4620-a197-10ccbb9e20f7' WHEN '58d2d752-30cc-4f22-b2d5-ff27a4b395d1' THEN '13bdea38-cb6c-4c6b-85cb-402a31427819' WHEN '2048dfe4-9b29-494f-8807-881c71023f22' THEN 'b9fdfd6f-b222-4c64-9953-b04fef1f55aa' WHEN '3b7fc9a8-a685-4e5b-9ae7-df7a0d530d2e' THEN '3c47ded2-01b0-4789-bf6e-defb171ddd43' WHEN 'ab077874-2a7f-4add-adec-8cb42e9e9561' THEN '47eb07cd-5c1c-4c0e-88c0-484d3b3411a1' WHEN '0144891e-136b-40fb-87ec-26f618e36365' THEN '15e95e05-6fb3-4779-bbcd-375cd2f031e0' WHEN '1706b1bf-6c89-4f31-a925-e5e679884794' THEN '53a9ddce-054f-4471-94fd-6243611ae0a8' WHEN '774a99e0-e8f7-4881-aa6e-94462da0c52d' THEN 'a07daa54-5e5d-48c7-a95f-097ce085c9fb' WHEN 'f5df832e-ab5e-4e9c-b6c9-037441011945' THEN 'd4714397-6e73-432d-add3-c01e22cb055f' WHEN 'ca33a292-b102-4efe-b644-48959d8ff741' THEN '9031494a-4710-430f-975c-18c9a5990592' WHEN 'c73b6ca5-aa7d-4737-af90-1e6cbab06ff5' THEN '3f27e34a-1817-4b2b-bc19-c3c17a7e6374' WHEN '9bf829da-096e-41c6-b175-f3436c1ce18c' THEN 'a5232aa9-627c-444a-8ac7-82c5b79c3f2d' WHEN '2fc65539-6b0f-4073-9db3-76dadc408cc8' THEN 'd47439dd-6349-4633-bf0b-eb97094ac743' WHEN 'dcda1568-0730-4cba-a9ce-c50c80ed941d' THEN '0999c397-1333-4ff3-aa26-fe854f46de9c' WHEN '8107d407-8094-4f0b-b459-54b2a43e1864' THEN 'ced822e8-13cd-49db-9011-808dc23aac45' WHEN '5dd5ecd6-2cd4-4e37-ae35-51da8f716d07' THEN '1bc57ad9-041a-42de-b0a1-c361a7beb531' WHEN '41070db5-8f7c-4d69-8652-cc2d4bfb8bf4' THEN '5a2e082b-8ed8-4116-b5c3-5414826f0d92' WHEN '9910d3da-4875-49eb-8da4-3f2db69a48a6' THEN '5a2e082b-8ed8-4116-b5c3-5414826f0d92' WHEN '04d8ce82-4fa3-4e48-88b7-bb41b354260c' THEN '00f522ff-8e1b-4983-961c-ef6cb1ff27d1' WHEN '07fb4e2f-26e5-4720-a949-9c28d4712e11' THEN '9152beea-f7ab-40ef-a692-ef63ac8e9ca6' WHEN '13c3f25f-3887-49c1-9492-cf7e512e5782' THEN '13120650-2e61-45af-976c-b2e0665c49af' WHEN '24676ed3-9308-42d4-bf35-1c739f0652e2' THEN '9d9d94a0-f338-4392-860f-983c29fabb16' WHEN '3ebb514f-ac4a-4913-b54b-409bcc29eff4' THEN '51daf6c9-25d3-4818-8857-0543f1203c57' WHEN '4687a49a-c987-4c56-bc6e-5094aa57667d' THEN 'c6d9487d-d138-4d73-beb1-5735e50da048' WHEN '4a5a324f-832f-4dca-b688-d4a006d297c7' THEN '318414bc-098b-4459-95c0-41e1ec49c8a8' WHEN '4e6247b0-7416-413f-b7a3-b31890a45f3b' THEN '4a9b3802-1067-4f6b-a144-4c2ffe9619a4' WHEN '55a670ec-c7c5-4f52-98ea-b25211aedd4e' THEN '47c37ef9-98ee-41d8-879b-e78db06295da' WHEN '577b13cd-242b-4951-a8c4-ab3ecde0e5b1' THEN '23576019-c749-4ee9-95b1-cdae21f5ff06' WHEN '5a04d6f3-c82d-4c82-b1e9-3d70bff135ae' THEN '56f594fc-6819-4d51-98a4-1cf5b4a265a6' WHEN '7e33b1ac-bb32-4b6c-b070-2c4fdcaf19fb' THEN '109fcdea-c114-4143-87ac-77c4c9c20f16' WHEN '8cecb38f-08cf-4a93-b350-9ccbb74109bb' THEN '5025eee3-28ea-46d6-b2c3-dbb1f38a24d6' WHEN '93391ee6-8e80-42db-922c-11f64ea57db9' THEN '84ef64f3-394a-4b35-ba4a-7e81b3b6a317' WHEN 'ab03fa75-bbdc-46a2-ba55-25e2f5edd5c4' THEN '485c3c0c-31f0-45a7-a06b-797c4c021466' WHEN 'ae2ca7b1-89da-46cb-8924-f9d04dd5da2e' THEN 'ce7db300-8777-425d-917a-2f6d9f325b58' WHEN 'b46b6969-3160-4cbd-a574-8727ee7c53c5' THEN '891ad351-7985-4c16-b6a6-830c26bc268f' WHEN 'cf49332c-0a05-4ba7-bf4f-48a703ee7a1e' THEN '577f2ec4-3dc0-4d10-9425-39f1cb654009' WHEN 'd120ca9a-703b-49e2-b333-ad6dfe508953' THEN '9983bdce-9f35-47a3-a570-4021cfa41b97' WHEN 'dafc7527-c6c8-45c3-8c7d-4813d20a4dcf' THEN 'd41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d' WHEN 'f23a31c3-6833-4df6-8583-3b3930b5a74f' THEN '21ac323f-7214-4891-9499-74e55c3d7d56' END), '')`.

Counters: sites 31, cells 177, pairs 31, images 52, images_stay 293, images_stay_filename 3, heroes_demoted 3, links 76, links_stay 20, names 23

| loser | survivor | pair limit (m) | already retired |
|---|---|---|---|
| Killarumiyuq (`ddc0a0bf-1313-499a-8ec6-77839727afe1`) | Killarumiyoq (`69aaac26-9f4a-47da-beb4-d31ef8d4301f`) | 2000 | False |
| Obelisk of Ark (`37008e3f-056c-43dc-81c2-74904cacdb4e`) | Obelisk of Axum (`a50cf939-77f1-489c-82f7-93b07b2bc5ae`) | 2000 | False |
| Roman City Ruins of Salona (`63d4e2b3-4dad-438d-be14-34bd79cf9842`) | Salona (`bf0d9250-fe2f-4f04-9dc7-28bcbfd6da20`) | 2000 | False |
| Dolmen del prado de Lácara (`1758f6e8-4518-43fb-a14a-1ce52caca683`) | Dolmen de Lácara (`4200b0d7-2aae-4e07-acf3-a342b0c468ac`) | 2000 | False |
| Kenko (`0abaf157-35d2-478f-8b19-c142f67aa8c7`) | Qenko (`1c93058e-d647-4f04-8aba-297c20ad41f2`) | 2000 | False |
| Xunantunich Mayan Ruins (`a2ddd76f-1c37-4ac9-971b-d9682384141d`) | Xunantunich (`03d63367-fb7a-4014-b1db-a704e99a10f3`) | 2000 | False |
| Archaeological Site of Olympia (`0d7c325a-5370-4a95-b048-8e599f69892c`) | Olympia, Greece (`9ba7c034-6aec-492e-b66e-4541ce3c987c`) | 2000 | False |
| Apollo Temple, Delphi (`7814f888-d384-442b-8b6b-72c1b209d1d5`) | Temple of Apollo, Delphi (`56836aa2-1680-43fb-aeef-1edcc33e2c91`) | 2000 | False |
| Khuntichi Vaat Hadsar Fort (`1a76bfc9-7056-4848-ac12-d24016a923bb`) | Hadsar Fort (`fe61c9c4-97dc-4478-93f8-5cd4a44d8ec2`) | 2000 | False |
| Wandlebury Hill (`3bb2d9e1-7e77-4582-8b28-92ab27133a9a`) | Wandlebury Hill Fort (`b319970d-efcd-4f5c-9d9b-55535771676b`) | 2000 | False |
| Archaeological Dolmens of Antequera (`434c9060-4b58-46a0-94f4-63a85b7133b9`) | Antequera Dolmens Site (`efe2bc83-83cc-4393-b725-a18543dc9d5f`) | 2000 | False |
| Kalkrieser Berg (`5d8a914c-d69d-409c-9713-588113811da5`) | Kalkriese (`3911fbf9-3c1c-4620-a197-10ccbb9e20f7`) | 2000 | False |
| Hipogeo de Biniai nou (`58d2d752-30cc-4f22-b2d5-ff27a4b395d1`) | Biniai Nou Hypogea (`13bdea38-cb6c-4c6b-85cb-402a31427819`) | 2000 | False |
| Banna, Birdoswald (`2048dfe4-9b29-494f-8807-881c71023f22`) | Birdoswald Roman Fort (`b9fdfd6f-b222-4c64-9953-b04fef1f55aa`) | 2000 | False |
| Mycenaean Acropolis of Midea (`3b7fc9a8-a685-4e5b-9ae7-df7a0d530d2e`) | Midea, Argolid (`3c47ded2-01b0-4789-bf6e-defb171ddd43`) | 2000 | False |
| Madain Saleh (`ab077874-2a7f-4add-adec-8cb42e9e9561`) | Hegra - Mada'in Salih (`47eb07cd-5c1c-4c0e-88c0-484d3b3411a1`) | 2000 | False |
| Archaeological Site of the Tombs of the Kings (`0144891e-136b-40fb-87ec-26f618e36365`) | Tombs of the Kings, Paphos (`15e95e05-6fb3-4779-bbcd-375cd2f031e0`) | 2000 | False |
| Cholesbury (`1706b1bf-6c89-4f31-a925-e5e679884794`) | Cholesbury Camp (`53a9ddce-054f-4471-94fd-6243611ae0a8`) | 2000 | False |
| Großmugl (`774a99e0-e8f7-4881-aa6e-94462da0c52d`) | The Giant Tumulus, Großmugl (`a07daa54-5e5d-48c7-a95f-097ce085c9fb`) | 2000 | False |
| Twin Gates of Pula (`f5df832e-ab5e-4e9c-b6c9-037441011945`) | Porta Gemina (`d4714397-6e73-432d-add3-c01e22cb055f`) | 2000 | False |
| Nefertari Temple (`ca33a292-b102-4efe-b644-48959d8ff741`) | Temple of Nefertari- Abu Simbel (`9031494a-4710-430f-975c-18c9a5990592`) | 2000 | False |
| Hatshepsut Temple (`c73b6ca5-aa7d-4737-af90-1e6cbab06ff5`) | Mortuary Temple of Hatshepsut (`3f27e34a-1817-4b2b-bc19-c3c17a7e6374`) | 2000 | False |
| Roman Ruins of Djemila (`9bf829da-096e-41c6-b175-f3436c1ce18c`) | Djemila (`a5232aa9-627c-444a-8ac7-82c5b79c3f2d`) | 2000 | False |
| Pyramid of Hetepheres I (`2fc65539-6b0f-4073-9db3-76dadc408cc8`) | Pyramid G1-a (`d47439dd-6349-4633-bf0b-eb97094ac743`) | 2000 | False |
| Enkomi (`dcda1568-0730-4cba-a9ce-c50c80ed941d`) | Engomi Ancient City Ruins (`0999c397-1333-4ff3-aa26-fe854f46de9c`) | 2058 | False |
| Sanctuary of Artemis, Brauron (`8107d407-8094-4f0b-b459-54b2a43e1864`) | Brauron (`ced822e8-13cd-49db-9011-808dc23aac45`) | 2000 | False |
| Ancient Stadium of Nemea (`5dd5ecd6-2cd4-4e37-ae35-51da8f716d07`) | Stadium at Nemea (`1bc57ad9-041a-42de-b0a1-c361a7beb531`) | 2000 | False |
| Qasr Sagha Temple (`41070db5-8f7c-4d69-8652-cc2d4bfb8bf4`) | Qasr el-Sagha (`5a2e082b-8ed8-4116-b5c3-5414826f0d92`) | 2000 | False |
| Qasr al-Sagha (`9910d3da-4875-49eb-8da4-3f2db69a48a6`) | Qasr el-Sagha (`5a2e082b-8ed8-4116-b5c3-5414826f0d92`) | 2000 | False |
| Olympos Ruins (`04d8ce82-4fa3-4e48-88b7-bb41b354260c`) | Olympos Antique City (`00f522ff-8e1b-4983-961c-ef6cb1ff27d1`) | 2000 | True |
| Templo Romano Évora (`07fb4e2f-26e5-4720-a949-9c28d4712e11`) | Roman Temple of Évora (`9152beea-f7ab-40ef-a692-ef63ac8e9ca6`) | 2000 | True |
| Area Archeologica di Alba Fucens (`13c3f25f-3887-49c1-9492-cf7e512e5782`) | Alba Fucens (`13120650-2e61-45af-976c-b2e0665c49af`) | 2000 | True |
| Archaeological Site, Heraion (`24676ed3-9308-42d4-bf35-1c739f0652e2`) | Heraion of Perachora (`9d9d94a0-f338-4392-860f-983c29fabb16`) | 2000 | True |
| Ancient Amathunta (`3ebb514f-ac4a-4913-b54b-409bcc29eff4`) | Amathus (`51daf6c9-25d3-4818-8857-0543f1203c57`) | 2000 | True |
| The Aqueduct of Jerwan (`4687a49a-c987-4c56-bc6e-5094aa57667d`) | Jerwan (`c6d9487d-d138-4d73-beb1-5735e50da048`) | 2000 | True |
| Tarxien Temples (`4a5a324f-832f-4dca-b688-d4a006d297c7`) | Templos de Tarxien (`318414bc-098b-4459-95c0-41e1ec49c8a8`) | 2000 | True |
| Coricancha (`4e6247b0-7416-413f-b7a3-b31890a45f3b`) | Qorikancha (`4a9b3802-1067-4f6b-a144-4c2ffe9619a4`) | 2000 | True |
| Archaeological Site of Kition (`55a670ec-c7c5-4f52-98ea-b25211aedd4e`) | Kition (`47c37ef9-98ee-41d8-879b-e78db06295da`) | 2000 | True |
| Augusta Bilbilis (`577b13cd-242b-4951-a8c4-ab3ecde0e5b1`) | Bilbilis (`23576019-c749-4ee9-95b1-cdae21f5ff06`) | 2000 | True |
| Dodona (`5a04d6f3-c82d-4c82-b1e9-3d70bff135ae`) | Archaeological Site of Dodoni (`56f594fc-6819-4d51-98a4-1cf5b4a265a6`) | 2000 | True |
| Hattuşa Örenyeri (`7e33b1ac-bb32-4b6c-b070-2c4fdcaf19fb`) | Hattusas (`109fcdea-c114-4143-87ac-77c4c9c20f16`) | 2000 | True |
| Pinara Antique City (`8cecb38f-08cf-4a93-b350-9ccbb74109bb`) | Pinara (`5025eee3-28ea-46d6-b2c3-dbb1f38a24d6`) | 2000 | True |
| Termantia (`93391ee6-8e80-42db-922c-11f64ea57db9`) | Tiermes Archaeological Site (`84ef64f3-394a-4b35-ba4a-7e81b3b6a317`) | 2000 | True |
| Dolmen of Menga (`ab03fa75-bbdc-46a2-ba55-25e2f5edd5c4`) | Dolmen de Menga (`485c3c0c-31f0-45a7-a06b-797c4c021466`) | 2000 | True |
| Banias (`ae2ca7b1-89da-46cb-8924-f9d04dd5da2e`) | Caesarea Philippi (`ce7db300-8777-425d-917a-2f6d9f325b58`) | 2000 | True |
| Bishop's Basilica of Philippopolis (`b46b6969-3160-4cbd-a574-8727ee7c53c5`) | Great Basilica, Plovdiv (`891ad351-7985-4c16-b6a6-830c26bc268f`) | 2000 | True |
| Ciudad Romana de Cáparra (`cf49332c-0a05-4ba7-bf4f-48a703ee7a1e`) | Cáparra (`577f2ec4-3dc0-4d10-9425-39f1cb654009`) | 2000 | True |
| Ancient Kourion (`d120ca9a-703b-49e2-b333-ad6dfe508953`) | Kourion (`9983bdce-9f35-47a3-a570-4021cfa41b97`) | 2000 | True |
| Ñusta Hispana (`dafc7527-c6c8-45c3-8c7d-4813d20a4dcf`) | Conjunto Arqueologico de Ñustahispana (`d41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d`) | 2000 | True |
| Thirty-nine (39) Bridge Street, Chester (`f23a31c3-6833-4df6-8583-3b3930b5a74f`) | Bridge Street Number 39, Chester (`21ac323f-7214-4891-9499-74e55c3d7d56`) | 2000 | True |

## Held back (not planned, not written)

* Enkomi (`dcda1568-0730-4cba-a9ce-c50c80ed941d`): nothing to move: the pair goes straight to its retirement
* Olympos Ruins (`04d8ce82-4fa3-4e48-88b7-bb41b354260c`): nothing to move: the pair goes straight to its retirement
* Templo Romano Évora (`07fb4e2f-26e5-4720-a949-9c28d4712e11`): nothing to move: the pair goes straight to its retirement
* Area Archeologica di Alba Fucens (`13c3f25f-3887-49c1-9492-cf7e512e5782`): nothing to move: the pair goes straight to its retirement
* Archaeological Site, Heraion (`24676ed3-9308-42d4-bf35-1c739f0652e2`): nothing to move: the pair goes straight to its retirement
* Ancient Amathunta (`3ebb514f-ac4a-4913-b54b-409bcc29eff4`): nothing to move: the pair goes straight to its retirement
* The Aqueduct of Jerwan (`4687a49a-c987-4c56-bc6e-5094aa57667d`): nothing to move: the pair goes straight to its retirement
* Coricancha (`4e6247b0-7416-413f-b7a3-b31890a45f3b`): nothing to move: the pair goes straight to its retirement
* Archaeological Site of Kition (`55a670ec-c7c5-4f52-98ea-b25211aedd4e`): nothing to move: the pair goes straight to its retirement
* Augusta Bilbilis (`577b13cd-242b-4951-a8c4-ab3ecde0e5b1`): nothing to move: the pair goes straight to its retirement
* Hattuşa Örenyeri (`7e33b1ac-bb32-4b6c-b070-2c4fdcaf19fb`): nothing to move: the pair goes straight to its retirement
* Pinara Antique City (`8cecb38f-08cf-4a93-b350-9ccbb74109bb`): nothing to move: the pair goes straight to its retirement
* Termantia (`93391ee6-8e80-42db-922c-11f64ea57db9`): nothing to move: the pair goes straight to its retirement
* Dolmen of Menga (`ab03fa75-bbdc-46a2-ba55-25e2f5edd5c4`): nothing to move: the pair goes straight to its retirement
* Banias (`ae2ca7b1-89da-46cb-8924-f9d04dd5da2e`): nothing to move: the pair goes straight to its retirement
* Bishop's Basilica of Philippopolis (`b46b6969-3160-4cbd-a574-8727ee7c53c5`): nothing to move: the pair goes straight to its retirement
* Ancient Kourion (`d120ca9a-703b-49e2-b333-ad6dfe508953`): nothing to move: the pair goes straight to its retirement
* Ñusta Hispana (`dafc7527-c6c8-45c3-8c7d-4813d20a4dcf`): nothing to move: the pair goes straight to its retirement
* Thirty-nine (39) Bridge Street, Chester (`f23a31c3-6833-4df6-8583-3b3930b5a74f`): nothing to move: the pair goes straight to its retirement

## Run

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --check-primitive
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --verify
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --interests
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --emit
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --rehearse
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --probe-guards
$PY scripts/remediation/mechanical/dup_merge.py files --wave 2026-11-12 --copy
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --apply
$PY scripts/remediation/mechanical/dup_merge.py files --wave 2026-11-12 --served
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --verify
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-12 --rehearse-rollback
```

The reversal order is retire, then move.

The loser's name row moves to the survivor as an alias. Lyra's boot (`_run_migrations`, 'Backfill AN Originals') inserts a label row for every site that has none under its own name key, so after a Lyra restart the retired loser holds a new row with that key and the rollback of the name row stops at `uq_usn`: roll the move back before the next Lyra restart, or delete that one new row first.
