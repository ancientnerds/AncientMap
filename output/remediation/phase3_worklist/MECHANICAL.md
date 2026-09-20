# Mechanically settable factual findings (27 sites) — **superseded: the write is done**

**Status 2026-09-21: written and audited.** These 27 rows **plus the 8 overlap sites**
(Satsurblia Cave, Didnauri, Armazi, Tsutskhvati Cave NM, Tsona Cave, Kutaisi, Dmanisi, Easter
Island) that Phase 3 also works were written in **one batch of 35 rows** — run stamp
`2026-09-21_mechanical-country`, journal 5,438 → **5,473** rows, landed pairs
`Georgia (country)` → `Georgia` **27** and `Chile, Easter Island` → `Chile` **8**,
`remaining_old_values=0` (`../AUDIT_LOG.md`, “Wave 4 MECHANICAL — the 35-row production write”).

**The 27-vs-35 split is superseded as a plan (ratified decision 1). Reason:** 35 = 27 + 8, and at
27 rows the `Georgia (country)` hub would have kept 7 sites, i.e. the split-hub defect would have
survived (`AUDIT_LOG.md`, “Condition (c) - the hub split”). The list below is kept as the input
record; **the country value in every row is already the new one**, so a census finding that still
flags one of them is comparing against the OLD value and must be reported as already-fixed, never
re-proposed. One row, one writer.

These T05 sites carry only `proposal=set` / `confidence=authoritative` findings
(`applicable=true`). The script applies them with a conditional `WHERE country = '<old>'`
and a journal entry. **Not Phase 3, not LLM work** (for the 8 overlap sites the country write is
done too — Phase 3 owns them for their *other* findings).

| Site | site_id | change |
|---|---|---|
| Ahu Akivi | 2dab79e8-1ece-4f9b-beb3-a91573d545c3 | `Chile, Easter Island` -> `Chile` |
| Ahu Nau Nau | 25910998-3672-4869-84cd-d737e7b8b611 | `Chile, Easter Island` -> `Chile` |
| Ahu Tongariki | 590d3dff-ec5a-4328-a0d9-5baf03686be0 | `Chile, Easter Island` -> `Chile` |
| Ahu Vinapu | 24695f34-5605-4cdd-965f-fd646c1ed044 | `Chile, Easter Island` -> `Chile` |
| Anacopia Fortress | 7d45e357-77ff-40f6-a4b4-7e16e015996a | `Georgia (country)` -> `Georgia` |
| Atashgah Of Tbilisi | f5da8b37-8247-42a2-91e7-769a85bb4d86 | `Georgia (country)` -> `Georgia` |
| Chabukauri Basilica | ca28f10c-b6b6-41bb-bf64-980908425ab7 | `Georgia (country)` -> `Georgia` |
| Dzalisi | cb0a55c2-48c5-4340-afb2-a5c0d5eec70b | `Georgia (country)` -> `Georgia` |
| Grakliani Hill | 9737ca03-ad30-46d2-8740-3dec20bed1ea | `Georgia (country)` -> `Georgia` |
| Kudaro | 2bb3d2fe-62b3-4d3f-b12f-e9bdee25f150 | `Georgia (country)` -> `Georgia` |
| Lake Paliastomi | 10096963-03a9-4698-82b9-8c6386759359 | `Georgia (country)` -> `Georgia` |
| Nekresi | 0060e6c0-8388-4762-bf51-9a3f88807899 | `Georgia (country)` -> `Georgia` |
| Nekresi Fire Temple | 7063f8dc-a347-4324-9930-6983ed9c997a | `Georgia (country)` -> `Georgia` |
| Nokalakevi | a621b66e-1fda-41b4-9c34-d1a3e7486bd5 | `Georgia (country)` -> `Georgia` |
| Orongo | 0db1078f-012b-42ef-a9b4-e5e482c92767 | `Chile, Easter Island` -> `Chile` |
| Rano Raraku | 56c3e7d6-250a-457d-9c42-7d37ef47af3c | `Chile, Easter Island` -> `Chile` |
| Sakdrisi | 17c20887-877e-4427-8728-4c856cc8c0c3 | `Georgia (country)` -> `Georgia` |
| Samshvilde | 43d64ea4-8c7e-4bca-bcfe-04b4e6e6b437 | `Georgia (country)` -> `Georgia` |
| Shukhuti Mosaic | a2e7ed0a-b619-4b9c-8626-6bfac777e811 | `Georgia (country)` -> `Georgia` |
| Tahai Ceremonial Complex | d972a5b7-866c-48d6-af54-d9ac91f00b0b | `Chile, Easter Island` -> `Chile` |
| Trialeti Petroglyphs | 0259ff6b-ef34-4a7e-93ef-78e2729e45a6 | `Georgia (country)` -> `Georgia` |
| Tsitsamuri | 8df1e714-b5bb-4d4b-846b-71cdf7cb3d21 | `Georgia (country)` -> `Georgia` |
| Uplistsikhe | a0c043a9-fc02-49d8-93e8-39100e5ed8c7 | `Georgia (country)` -> `Georgia` |
| Urbnisi | aeee41a7-f003-4d34-ba18-6f9b96563c4d | `Georgia (country)` -> `Georgia` |
| Vani | ea209a12-df80-46f7-9985-4ccd0ae5fc99 | `Georgia (country)` -> `Georgia` |
| Vani Archaeological Site | e8ecb6c3-4f2c-4505-9b66-ac3743b02e54 | `Georgia (country)` -> `Georgia` |
| Ziari | 1203a68d-5c19-4f8e-828f-053129f79a63 | `Georgia (country)` -> `Georgia` |
