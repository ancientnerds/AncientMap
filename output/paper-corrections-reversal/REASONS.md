# REASONS - byte-identical correction entries, 04.10.2026

## What happened

The audit campaign's conveyor (`ship_ready.py`) decided what to send by reading
`build_status.json`, which keeps `built: true` forever after a successful build.
Every paper that was already live was therefore sent a second time with the same
bundle, and a third time where a later pass rebuilt it. The second write appended
the SAME correction log entry again.

**Nothing in the paper text changed.** The repeats live only in
`research_requests.result_json->'corrections'`, the correction log the page
renders under the paper, and they are byte-identical to an entry that is already
there - same date, same text, same length.

## What this reversal does

For each of the 22 papers: keep the FIRST occurrence of every distinct entry, in
its original order, and drop later byte-identical repeats.

* no distinct entry is removed - the gate in `dupes_plan.py` refuses to write a
  plan in which a removed entry has no kept byte-identical twin;
* no entry is reordered or reworded;
* no paper text, title, date, author, writer stamp, evidence, video or reference
  is touched;
* 42 of 97 entries go, 55 stay.

## Why it is safe to write without a schema change

`theo_paper_publications` has a CHECK constraint admitting only
`publish | correct | register_video`, and a row there would mean "a paper was
published/corrected" - which is exactly what this reversal is NOT. Adding a
reversal action would need a numbered migration and therefore a deploy to main.
So the record of this write is the plan, the backup and this file, kept in the
repository, plus the journal's own unchanged `bundle_sha256` history per paper.

## Rollback

`BACKUP.json` holds the complete corrections array of every affected paper as it
stood before the write; `BACKUP.sha256` is its own hash. Restoring is one UPDATE
per paper from that file, and `resulting_corrections_sha256` in `PLAN.json`
verifies the post-state.

## Per paper

### ardre-viii-and-the-norse-mythological-tradition

`4e86ca59-a8ec-4f8b-a3c3-f0d0e398932c` - 4 entries, 2 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `7f001be54518` | 1310 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `99269065367a` | 1108 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `99269065367a` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `99269065367a` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### cargo-cults-and-uncontacted-peoples-in-comparative-perspective

`a00c4ee2-0162-4bfe-997f-72f7ac3457fc` - 3 entries, 1 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `ea8c8d8b766d` | 1291 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `29241c117769` | 1073 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `29241c117769` | 1073 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### cyclical-world-ages-in-comparative-mythology

`1d0053d4-c28b-45db-a30c-20c6501d6147` - 5 entries, 1 removed, 4 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `b8e98f71e355` | 581 | keep | Unabhaengige Belegpruefung am Quelltext (3. Oktober 2026): 38 Aussagen und Belegstellen korrigiert, sechs nich |
| 1 | `22e393f1b222` | 748 | keep | Nachtrag zur Belegpruefung vom 3. Oktober 2026: Die sechs zuvor als unbelegbar gemeldeten Passagen sind nun ta |
| 2 | `f20b16e9c1be` | 1292 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `b17ef6d56c5b` | 1089 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `b17ef6d56c5b` | 1089 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### flying-discs-in-european-religious-art

`1e7678ad-2e4b-4e6d-8353-701d38037c8e` - 3 entries, 1 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `0e126b2313c6` | 1293 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `fd829cba629a` | 1091 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `fd829cba629a` | 1091 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### geomagnetic-excursions-and-pole-shift-catastrophism

`a56973e7-19b2-4394-be43-24182ef4fb1a` - 5 entries, 3 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `dfc5c7ff6535` | 1309 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `dab9452d4629` | 1108 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `dab9452d4629` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `dab9452d4629` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `dab9452d4629` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### global-flood-myths-and-the-younger-dryas-catastrophe-debate

`9b23ae9a-d0d1-4c06-b65d-4098e2cb5761` - 5 entries, 3 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `55e6d4bb4324` | 1295 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `656d4500080d` | 1093 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `656d4500080d` | 1093 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `656d4500080d` | 1093 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `656d4500080d` | 1093 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### hawaras-labyrinth-between-mainstream-and-fringe-archaeology

`994e7d40-e35d-49af-8af6-cfaef9e1279b` - 5 entries, 3 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `989c68418fe6` | 1291 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `cc8eee92c4d3` | 1089 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `cc8eee92c4d3` | 1089 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `cc8eee92c4d3` | 1089 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `cc8eee92c4d3` | 1089 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### induced-emf-in-ancient-megalithic-stone-structures

`4886d748-c37f-4c09-8fc6-f29eef5caacb` - 4 entries, 2 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `4fe5b3ce9697` | 1328 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `caea8e090d3f` | 1126 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `caea8e090d3f` | 1126 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `caea8e090d3f` | 1126 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### near-death-experience-phenomenology-and-reincarnation-traditions

`b142912a-5ab1-4898-86b6-436fa9f6cdce` - 4 entries, 2 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `85ca038794c0` | 1326 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `91159d3903e3` | 1123 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `91159d3903e3` | 1123 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `91159d3903e3` | 1123 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### panspermia-and-directed-panspermia-in-scientific-and-cultural-context

`aae36b9c-85e0-4825-9492-77ef3c02eb21` - 5 entries, 3 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `ae25a2a21f2c` | 1288 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `d61427a98949` | 1085 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `d61427a98949` | 1085 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `d61427a98949` | 1085 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `d61427a98949` | 1085 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### pineal-gland-dmt-in-near-death-and-cross-cultural-mysticism

