# Phase-4 pilot thresholds, sealed before the first model question

Source: entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json` (sha256 `515601c3e91a770ce096ee001e6bfc1659c875d008f11d1b508d07a31d20e5af`), key `pilot_and_thresholds`. The two blocks between the rules are copied verbatim by `scripts/remediation/phase4/pilot4.py thresholds`. They are fixed: nothing in them changes after the first model question is exported.

---

THRESHOLDS (fixed now; never loosened after the data is seen)
- T1: 0 UNSUPPORTED sentences or cards among write-eligible sites. With about 500 sentences, the rule-of-three bound is about 0.6%.
- T2: 0 WRONG_SITE.
- T3: 0 lost hedges, negations or restrictions, and 0 flipped meanings from span drops.
- T4: 0 verifier false-passes, i.e. cases where the audit finds a violation of a property some V-rule claims to check.
- T5: broken sentences (fragment or dangling reference) at most 1% of published sentences, each traced to a rule gap that is then closed.
- T6: cards 100% within 80-200 characters, 0 country names, 0 markers, 0 missing glyphs, 0 NOT_CONTAINED.
- T7: 0 of the 25 gold or canary errors recur. Each such site is written clean or held with a closed-list reason.
- T8: at least 80% of the pilot's lane-W sites are write-eligible (coverage).
- T9: at most $0.004 per site (ledger), and at most 2% selector or reviewer parse failures.
- T10 writer: 0 unexplained matched_0; every chunk passes read-back and the inverse proof; acceptance 0 deviations; T08 finds 0 on written sites; both in-database invariants hold.
- T11 lane R: 0 UNSUPPORTED over at least 8 sites. Any hit closes lane R for the run, and its sites are held with the reason 'lane-R-closed'.
- T12 lane T: the same rule over at least 5 sites.
- T13: MiniMax cost per search recorded, and the floors never crossed.

Reported, not gating: reviewer-auditor agreement, and the reviewer's miss rate.

ON FAILURE
- A failure on T1-T7 or T10-T12 means STOP, find the root cause, fix it, and re-pilot on a fresh draw of the same strata in a new run directory.
- A failure on T8 or T9 allows documented tuning (selection preferences, span rules, parser), followed by a re-pilot.

---

## Note, 2026-09-24 - written before the first model question of this pilot was exported

- **The answering model is Opus, through the handoff.** By the owner's order of 2026-09-23 ("no
  DeepSeek any more - everything with Opus"), every model question of this pilot - selector,
  translator, restricted lane, reviewer - is exported to a handoff directory and answered by an Opus
  agent of the orchestrating Claude Code session (`scripts/remediation/opus_handoff.py`,
  `OPUS_MODEL` = `anthropic/claude-opus-5-5 (Claude Code agent)`), never by a model API called from
  the pipeline. The design's "opencode-go/deepseek-v4.1-flash through Pi" does not run.
- **MiniMax route searches are not used** (owner order, "everything with Opus"). The routes stage
  (S1b) runs with a search allowance of 0 (`mass4.py --searches-off`): it builds no MiniMax client
  and sends no search. A site its free routes (the `source_url` title, langlinks, geosearch) leave
  without an own English article waits on the search and is **held `search-stopped`** by the route
  stage, and is reported - its lane is never guessed. The pilot's lane-T and lane-R strata are
  therefore candidates held so (`phase4/pilot4.py`).
- **What follows from the two orders, under the thresholds as written above (none is changed or
  loosened):** the design's pilot step 3 ("20 MiniMax searches between two quota probes") is not
  run, so T13 has no search to record; no site reaches lane T or R, so T11 ("over at least 8 sites")
  and T12 ("over at least 5 sites") cannot be met - lanes T and R do not pass their pilot and none
  of their sites is written; T9's dollar bound reads a ledger whose Opus lines are unmetered
  (`metering: unmetered`, cost 0): the ledger's dollars measure nothing, and the pilot reports the
  number of unmetered calls instead of a price. T9's parse-failure bound, and T1-T8 and T10, apply
  unchanged.
