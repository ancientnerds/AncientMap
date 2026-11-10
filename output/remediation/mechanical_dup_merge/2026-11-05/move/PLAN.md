# D14 duplicate merge `dup-merge-move-2026-11-05`: plan

Built 2026-11-05T22:36:08+00:00 by `scripts/remediation/mechanical/dup_merge.py` from the read-only production read of 2026-11-05 22:34:26.610072+00 (`READ.jsonl`). Lane `dup-merge-move-2026-11-05`: run stamp `2026-11-05_mechanical-dup-merge-move`, journal test id `D14/dup-merge-move`, premise `u.name || ' | ' || coalesce((SELECT string_agg(e.kind || '=' || e.value, ', ' ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = u.id), '') || ' | ' || coalesce(u.scope_status, 'NULL') || ' | ' || coalesce(u.scope_reason, 'NULL') || ' | survivor ' || coalesce((SELECT s.name || ' | ' || coalesce((SELECT string_agg(e.kind || '=' || e.value, ', ' ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = s.id), '') FROM unified_sites s WHERE CAST(s.id AS text) = CASE CAST(u.id AS text) WHEN '04d8ce82-4fa3-4e48-88b7-bb41b354260c' THEN '00f522ff-8e1b-4983-961c-ef6cb1ff27d1' WHEN '07fb4e2f-26e5-4720-a949-9c28d4712e11' THEN '9152beea-f7ab-40ef-a692-ef63ac8e9ca6' WHEN '13c3f25f-3887-49c1-9492-cf7e512e5782' THEN '13120650-2e61-45af-976c-b2e0665c49af' WHEN '24676ed3-9308-42d4-bf35-1c739f0652e2' THEN '9d9d94a0-f338-4392-860f-983c29fabb16' WHEN '3ebb514f-ac4a-4913-b54b-409bcc29eff4' THEN '51daf6c9-25d3-4818-8857-0543f1203c57' WHEN '4687a49a-c987-4c56-bc6e-5094aa57667d' THEN 'c6d9487d-d138-4d73-beb1-5735e50da048' WHEN '4e6247b0-7416-413f-b7a3-b31890a45f3b' THEN '4a9b3802-1067-4f6b-a144-4c2ffe9619a4' WHEN '55a670ec-c7c5-4f52-98ea-b25211aedd4e' THEN '47c37ef9-98ee-41d8-879b-e78db06295da' WHEN '577b13cd-242b-4951-a8c4-ab3ecde0e5b1' THEN '23576019-c749-4ee9-95b1-cdae21f5ff06' WHEN '7e33b1ac-bb32-4b6c-b070-2c4fdcaf19fb' THEN '109fcdea-c114-4143-87ac-77c4c9c20f16' WHEN '8cecb38f-08cf-4a93-b350-9ccbb74109bb' THEN '5025eee3-28ea-46d6-b2c3-dbb1f38a24d6' WHEN '93391ee6-8e80-42db-922c-11f64ea57db9' THEN '84ef64f3-394a-4b35-ba4a-7e81b3b6a317' WHEN 'ab03fa75-bbdc-46a2-ba55-25e2f5edd5c4' THEN '485c3c0c-31f0-45a7-a06b-797c4c021466' WHEN 'ae2ca7b1-89da-46cb-8924-f9d04dd5da2e' THEN 'ce7db300-8777-425d-917a-2f6d9f325b58' WHEN 'b46b6969-3160-4cbd-a574-8727ee7c53c5' THEN '891ad351-7985-4c16-b6a6-830c26bc268f' WHEN 'd120ca9a-703b-49e2-b333-ad6dfe508953' THEN '9983bdce-9f35-47a3-a570-4021cfa41b97' WHEN 'dafc7527-c6c8-45c3-8c7d-4813d20a4dcf' THEN 'd41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d' WHEN 'f23a31c3-6833-4df6-8583-3b3930b5a74f' THEN '21ac323f-7214-4891-9499-74e55c3d7d56' WHEN 'f3da4b6e-c4a3-4416-9c28-93bf761119ad' THEN '1531d4a1-bb24-4727-9b25-f2089088acaf' WHEN 'f5ca382a-3725-4cbb-961a-6afbf5c21507' THEN 'f6b6e039-36f1-4107-b730-dc2aa34b7a92' WHEN 'f967e3c4-fc5b-4cd0-91d1-06030d51e31c' THEN '0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3' END), '')`.

Counters: sites 16, cells 52, pairs 16, images 0, images_stay 265, heroes_demoted 0, links 28, links_stay 18, names 12