`4486b29c-8773-4b49-ab74-f7832426e88e` - 7 entries, 3 removed, 4 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `eb0f1b2942a4` | 1310 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `904f78ba485a` | 1108 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `904f78ba485a` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `904f78ba485a` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `f40ba3c45e73` | 1108 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 5 | `979e1764c327` | 1108 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 6 | `979e1764c327` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### plasma-cosmology-and-the-electric-universe

`02515a7a-2097-409d-8288-1da5f2a72216` - 3 entries, 1 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `c98856926e12` | 1310 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `1b2b97de2715` | 1107 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `1b2b97de2715` | 1107 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### quantum-approaches-to-consciousness

`80c629b4-f5e3-43d4-8920-1b4b6eddaa1b` - 5 entries, 2 removed, 3 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `829e56923be3` | 1326 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `d73ef8782c5a` | 1124 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `d73ef8782c5a` | 1124 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `d73ef8782c5a` | 1124 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `1c9cf823eeea` | 1123 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### solar-superflares-cosmic-impacts-and-fire-and-flood-mythology

`ee3493e8-70cb-4619-941d-9fa2afcc6739` - 4 entries, 2 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `dc850582952c` | 1293 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `58ecaa4f38a6` | 1090 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `58ecaa4f38a6` | 1090 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `58ecaa4f38a6` | 1090 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### stargate-project-and-sri-remote-viewing-evidence

`099ad920-2e52-4180-915c-c040d316f3d7` - 4 entries, 1 removed, 3 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `4097b58ca3de` | 799 | keep | Unabhaengige Belegpruefung am Quelltext (3. Oktober 2026): 33 Aussagen und Belegstellen korrigiert. Die Remote |
| 1 | `3c93afbcd695` | 1321 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `74ace6fa0700` | 1120 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `74ace6fa0700` | 1120 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### the-bosnian-pyramid-project

`e82bd854-1faa-460c-93b7-bdf9e57e09bc` - 4 entries, 1 removed, 3 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `e3e82f9ea1b2` | 1311 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `30601a0cdb5d` | 668 | keep | One structural repair, no claim touched. The stored text of this paper ended mid-sentence: the original resear |
| 2 | `23f642a07d31` | 1108 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `23f642a07d31` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### the-engineering-and-origins-of-the-baalbek-megaliths

`29436601-239b-4139-a5a0-c9e34e32928f` - 6 entries, 3 removed, 3 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `85403df5019b` | 1309 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `4ef660fa8378` | 784 | keep | Provenance record added; no sentence of the paper's text changed. The correction published earlier today rewro |
| 2 | `15b2cbc8dc6e` | 1107 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `15b2cbc8dc6e` | 1107 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `15b2cbc8dc6e` | 1107 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 5 | `15b2cbc8dc6e` | 1107 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### the-lost-universal-tongue-in-myth-and-linguistics

`a98ad8fe-31e0-4abe-868e-02559f6c2c58` - 4 entries, 2 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `0427e0e2beae` | 1318 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `d7826193014c` | 1116 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `d7826193014c` | 1116 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `d7826193014c` | 1116 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### the-simulation-hypothesis-arguments-critics-and-ancient-predecessors

`ea0c513e-fe1b-47df-855e-71f473a8a1f1` - 3 entries, 1 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `6e2694edd285` | 1312 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `3c8942ee8c28` | 1109 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `3c8942ee8c28` | 1109 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### the-squatter-man-petroglyph-and-auroral-sky-mythology

`27ec3538-258c-4960-9493-2bf6c0dc1a3b` - 3 entries, 1 removed, 2 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `f61c965f1c2a` | 1311 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 1 | `36193b6aceb8` | 1108 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 2 | `36193b6aceb8` | 1108 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### ufos-uap-and-the-modern-disclosure-debate

`95fa3798-1678-40a4-ae2e-58595de93918` - 6 entries, 2 removed, 4 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `b8ee77553104` | 57 | keep | Roswell date correction |
| 1 | `6a0a6d5f0913` | 313 | keep | Removed an uncited sentence: the weather-balloon explanation did not hold as the official position for nearly  |
| 2 | `6ebb69833981` | 1325 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `001a1c1ed487` | 1123 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `001a1c1ed487` | 1123 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 5 | `001a1c1ed487` | 1123 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

### water-erosion-evidence-in-the-osiris-shaft

`ef52c194-e8c8-42a9-b317-e64a273f7780` - 5 entries, 2 removed, 3 left.

| # | sha256 (first 12) | chars | kept/removed | text |
|---|------------------|-------|--------------|------|
| 0 | `f3715cccddae` | 631 | keep | Unabhaengige Belegpruefung am Quelltext (3. Oktober 2026): 14 Aussagen an ihre Quellen angepasst, 5 unbelegte  |
| 1 | `f3715cccddae` | 631 | REMOVE | Unabhaengige Belegpruefung am Quelltext (3. Oktober 2026): 14 Aussagen an ihre Quellen angepasst, 5 unbelegte  |
| 2 | `d6d5e6bccece` | 1292 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 3 | `9cbebfee2d0d` | 1090 | keep | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |
| 4 | `9cbebfee2d0d` | 1090 | REMOVE | Every claim in this paper was re-checked against the sources it cites, by an independent audit that fetched an |

