# Card Description Generator

A procedure for generating punchy 120-character card descriptions for all Forgotten Worlds card sites. Claude Code follows this step-by-step when the user says "generate card descriptions".

## Execution Procedure

**Step 0 — Check prerequisites**

1. Verify `output/card_sites.json` exists. If not, run: `python scripts/export_card_sites.py`
2. Verify `card_stats.card_description` column exists (the migration in `orchestrator.py` adds it on deploy; for local dev, run the ALTER TABLE manually if needed).

**Step 1 — Check progress**

1. Read `output/card_descriptions.json`. If missing, create it with content: `{"descriptions": {}}`
2. Scan `output/card_descriptions_batch_*.json` for any batch files not yet merged. If found, merge them first (see Step 3c).
3. Count completed descriptions vs total sites in `output/card_sites.json`.
4. Report: `Progress: X / Y descriptions complete (Z% done)`
5. If all done → skip to Step 4.

**Step 2 — Prepare parallel batches**

1. Read `output/card_sites.json` (full site list).
2. Read `output/card_descriptions.json` (completed descriptions).
3. Filter out sites whose `site_id` is already in the descriptions dict → get `remaining` list.
4. Split `remaining` into **10 equal chunks** by index (chunk 0 = indices 0–N, chunk 1 = N+1–2N, etc.). No overlap.
5. Write each chunk to `output/batch_input_NNN.json` (array of site objects, NNN = 001–010).
6. Report: `Prepared 10 batches of ~M sites each. Total remaining: R`

**Step 3 — Generate descriptions (parallel agents)**

Launch **10 agents in parallel** (subagent_type: `general-purpose`), each with:
- Its own batch input file to read (`output/batch_input_NNN.json`)
- Its own output file to write (`output/card_descriptions_batch_NNN.json`)
- The full Tone & Style Guide (copy the guide into the agent prompt — agents don't share context)

Each agent's prompt must include:
1. Read `output/batch_input_NNN.json`
2. For each site, write a **max 120-character** description following the Tone & Style Guide
3. Validate every description is <= 120 chars. If over, shorten it.
4. Write the result to `output/card_descriptions_batch_NNN.json` as: `{"site_id": "description", ...}`
5. Print a summary: `Batch NNN complete. Wrote X descriptions.`

**Step 3b — Wait and verify**

After all agents finish:
1. Read each `output/card_descriptions_batch_NNN.json`
2. Check: total descriptions across all batch files == total sites in all input files
3. Check: no duplicate `site_id` across batches (there shouldn't be, but verify)
4. Check: every description is <= 120 chars and non-empty
5. Report any gaps or issues

**Step 3c — Merge**

1. Read `output/card_descriptions.json` (existing descriptions)
2. Read all `output/card_descriptions_batch_*.json` files
3. Merge everything into `output/card_descriptions.json`
4. Delete the batch input and output files (cleanup)
5. Report: `Merged N new descriptions. Total: X / Y (Z%)`

**Step 4 — Validate all descriptions**

1. Read `output/card_descriptions.json`.
2. Check every description:
   - Length <= 120 characters? Flag any that exceed.
   - Not empty/blank?
3. If any fail: fix them in-place (rewrite to fit 120 chars), save the file.
4. Report: `Validation: X passed, Y fixed`

**Step 5 — Import to DB**

1. Run: `python scripts/import_card_descriptions.py`
2. Report the result (how many rows updated, total with descriptions).

---

## Tone & Style Guide

**Voice**: Mix of documentary narrator and curiosity hook. Think National Geographic meets a trading card.

**Structure** (aim for this pattern, adapt as needed):
- **Start with an age/period anchor**: "Built 9,600 BC", "3rd-century fortress", "Active 6000–3000 BC"
- **ONE outstanding fact**: the single most remarkable thing about this site
- **Spark curiosity**: leave the reader wanting to know more

**When age/period is unknown or vague** (`period_start` is null, `period_name` is "Unknown" or missing):
- **Skip the date opener entirely.** Lead with the site's defining trait instead.
- Good openers: the site type ("Hilltop fortress..."), a physical feature ("Carved from a single rock..."), what was found there ("Over 2,000 Bronze Age tools unearthed..."), or its scale/purpose ("A 3km tunnel system connecting...").
- **Never write "Date unknown"** or "Undated" — just don't mention dates at all.
- If `period_name` is a broad range like "< 4500 BC" or "1000 - 1500 AD", use that range loosely: "Predating 4500 BC" or "Medieval-era" — don't fake precision.

**Rules**:
- **Max 120 characters** (hard limit — this must fit on a card)
- **Never mention the country** (it's already shown on the card)
- **Factually accurate** — only use facts from the Wikipedia source text provided
- **No generic filler** ("ancient ruins", "important site", "rich history")
- **Prefer concrete details** over vague adjectives
- If the wiki excerpt is empty/missing, write a brief factual description based on the site name, type, and period

**Examples with known dates**:
```
Göbekli Tepe: "Built 9,600 BC. Massive carved pillars erected 6,000 years before Stonehenge."
Pompeii: "Buried by Vesuvius in 79 AD. Bakeries, bathhouses, and graffiti frozen exactly as they were."
Petra: "Carved into sandstone cliffs around 300 BC. A lost trade capital that channeled water through the desert."
Angkor Wat: "Built in the 12th century. The world's largest religious monument, once home to 750,000 people."
Machu Picchu: "Built around 1450 AD. An Inca estate perched 2,430m high, abandoned before the Spanish ever found it."
Chichén Itzá: "Built around 600 AD. Its pyramid casts a serpent shadow down the stairs at every equinox."
```

**Examples with unknown/vague dates**:
```
Yonaguni Monument: "A massive stepped structure on the seafloor. Still debated: natural formation or submerged ruins?"
Adam's Calendar: "A stone circle aligned to solstices and equinoxes, hidden in the mountains near Mpumalanga."
Gunung Padang: "Layers of buried construction stacked deep into a volcanic hill. Each layer older than the last."
Rujm el-Hiri: "Concentric stone rings visible only from the air, with no settlement anywhere nearby."
```

**Anti-examples** (don't write like this):
```
BAD: "An important archaeological site with rich history." (generic, no facts)
BAD: "Located in Turkey, this ancient temple..." (mentions country)
BAD: "Göbekli Tepe is one of the most significant archaeological discoveries of the 20th century." (Wikipedia voice, no card punch)
BAD: "Date unknown. A mysterious site in the desert." (says "date unknown", generic)
```
