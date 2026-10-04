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
| `theo_source_archive` | Full text and gzipped original HTML of every source a research run reads, plus adapter abstracts for sources never fetched. Archive completion adds the full text of each source a moderated claim cites that has none yet: the page its URL serves (HTML or PDF, extracted to text), Wikipedia articles through their REST HTML, the pages `doi.org` redirects to, and for a YouTube video the transcript copied from `news_videos` | `handlers/content_fetch.py`, `training_corpus.persist_run_corpus`, `archive_completion.py` |
| `theo_source_archive_runs` | Which run saw which source, under which search query, and whether a moderated claim cited it (`cited`, see below) | `training_corpus.persist_run_corpus`, `archive_completion.py` |
| `research_artifacts` | Intermediate reasoning: angle findings, specialist analyses, synthesis, debate, moderator verdicts, citation registry, the research dossier (manifest and image candidate pool), failure snapshots, curator input/output, miner candidates. Runs from before Theo became research-only also left final paper metrics | `handlers/state_persist.py`, `handlers/dossier.py`, `theo_worker`, `curator`, `graph_miner` |
| `thinking_log_archive` | Activity-feed rows moved here by the 90/365-day prune instead of being deleted | `thinking_log.prune_thinking_log` |
| `research_requests_archive` | Whole-row copy of a research request taken before a user deletes it | `api/routes/theo.py` |

`theo_source_archive_runs.cited` means "cited by a moderated claim": a final,
revised or speculative claim of the run's moderator cites the source. Theo only
researches; the paper is written later in the local paper studio, so a run has
no finished paper whose citations it could record. Rows written before Theo
became research-only mean that the finished paper cited the source.

Two tools read the corpus back. The dossier export
(`python -m pipeline.lyra.theo_dossier export`) reads a researched run's
dossier from `research_artifacts` and the texts of its sources from
`theo_source_archive`; `python -m pipeline.studio paper pull` stores those
texts in the local paper workspace (`texts/<source_id>.txt`), where the Claude
writer and the claim check read them. Archive completion reads which of the
cited sources already have a full text. Both take the best archive row per
source: a fetched full text before a TDM reservation before an adapter
abstract, the newest row within each class. The export ships the text of that
best row when it has a body and no reservation: a fetched full text or, where
nothing better exists, the adapter abstract. The reservation row of a reserved
source wins over an abstract, so the export ships nothing for it. Archive
completion counts only a fetched full text or a reservation as done: a source
with only an abstract is fetched again.

The pre-existing content stores (`news_videos.transcript_text`,
`news_articles.content`, `unified_sites`, `source_records`) are already
durable and are not changed by this policy.

## Legal basis and limits

**Lawful access.** Only publicly reachable pages are fetched. Nothing
circumvents a paywall, a login, or a technical access restriction. During a
run, `handlers/content_fetch.py` keeps `doi.org` out of the archive because it
resolves to publisher landing pages; that exclusion stays. Archive completion
(`archive_completion.py`, once per run after the moderator) follows a
`doi.org` redirect to the publisher's page and archives what that page serves,
under the same TDM check as every other fetch: the reservation is looked up
for the host and path the redirect ends on, and in the page's
`tdm-reservation` meta tag. The row keeps the URL the source was cited under
and that URL's domain (a `doi.org` host); the publisher's host is not stored.

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

**TDM-reserved sources (owner decision 16, 2026-09-26; recorded with the
owner's other decisions of the studio build in
`docs/superpowers/plans/2026-09-26-owner-questions.md`).** The page body of a
TDM-reserved source is never archived: `training_corpus.archive_documents`
stores a reserved document without its body, whichever tool fetched it, and
archive completion counts the source as `tdm_reserved` in the run's dossier
manifest. A paper may still cite it like any source. The claim check of the
paper studio reads such a source live from its URL: the `theo-claim-check`
workflow, which runs between `python -m pipeline.studio paper claims-export`
and `claims-import` (neither command fetches anything), fetches the page with
the archive's own reader and keeps the text it read only in the local paper
workspace, as `claims_check/live/<source_id>.txt`. `claims-import` and `paper
check` read that file; it is never uploaded or archived. An evidence quote on
the published paper may come from that text (owner question Q9, 2026-09-27,
same file).

A reservation covers what was fetched from the host. A source whose page is
reserved can still have an adapter-abstract row (written from the search
adapter's snippet, not from the page, with `tdm_opt_out = FALSE`), and a
YouTube transcript is copied from `news_videos` with no host to ask. Both kinds
of row carry `tdm_signal = ''` and no `tdm_checked_at`: nothing was fetched
from a host, so nothing was checked. The export rules below keep them out of
a training set unless their licence is established and the source has no
reservation.

**Retention.** Corpus data is retained as long as it is necessary for the
purpose above (§ 44b(2) sentence 2). Review annually; delete the corpus if the
model project is abandoned.

**Right to object.** A rights holder objecting to the use of their content is
served by deleting the affected rows:

```sql
DELETE FROM theo_source_archive WHERE domain = '<host>';
```

Rows archived through a `doi.org` redirect carry a `doi.org` domain, not the
publisher's host (see "Lawful access"), so a publisher's objection also needs
a match on its DOIs (the `doi` column or the DOI in `url`).

## Export rules

These are filters at **export** time. Collection stays broad on purpose —
narrowing it later is possible, widening it retroactively is not.

1. **Unresolved licence is excluded by default.** `license = ''` means nobody
   established what the licence is. Such rows may only enter a training set
   with a documented § 44b assessment recorded in this file. YouTube
   transcripts copied from `news_videos` and adapter abstracts have an empty
   licence unless the source's adapter reported one, so this rule keeps them
   out by default.
2. **TDM reservations are excluded.** `tdm_opt_out = TRUE` rows carry no body
   anyway; `tdm_signal = 'check_failed'` rows require a fresh check. A source
   with any reservation row is excluded as a whole: an older abstract row of
   the same source is not exported either.
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
  AND full_text IS NOT NULL
  AND source_id NOT IN (SELECT source_id FROM theo_source_archive WHERE tdm_opt_out);
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
