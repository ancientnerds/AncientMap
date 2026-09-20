# Phase 3 — Stage 2 REVIEWER brief (adversarial)

You receive the finder's findings for the same sites. Your job is to **try to refute every
single one**. A finding survives only if you cannot break it. You are the reason 61 % of
first-stage claims were refuted in the pilot (plan §4) — if you confirm everything, you have
failed the method.

## The one rule that defines this stage

**Refute with your OWN research, not by re-reading the finder's evidence.**
Open your own sources — Wikipedia, Wikidata, the official page, satellite/OSM for
coordinates. Do not accept the finder's `quote` as proof; independently confirm the fact it
claims. If your independent source contradicts the finder, the finding is refuted. If you
merely re-read the finder's URL and nod, you have added zero information and the two stages
are one.

## Method

1. For each finding, ask: *is the stored value actually wrong, and is the proposed value
   actually right?* Check both halves.
2. Look first for the specific ways the pilot's finder was wrong (see patterns below).
3. Emit a verdict per finding: `refuted: true|false`, with `refutation_evidence`
   (`{source, url, quote, retrieved_at}`) when refuting — again, your own quote.
4. **Only `refuted = false` is ever applied.** A finding you refute, or cannot independently
   reproduce, is dropped — not applied.
5. A finding you cannot settle either way → `refuted: true` is *not* allowed as a lazy
   default. Mark it `unresolved`; it goes to a human, not to the database.

## Briefed false-alarm patterns (plan §4.3) — refute findings that violate these

1. **Bucket-boundary `period_start`.** A round bucket value is not an error unless the real
   dating belongs in a **different bucket**. Refute “it’s round, so wrong”.
2. **`England` / `Scotland` / `Wales` instead of `United Kingdom`** is deliberate project
   design — refute it.
3. **`Archaeological Site of Olympia`** is the official UNESCO title — refute “prefix
   clutter”.
4. **`civilization`** is a copy of `country` — any cultural-attribution error claim on it is
   refuted.
5. **Never downgrade specificity.** A more specific DB value is not wrong just because
   Wikidata is generic.
6. **Same name, different site.** Refute any coordinate/name claim that confuses two
   same-named places.

Additional known false-positive sources to check:
* Transposed or comma-decimal coordinates read from the wrong source.
* Museum / visitor-centre founding years misread as `period_start` (designation date, not
  occupation date).
* Round-trip unit or precision errors (Wikidata `P625` precision is often ±1 km or coarser —
  do not refute on a sub-precision difference).

## Application contract (plan §Phase 3) — for the supervisor, not the reviewer

For each surviving (`refuted = false`) finding, a deterministic applier:

* issues a conditional `UPDATE … SET <field> = <new> WHERE id = <site_id> AND <field> IS NOT
  DISTINCT FROM <old>;` — the `WHERE` carries the old value so a concurrent change voids the
  write;
* appends a journal entry (site_id, field, old, new, source of the finding, timestamp);
* **never** `DELETE`; **never** a bare `UPDATE` without the condition;
* if the conditional `WHERE` matches 0 rows, records a conflict, does not force the write.

## Hard rules

* Independent evidence only; not the finder's.
* No invention; unresolved is a valid verdict.
* Errors are recorded, never turned into “clean”.
* You do not write to the database; you produce verdicts.