| loser | survivor | pair limit (m) | already retired |
|---|---|---|---|
| Olympos Ruins (`04d8ce82-4fa3-4e48-88b7-bb41b354260c`) | Olympos Antique City (`00f522ff-8e1b-4983-961c-ef6cb1ff27d1`) | 2000 | True |
| Templo Romano Évora (`07fb4e2f-26e5-4720-a949-9c28d4712e11`) | Roman Temple of Évora (`9152beea-f7ab-40ef-a692-ef63ac8e9ca6`) | 2000 | True |
| Area Archeologica di Alba Fucens (`13c3f25f-3887-49c1-9492-cf7e512e5782`) | Alba Fucens (`13120650-2e61-45af-976c-b2e0665c49af`) | 2000 | True |
| Archaeological Site, Heraion (`24676ed3-9308-42d4-bf35-1c739f0652e2`) | Heraion of Perachora (`9d9d94a0-f338-4392-860f-983c29fabb16`) | 2000 | True |
| Ancient Amathunta (`3ebb514f-ac4a-4913-b54b-409bcc29eff4`) | Amathus (`51daf6c9-25d3-4818-8857-0543f1203c57`) | 2000 | True |
| The Aqueduct of Jerwan (`4687a49a-c987-4c56-bc6e-5094aa57667d`) | Jerwan (`c6d9487d-d138-4d73-beb1-5735e50da048`) | 2000 | True |
| Coricancha (`4e6247b0-7416-413f-b7a3-b31890a45f3b`) | Qorikancha (`4a9b3802-1067-4f6b-a144-4c2ffe9619a4`) | 2000 | True |
| Archaeological Site of Kition (`55a670ec-c7c5-4f52-98ea-b25211aedd4e`) | Kition (`47c37ef9-98ee-41d8-879b-e78db06295da`) | 2000 | True |
| Augusta Bilbilis (`577b13cd-242b-4951-a8c4-ab3ecde0e5b1`) | Bilbilis (`23576019-c749-4ee9-95b1-cdae21f5ff06`) | 2000 | True |
| Hattuşa Örenyeri (`7e33b1ac-bb32-4b6c-b070-2c4fdcaf19fb`) | Hattusas (`109fcdea-c114-4143-87ac-77c4c9c20f16`) | 2000 | True |
| Pinara Antique City (`8cecb38f-08cf-4a93-b350-9ccbb74109bb`) | Pinara (`5025eee3-28ea-46d6-b2c3-dbb1f38a24d6`) | 2000 | True |
| Termantia (`93391ee6-8e80-42db-922c-11f64ea57db9`) | Tiermes Archaeological Site (`84ef64f3-394a-4b35-ba4a-7e81b3b6a317`) | 2000 | True |
| Dolmen of Menga (`ab03fa75-bbdc-46a2-ba55-25e2f5edd5c4`) | Dolmen de Menga (`485c3c0c-31f0-45a7-a06b-797c4c021466`) | 2000 | True |
| Banias (`ae2ca7b1-89da-46cb-8924-f9d04dd5da2e`) | Caesarea Philippi (`ce7db300-8777-425d-917a-2f6d9f325b58`) | 2000 | True |
| Bishop's Basilica of Philippopolis (`b46b6969-3160-4cbd-a574-8727ee7c53c5`) | Great Basilica, Plovdiv (`891ad351-7985-4c16-b6a6-830c26bc268f`) | 2000 | True |
| Ancient Kourion (`d120ca9a-703b-49e2-b333-ad6dfe508953`) | Kourion (`9983bdce-9f35-47a3-a570-4021cfa41b97`) | 2000 | True |
| Ñusta Hispana (`dafc7527-c6c8-45c3-8c7d-4813d20a4dcf`) | Conjunto Arqueologico de Ñustahispana (`d41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d`) | 2000 | True |
| Thirty-nine (39) Bridge Street, Chester (`f23a31c3-6833-4df6-8583-3b3930b5a74f`) | Bridge Street Number 39, Chester (`21ac323f-7214-4891-9499-74e55c3d7d56`) | 2000 | True |
| Archaeological Park Carnuntum (`f3da4b6e-c4a3-4416-9c28-93bf761119ad`) | Carnuntum (`1531d4a1-bb24-4727-9b25-f2089088acaf`) | 2000 | True |
| Dooey's Cairn (`f5ca382a-3725-4cbb-961a-6afbf5c21507`) | Ballymacaldrack Court Tomb (`f6b6e039-36f1-4107-b730-dc2aa34b7a92`) | 2000 | True |
| Shaduppum (`f967e3c4-fc5b-4cd0-91d1-06030d51e31c`) | Tel Hermal Fort (`0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3`) | 2000 | True |

## Held back (not planned, not written)

* Coricancha (`4e6247b0-7416-413f-b7a3-b31890a45f3b`): nothing to move: the pair goes straight to its retirement
* Dolmen of Menga (`ab03fa75-bbdc-46a2-ba55-25e2f5edd5c4`): nothing to move: the pair goes straight to its retirement
* Ñusta Hispana (`dafc7527-c6c8-45c3-8c7d-4813d20a4dcf`): nothing to move: the pair goes straight to its retirement
* Dooey's Cairn (`f5ca382a-3725-4cbb-961a-6afbf5c21507`): nothing to move: the pair goes straight to its retirement
* Shaduppum (`f967e3c4-fc5b-4cd0-91d1-06030d51e31c`): nothing to move: the pair goes straight to its retirement

## Run

```bash
PY=./.venv/Scripts/python.exe
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --check-primitive
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --verify
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --interests
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --emit
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --rehearse
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --probe-guards
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --apply
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --verify
$PY scripts/remediation/mechanical/apply.py --lane dup-merge-move-2026-11-05 --rehearse-rollback
```

The reversal order is retire, then move.

The loser's name row moves to the survivor as an alias. Lyra's boot (`_run_migrations`, 'Backfill AN Originals') inserts a label row for every site that has none under its own name key, so after a Lyra restart the retired loser holds a new row with that key and the rollback of the name row stops at `uq_usn`: roll the move back before the next Lyra restart, or delete that one new row first.
