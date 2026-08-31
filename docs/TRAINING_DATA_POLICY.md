# Training data policy

**Status:** in force since 2026-08-31. Owner: Dominiak Consulting (operator of
ancientnerds.com).

## Purpose

Ancient Nerds collects text and reasoning traces from its own research
pipeline in order to develop a domain-specific language model for
archaeology and ancient history ("Ancient Nerds LLM"). This is text and data
mining within the meaning of § 44b UrhG / Art. 4 DSM Directive: analysing
lawfully accessible works to derive information from them.

This document records what is collected, on what basis, and what may be used
in a training export. It exists because collection decisions are made once
and reviewed rarely, while their legal consequences surface years later.

## What is collected

| Store | Content | Written by |
| --- | --- | --- |
| `theo_source_archive` | Full text and gzipped original HTML of every source a research run reads, plus adapter abstracts for sources never fetched | `handlers/content_fetch.py`, `training_corpus.persist_run_corpus` |
| `theo_source_archive_runs` | Which run saw which source, under which search query, and whether the finished paper cited it | `training_corpus.persist_run_corpus` |
| `research_artifacts` | Intermediate reasoning: angle findings, specialist analyses, synthesis, debate, moderator verdicts, final paper metrics, citation registry, failure snapshots, curator input/output, miner candidates | `handlers/state_persist.py`, `theo_worker`, `curator`, `graph_miner` |
| `thinking_log_archive` | Activity-feed rows moved here by the 90/365-day prune instead of being deleted | `thinking_log.prune_thinking_log` |
| `research_requests_archive` | Whole-row copy of a research request taken before a user deletes it | `api/routes/theo.py` |

The pre-existing content stores (`news_videos.transcript_text`,
`news_articles.content`, `unified_sites`, `source_records`) are already
durable and are not changed by this policy.

## Legal basis and limits

**Lawful access.** Only publicly reachable pages are fetched. Nothing
circumvents a paywall, a login, or a technical access restriction. `doi.org`
is excluded from the archive because it resolves to publisher landing pages.

**Reservation of rights (§ 44b(3) UrhG).** A machine-readable reservation is
honoured. Before archiving a host's content the pipeline reads
`/robots.txt` and `/.well-known/tdmrep.json`, and inspects the document for a
`tdm-reservation` meta tag. When a reservation is found the document body is
**not** stored; a metadata row records the finding, the signal that carried it
and the timestamp. A reservation cannot be reconstructed after the fact, which
is why it is captured per document rather than looked up at export time.

If a host cannot be reached for the check, the resulting rows carry
`tdm_signal = 'check_failed'`. Those rows are unchecked, not cleared, and must
be re-verified before any export that includes them.

**Retention.** Corpus data is retained as long as it is necessary for the
purpose above (§ 44b(2) sentence 2). Review annually; delete the corpus if the
model project is abandoned.

**Right to object.** A rights holder objecting to the use of their content is
served by deleting the affected rows:

```sql
DELETE FROM theo_source_archive WHERE domain = '<host>';
```

## Export rules

These are filters at **export** time. Collection stays broad on purpose —
narrowing it later is possible, widening it retroactively is not.

1. **Unresolved licence is excluded by default.** `license = ''` means nobody
   established what the licence is. Such rows may only enter a training set
   with a documented § 44b assessment recorded in this file.
2. **TDM reservations are excluded.** `tdm_opt_out = TRUE` rows carry no body
   anyway; `tdm_signal = 'check_failed'` rows require a fresh check.
3. **Non-commercial site sources are excluded from any commercial training.**
   The site database mixes licences; these `source_id` values are
   non-commercial or unclear and must be filtered:
   `topostext`, `earth_impacts`, `unesco` (description text),
   `arachne` (DAI terms unconfirmed — treat as excluded until clarified).
   Verified permissive at the record level: `geonames` (CC BY 4.0),
   `pleiades` (CC BY 3.0), `historic_england` (OGL v3.0), `open_context`
   (CC BY / CC0). Check `source_records.license` per row rather than trusting
   this list, which is a summary.
4. **User contributions are excluded until the terms cover training.** The
   current licence grant in `ancient-nerds-map/terms.html` covers publishing,
   modifying and incorporating a contribution into the service. It does not
   mention model training. See "Open items".
5. **Lyra conversations do not exist as data.** `PRIVACY.md` states that chat
   history is not stored server-side, and no code stores it. Any change here
   is a product decision requiring consent and a privacy-notice update.

Baseline export query:

```sql
SELECT source_id, url, license, full_text
FROM theo_source_archive
WHERE license <> ''
  AND tdm_opt_out = FALSE
  AND tdm_signal <> 'check_failed'
  AND full_text IS NOT NULL;
```

## Operating notes

* `LYRA_THEO_ARCHIVE_EXTRA_FETCH=1` additionally fetches sources the prompt
  path skips (Wikipedia, sources whose abstract already exceeds the fetch
  threshold). Off by default; it costs HTTP requests per angle and nothing
  else. `LYRA_THEO_ARCHIVE_EXTRA_FETCH_CAP` bounds those extra fetches per
  angle (default 800).
* Prompt caps (`source_max_content_chars` = 2000,
  `minimax_source_max_content_chars` = 12000) govern what an LLM sees and are
  independent of the archive, which stores the uncapped text. Raising a cap to
  "get more data" would only raise token spend.
* `scripts/vps_backup.sh` excludes `theo_source_archive` data from the daily
  dump and writes a separate weekly corpus dump (retention 2), so ten daily
  dumps do not carry ten copies of the corpus.
* The quota watchdog reports corpus size every ~6h and posts to Discord at
  5 GiB and 20 GiB.

## Open items for the operator

1. **Terms of Service.** To make user contributions usable for training, the
   licence grant needs to name it — e.g. "…to publish, modify, incorporate,
   and use for training, developing and improving machine-learning models…",
   plus the right to sublicense. Requires a 30-day notice period; existing
   contributions are not covered retroactively without renewed consent.
2. **Deleted papers.** `research_requests_archive` retains a deleted paper
   internally, including its `user_id`. This must be disclosed in the privacy
   notice, and the erasure request path (Art. 17 GDPR) must be able to reach
   it.
3. **Arachne / DAI terms** — unconfirmed, currently on the exclusion list.
4. **AI Act Art. 53** — if a general-purpose model is ever published, a
   training-data summary and a copyright policy are required. This file is the
   starting point; hook it into the EU AI Act compliance work.
