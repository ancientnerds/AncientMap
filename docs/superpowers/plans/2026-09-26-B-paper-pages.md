# Stream B: Paper Pages for Claude-Written Papers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The public paper page `/research/{slug}` (and `GET /api/v1/research/{slug}`) shows what a Claude-written paper carries: stable `#ev-NN` evidence anchors with "Video at m:ss" deep links, the registered YouTube videos, the public corrections log and the visible AI disclosure line. Papers without these keys keep rendering byte for byte as they do today.

**Architecture:** Evidence stays out of the markdown. `result_json.evidence[]` ties each claim to one paragraph through `anchor_text`. After nh3 has sanitised the body, a pure Python helper in `pipeline/research_html_renderer.py` injects `id="ev-NN"` into the matching `<p>` (the same approach as `_heading_anchors`). The same module validates the four optional keys (`evidence`, `videos`, `corrections`, `writer`), and fails loudly on malformed data. `api/routes/research_html.py` adds the `videos`/`corrections`/`writer` payload keys only when a paper has them. React renders them through three new components in `components/theo/`, and `researchMeta` extends the JSON-LD only when they are present.

**Tech Stack:** Python 3.11 (FastAPI, SQLAlchemy `text()`, psycopg2 jsonb decoding, Python-Markdown and nh3 via the existing `markdown_to_html`), pytest; React 18 SSR (`renderToString`), TypeScript strict, Vitest (node and jsdom), plain CSS.

---

## Read this first (binding rules for every task)

- **Worktree:** `C:/PythonProjects/AncientMap-studio` (branch `feat/studio`). Other implementers work in the same worktree at the same time. Touch only the files listed under "File Structure". Anything else goes to the "Cross-stream requests" section at the end; do not do it yourself.
- **Every task of this plan needs INT:I0**, the build index's integration item I0 (`docs/superpowers/plans/2026-09-26-00-index.md`, section 6): the owner-decision amendments and every confirm-round fix are in the four plans, the spec, the writer-brief asset and the owner-questions file, committed per plan by pathspec after the last confirm fix. Until that commit, the text of any task may still change: the amendment passes also changed tasks that no per-task gate named (Task 4's and Task 9's `poster`, for example), so a task built earlier can be a pre-amendment version. Check that both of these hold: `git log --oneline 622a20d..HEAD -- docs/superpowers/plans/2026-09-26-B-paper-pages.md` prints at least one commit (this plan's I0 commit), and `git status --porcelain -- docs/superpowers/specs/2026-09-26-studio-and-claude-write-design.md "docs/superpowers/plans/2026-09-26-[ABCD]-*.md" docs/superpowers/plans/2026-09-26-owner-questions.md docs/superpowers/plans/assets/writer-brief-editorial.md` prints nothing. If either check fails, stop and report it to the orchestrator. Do not start any task of this plan, the frontend Tasks 5-12 included.
- **Commit only your own paths**, always with a pathspec, so nobody else's staged files end up in your commit:
  `git add <paths> && git commit -m "<sentence>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <paths>`
  Do not push. A push to `main` is a live deploy (CLAUDE.md).
- **Working copies are CRLF** (`core.autocrlf=true`). Make edits with the Edit tool. **Never write code through bash heredocs:** they eat backslashes in this environment (see the memory note `reference-heredoc-backslash-escapes`).
- **No fallback code** (CLAUDE.md). Malformed extras raise `PaperPageError`. An evidence anchor that does not resolve raises; it is never silently dropped. The publish gates (stream A, request CS-3: the `theo_publish` CLI's publish, correct and register-video modes, and the founder route `POST /research/{id}/publish`) run the same checks through this plan's own functions, so a raise on a live page means gate and page disagree, which is a bug to fix.
- **One anchor rule** (stream A's contract C9, the writer brief's "anchor_text is the opening of that paragraph"): the normalised anchor is at least `MIN_ANCHOR_CHARS` (20) characters long, and exactly one paragraph's normalised text **starts with** it. Several evidence entries may open the same paragraph. The page applies it to the plain `<p>` elements it serves (Task 2); a substring match is wrong.
- `pipeline/research_html_renderer.py` is imported by `pipeline/static_exporter.py` and the landing route, so its module-level imports stay stdlib-only. It imports `EVIDENCE_ID_RE`, `YOUTUBE_ID_RE`, `poster_web_path`, `normalize_anchor_text` and `MIN_ANCHOR_CHARS` from `pipeline.lyra.theo_publishing` **inside** the functions that need them (`parse_evidence`, `parse_corrections`, `parse_videos`, `resolve_evidence_anchors`; the import would otherwise be circular, see Task 2). `pipeline.lyra.theo_publishing.EVIDENCE_ID_RE` (`ev-[0-9]{2,}`: ASCII digits only, always applied with `.fullmatch`) is the one Python definition of the evidence-id format, `pipeline.lyra.theo_publishing.YOUTUBE_ID_RE` (`[A-Za-z0-9_-]{11}`, always applied with `.fullmatch`) the one definition of a YouTube video id's format, and `pipeline.lyra.theo_publishing.poster_web_path(request_id, youtube_id)` (`/data/research-images/<request_id>/video_<youtube_id>.jpg`, owner decision #13) the one definition of a video poster's path: gate, page, local check, studio ledger and case file import them, and this plan defines no copy.
- **Line numbers are hints, anchors are binding.** `integrate/wave1`'s edits to `api/routes/public_v1.py`, `api/schemas/public_v1.py`, `ancient-nerds-map/src/types/anRoute.ts`, `ancient-nerds-map/src/seo/__tests__/render.test.tsx` and `tests/api/test_sitemap_lastmod.py` are already in `feat/studio` (merge 622a20d); every quoted anchor of this plan was re-verified verbatim on 622a20d. The orchestrator merges `origin/main` again before the push (I11b); locate edits by name or quoted text, never by line. When a merge meets one of this plan's test files, keep both sides' tests.
- **Byte parity:** `ancient-nerds-map/src/seo/__tests__/meta.test.ts` compares `renderHead()` byte for byte with the frozen `pyref/*.html`. Do not edit any `pyref/` file. All JSON-LD additions depend on the new optional fields, which the pyref payloads do not have.
- Python test command form (from the repo root):
  `./.venv/Scripts/python.exe -m pytest <file> -m "not integration and not live_llm" -q`
- Frontend test command form: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run <file>`

## Dependencies and order

Every row also needs INT:I0 (see "Read this first"). The table lists only the needs beyond it.

| Task | Needs |
|---|---|
| 1 | **CS-2 (A Task 2)**: `EVIDENCE_ID_RE`, `YOUTUBE_ID_RE` and `poster_web_path` in `pipeline/lyra/theo_publishing.py` |
| 2 | Task 1 + **CS-2** (stream A Task 2: `normalize_anchor_text` and `MIN_ANCHOR_CHARS` in `pipeline/lyra/theo_publishing.py`) |
| 3 | Tasks 1, 2 (and therefore CS-2) |
| 4 | Task 1 (and therefore CS-2). Its Step 0 extends `api/schemas/public_v1.py`, which this stream owns |
| 5-11 | frontend only, independent of the Python tasks. Run them in order (5 → 11) |
| 12 | nothing beyond INT:I0 (sitemap lastmod) |
| 13 | Task 3 (the comment describes the body_html that Task 3 serves) |
| 14 | all |

Check CS-2 with `grep -cE "def normalize_anchor_text|^MIN_ANCHOR_CHARS|^EVIDENCE_ID_RE|^YOUTUBE_ID_RE|def poster_web_path" pipeline/lyra/theo_publishing.py`: it must print `5`. If it prints less, do Tasks 5-12 first and come back to 1-4 and 13 later. Do not stub the functions or copy a regex or the poster path: a stub would hide the contract this plan depends on, and a copy would be a second definition of the evidence-id format, the YouTube-id format or the poster path (the owner's rule: never duplicate a utility, import it).

Stream A's publish, correct and register-video gates (A Tasks 15, 17, 18) and the founder publish route (A Task 21) call this plan's `paper_markdown`, `parse_evidence`, `resolve_evidence_anchors`, `paper_extras` and `PaperPageError` (CS-3), so land Tasks 1-2 early. They are ready when `grep -cE "def (paper_markdown|parse_evidence|resolve_evidence_anchors)[(]|class PaperPageError" pipeline/research_html_renderer.py` prints `4`. Tasks 1 and 2 depend only on A Task 2, so there is no cycle.

## File Structure

| File | Action | Single responsibility |
|---|---|---|
| `pipeline/research_html_renderer.py` | Modify | Research-paper markdown preparation (`paper_markdown`), validation of the four optional `result_json` keys (`paper_extras` and friends), and the post-sanitise `#ev-NN` anchor and video-link injection (`inject_evidence_anchors`) |
| `api/routes/research_html.py` | Modify | SSR payload for `/research/{slug}`: selects the extras, injects the anchors, adds the payload keys only when present |
| `api/routes/public_v1.py` | Modify | `GET /api/v1/research/{slug}` exposes evidence, videos, corrections, writer and a composite `ai_system` |
| `api/schemas/public_v1.py` | Modify | Public schema of a paper's extras: `ResearchEvidenceRef`, `ResearchVideoRef`, `ResearchCorrectionOut`, `ResearchWriterOut` and the extended `ResearchPaperDetail` (Task 4 Step 0) |
| `api/routes/sitemap.py` | Modify | `sitemap_research`: a paper's `lastmod` is the later of its publication and its newest correction day (`_RESEARCH_SQL`) |
| `tests/api/test_sitemap_lastmod.py` | Modify | The research lastmod query and the part file that reads it |
| `ancient-nerds-map/src/seo/SanitizedMarkdownHtml.tsx` | Modify | Comment only: body_html also passes through `inject_evidence_anchors` (the nosemgrep justification) |
| `tests/pipeline/test_research_paper_extras.py` | Create | Parser and validator tests for the extras (need only A Task 2's `EVIDENCE_ID_RE`, `YOUTUBE_ID_RE` and `poster_web_path`) |
| `tests/pipeline/test_research_evidence_anchors.py` | Create | Anchor resolution and injection tests, plus the `normalize_anchor_text` contract test |
| `tests/api/test_research_html_ssr.py` | Modify | Payload contract: old papers unchanged, extras present when stored (a video's poster included), loud failures, Medium copy untouched (no anchors, no disclosure line: owner decision #23) |
| `tests/api/test_public_v1_research_extras.py` | Create | Public API detail response with and without extras |
| `ancient-nerds-map/src/types/anRoute.ts` | Modify | `ResearchVideo`, `ResearchCorrection`, `ResearchWriter` and the optional `ResearchRoute` fields |
| `ancient-nerds-map/src/components/theo/paperExtras.ts` | Create | Pure helpers shared by the components and `researchMeta` (watch/thumbnail URL, newest correction date) |
| `ancient-nerds-map/src/components/theo/PaperDisclosure.tsx` | Create | The visible AI disclosure line (`disclosureText` plus the component) |
| `ancient-nerds-map/src/components/theo/PaperCorrections.tsx` | Create | The corrections log section (links to current ids, anchors for retired ids) |
| `ancient-nerds-map/src/components/theo/PaperVideo.tsx` | Create | Click-to-play YouTube figure built on `news/InlineVideo`: our own studio thumbnail as the poster when the video has one (owner decision #13, spec §2.7), the framed posterless player when it was registered without one; never a YouTube request before the click |
| `ancient-nerds-map/src/components/theo/useEvidenceHashScroll.ts` | Create | Effect-only re-scroll to `#ev-NN` / `#corrections` once the images above have settled |
| `ancient-nerds-map/src/styles/paper-extras.css` | Create | CSS for the anchors (scroll-margin, `:target`), video chips, disclosure and corrections |
| `ancient-nerds-map/src/components/theo/PaperArticle.tsx` | Modify | Places disclosure, videos and corrections in the paper markup |
| `ancient-nerds-map/src/pages/ResearchPaperPage.tsx` | Modify | Calls `useEvidenceHashScroll()` |
| `ancient-nerds-map/src/seo/meta.ts` | Modify | `researchMeta`: `dateModified` and `video` (VideoObject) only when present |
| `ancient-nerds-map/src/seo/__tests__/fixtures.ts` | Modify | `RESEARCH_WITH_EXTRAS` fixture (handwritten; the frozen pyref files are untouched) |
| `ancient-nerds-map/src/seo/__tests__/render.test.tsx` | Modify | SSR render and storage-spy tests for the extended paper |
| `ancient-nerds-map/src/seo/__tests__/meta.test.ts` | Modify | JSON-LD tests for the extras |
| `ancient-nerds-map/src/components/theo/__tests__/paperExtras.test.ts` | Create | Helper tests |
| `ancient-nerds-map/src/components/theo/__tests__/PaperDisclosure.test.tsx` | Create | Disclosure wording and markup |
| `ancient-nerds-map/src/components/theo/__tests__/PaperCorrections.test.tsx` | Create | Corrections markup |
| `ancient-nerds-map/src/components/theo/__tests__/PaperVideo.test.tsx` | Create | Video figure markup |
| `ancient-nerds-map/src/components/theo/__tests__/useEvidenceHashScroll.test.tsx` | Create | Hook behaviour under jsdom |

Nothing is deleted.

## Interfaces this plan defines (other streams rely on them)

- `pipeline.research_html_renderer.PAPER_EXTRAS_COLUMNS`: SQL select fragment (alias `r`) for the `evidence`, `videos`, `corrections` and `writer` columns (`jsonb`, decoded by psycopg2, `None` when absent).
- `class PaperPageError(ValueError)`: the error type every validator and the resolver raise. The message names every problem.
- `paper_markdown(report: str, title: str) -> str`: the exact markdown the page renders.
- `parse_evidence(raw) -> list[{id, anchor_text, claim}]`, `parse_corrections(raw, evidence_ids: set[str]) -> list[{date, text, evidence_id, holds_anchor}]` (`holds_anchor` marks the correction that retired an id: the last entry naming an id that is no longer in `evidence_ids`), `parse_videos(raw, anchor_ids: set[str], request_id: str) -> list[{youtube_id, title, published_at, evidence_timestamps, poster}]` (`poster` is the stored web path or `None` when the video was registered without one), `parse_writer(raw) -> {model, tool, research_model, published, human_review} | None`, `paper_extras(row) -> PaperExtras` (the row needs `.id .evidence .videos .corrections .writer`: `.id` is the request id in text form, as `PAPER_SUMMARY_COLUMNS` selects it (`r.id::text AS id`) and A's `check_page` passes it; it names the only valid poster path; other attributes are ignored).
- `parse_evidence` and `parse_corrections` check every evidence id with `pipeline.lyra.theo_publishing.EVIDENCE_ID_RE.fullmatch`, and `parse_videos` checks every `youtube_id` with `pipeline.lyra.theo_publishing.YOUTUBE_ID_RE.fullmatch` and an optional `poster` against `pipeline.lyra.theo_publishing.poster_web_path(request_id, youtube_id)`, each imported inside the function. This module defines and exports none of the three: import them from `theo_publishing`.
- `resolve_evidence_anchors(html: str, evidence: list[dict]) -> dict[str, int]`: evidence id to index of the one plain `<p>` whose `normalize_anchor_text(visible text)` starts with `normalize_anchor_text(anchor_text)`; a normalised anchor shorter than `MIN_ANCHOR_CHARS` is rejected. Raises `PaperPageError("evidence anchors do not resolve to exactly one paragraph: …")` naming each entry as `<id> matches <n> paragraphs` or `<id>: anchor_text shorter than 20 characters after normalisation`.
- `inject_evidence_anchors(html, evidence, moments=None) -> str`, `VideoMoment(youtube_id, seconds, title)`, `evidence_video_moments(extras)`, `page_extras_payload(extras)`.
- Rendered HTML contract: `<p id="ev-NN" class="theo-evidence">`; further ids on the same paragraph are `<span class="theo-evidence-anchor" id="ev-NN"></span>`; video links are `<a class="theo-evidence-video" href="https://www.youtube.com/watch?v=<id>&amp;t=<s>s" …>Video at m:ss</a>`; corrections are `<section id="corrections">`, and a retired id becomes `<li id="ev-NN">`. The deep link is `https://ancientnerds.com/research/<slug>#ev-NN`.
- SSR payload (optional keys): `videos: [{youtube_id, title, published_at, poster}]` (`poster`: our own thumbnail's web path, or `null`), `corrections: [{date, text, evidence_id, holds_anchor}]`, `writer: {model, tool, research_model, published, human_review}`.
- `api.routes.public_v1.paper_detail_extras(extras, slug) -> dict`; `ResearchVideoRef.poster: str | None` (the stored web path).
- TS: `ResearchVideo` (with `poster: string | null`), `ResearchCorrection`, `ResearchWriter` (`anRoute.ts`); `youtubeWatchUrl`, `youtubeThumbnailUrl`, `latestCorrectionDate` (`paperExtras.ts`); `disclosureText` (`PaperDisclosure.tsx`); `useEvidenceHashScroll` (`useEvidenceHashScroll.ts`).

---

### Task 1: Validate the paper extras (Python)

**Prerequisite:** CS-2 is merged (`grep -cE "def normalize_anchor_text|^MIN_ANCHOR_CHARS|^EVIDENCE_ID_RE|^YOUTUBE_ID_RE|def poster_web_path" pipeline/lyra/theo_publishing.py` prints `5`). `parse_evidence` and `parse_corrections` import `EVIDENCE_ID_RE` from there, and `parse_videos` imports `YOUTUBE_ID_RE` and `poster_web_path`.

**Files:**
- Modify: `pipeline/research_html_renderer.py:1-13` (module docstring, imports), append a block at the end of the file (after `_orphan_re_with_stray`, line 163)
- Test: `tests/pipeline/test_research_paper_extras.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_research_paper_extras.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""The optional result_json keys of a Claude-written paper, validated for the page.

Studio spec 2026-09-26 §2.7/§3.7: evidence[], videos[], corrections[] and writer
sit next to the report. The paper page, the public API and the publish gate read
them through these parsers, so a malformed value fails loudly in one place
instead of rendering half a disclosure or a dead anchor. A paper without the
keys (all 31 papers published before the studio) parses to "nothing to add".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline.research_html_renderer import (
    PAPER_EXTRAS_COLUMNS,
    PaperExtras,
    PaperPageError,
    VideoMoment,
    evidence_video_moments,
    format_references_md,
    page_extras_payload,
    paper_extras,
    paper_markdown,
    parse_corrections,
    parse_evidence,
    parse_videos,
    parse_writer,
    strip_leading_title_heading,
)

WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}
# The request id as PAPER_SUMMARY_COLUMNS selects it (r.id::text). A video's
# poster is our own studio thumbnail at exactly this path (owner decision #13,
# spec §2.7: theo_publishing.poster_web_path).
REQ = "7f00aa00-0000-4000-8000-000000000000"
POSTER = f"/data/research-images/{REQ}/video_dQw4w9WgXcQ.jpg"


def _evidence(ev_id: str = "ev-01", **overrides) -> dict:
    entry = {
        "id": ev_id,
        "anchor_text": "The stone weighs about 1,000 tonnes",
        "claim": "The Stone of the Pregnant Woman weighs about 1,000 t.",
        "source_ids": ["S12"],
        "quote": "about 1,000 tonnes",
        "quote_source_id": "S12",
        "verdict": "supported",
    }
    entry.update(overrides)
    return entry


def _video(**overrides) -> dict:
    video = {
        "youtube_id": "dQw4w9WgXcQ",
        "title": "Baalbek: the 1,000-tonne question",
        "published_at": "2026-10-01T15:00:00+00:00",
        "evidence_timestamps": {"ev-01": 312},
    }
    video.update(overrides)
    return video


def _row(**overrides) -> SimpleNamespace:
    row = {"id": REQ, "evidence": None, "videos": None, "corrections": None, "writer": None}
    row.update(overrides)
    return SimpleNamespace(**row)


class TestPaperMarkdown:
    def test_is_the_title_strip_followed_by_the_reference_reflow(self):
        report = "# Baalbek\n\n## Findings\n\nText [1].\n\n## References\n\n[1] A. https://a.org\n[2] B."
        assert paper_markdown(report, "Baalbek") == format_references_md(
            strip_leading_title_heading(report, "Baalbek")
        )
        assert not paper_markdown(report, "Baalbek").startswith("# Baalbek")


class TestExtrasColumns:
    def test_selects_the_four_keys_as_jsonb(self):
        for key in ("evidence", "videos", "corrections", "writer"):
            assert f"r.result_json::jsonb->'{key}' AS {key}" in PAPER_EXTRAS_COLUMNS


class TestParseEvidence:
    def test_absent_key_means_no_evidence(self):
        assert parse_evidence(None) == []

    def test_keeps_id_anchor_and_claim(self):
        assert parse_evidence([_evidence()]) == [
            {
                "id": "ev-01",
                "anchor_text": "The stone weighs about 1,000 tonnes",
                "claim": "The Stone of the Pregnant Woman weighs about 1,000 t.",
            }
        ]

    # "ev-\u0661\u0662" is ev- plus Arabic-Indic digits: EVIDENCE_ID_RE is ASCII-only
    # (ev-[0-9]{2,}), like the page's PAPER_HASH_RE, so the page never injects
    # an id that the deep-link handler cannot match.
    @pytest.mark.parametrize(
        "bad_id", ["ev-1", "ev-01a", "EV-01", "evidence-01", "ev-\u0661\u0662", 3, None]
    )
    def test_rejects_ids_that_are_not_ev_nn(self, bad_id):
        with pytest.raises(PaperPageError, match="ev-NN"):
            parse_evidence([_evidence(bad_id)])

    def test_rejects_a_duplicate_id(self):
        with pytest.raises(PaperPageError, match="ev-01 appears twice"):
            parse_evidence([_evidence(), _evidence()])

    def test_rejects_an_empty_anchor_text(self):
        with pytest.raises(PaperPageError, match="ev-01.anchor_text"):
            parse_evidence([_evidence(anchor_text="  ")])

    def test_rejects_a_value_that_is_not_a_list_of_objects(self):
        with pytest.raises(PaperPageError, match="result_json.evidence"):
            parse_evidence({"id": "ev-01"})


class TestParseCorrections:
    def test_a_current_evidence_id_is_a_link_not_an_anchor(self):
        got = parse_corrections(
            [{"date": "2026-10-02", "text": "Quarry date re-sourced.", "evidence_id": "ev-01"}],
            {"ev-01"},
        )
        assert got == [
            {
                "date": "2026-10-02",
                "text": "Quarry date re-sourced.",
                "evidence_id": "ev-01",
                "holds_anchor": False,
            }
        ]

    def test_a_retired_id_is_held_by_the_correction_that_retired_it(self):
        # The publish gate lets an entry name an id while it is current
        # ("concerns this paragraph") and never once it is retired, so the
        # retiring entry is the last one naming it.
        got = parse_corrections(
            [
                {"date": "2026-10-02", "text": "Wording fixed.", "evidence_id": "ev-05"},
                {"date": "2026-10-04", "text": "Claim removed.", "evidence_id": "ev-05"},
            ],
            {"ev-01"},
        )
        assert [c["holds_anchor"] for c in got] == [False, True]

    def test_evidence_id_may_be_absent(self):
        got = parse_corrections([{"date": "2026-10-02", "text": "Typo in a date."}], set())
        assert got[0]["evidence_id"] is None
        assert got[0]["holds_anchor"] is False

    @pytest.mark.parametrize("day", ["2026-10-2", "02.10.2026", "2026-10-02T10:00:00", None])
    def test_rejects_a_date_that_is_not_yyyy_mm_dd(self, day):
        with pytest.raises(PaperPageError, match="YYYY-MM-DD"):
            parse_corrections([{"date": day, "text": "x"}], set())

    def test_rejects_an_impossible_day(self):
        with pytest.raises(PaperPageError, match="not a calendar day"):
            parse_corrections([{"date": "2026-02-30", "text": "x"}], set())

    def test_rejects_a_malformed_evidence_id(self):
        with pytest.raises(PaperPageError, match="evidence_id must look like ev-NN"):
            parse_corrections([{"date": "2026-10-02", "text": "x", "evidence_id": "5"}], set())

    def test_rejects_an_empty_text(self):
        with pytest.raises(PaperPageError, match=r"corrections\[0\].text"):
            parse_corrections([{"date": "2026-10-02", "text": ""}], set())


class TestParseVideos:
    def test_keeps_the_fields_the_page_and_api_need(self):
        got = parse_videos([_video()], {"ev-01"}, REQ)
        assert got == [
            {
                "youtube_id": "dQw4w9WgXcQ",
                "title": "Baalbek: the 1,000-tonne question",
                "published_at": "2026-10-01T15:00:00+00:00",
                "evidence_timestamps": {"ev-01": 312},
                # Registered without a poster: a valid state, the page then
                # shows the posterless player (owner decision #13).
                "poster": None,
            }
        ]

    def test_keeps_our_own_poster(self):
        got = parse_videos([_video(poster=POSTER)], {"ev-01"}, REQ)
        assert got[0]["poster"] == POSTER

    @pytest.mark.parametrize(
        "poster",
        [
            "/data/research-images/99999999-8888-7777-6666-555555555555/video_dQw4w9WgXcQ.jpg",
            f"/data/research-images/{REQ}/video_aaaaaaaaaaa.jpg",
            f"/data/research-images/{REQ}/thumbnail_1.jpg",
            f"/data/research-images/{REQ}/video_dQw4w9WgXcQ.png",
            f"https://ancientnerds.com/data/research-images/{REQ}/video_dQw4w9WgXcQ.jpg",
            "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "",
            None,
        ],
    )
    def test_rejects_any_poster_but_the_video_path(self, poster):
        with pytest.raises(PaperPageError, match=r"videos\[0\]\.poster must be " + POSTER):
            parse_videos([_video(poster=poster)], {"ev-01"}, REQ)

    @pytest.mark.parametrize("youtube_id", ["dQw4w9WgXc", "dQw4w9WgXcQQ", "dQw4w9WgX<Q", None])
    def test_rejects_a_malformed_youtube_id(self, youtube_id):
        with pytest.raises(PaperPageError, match="youtube_id"):
            parse_videos([_video(youtube_id=youtube_id)], {"ev-01"}, REQ)

    def test_rejects_a_timestamp_for_an_unknown_evidence_id(self):
        with pytest.raises(PaperPageError, match="neither an evidence id nor retired"):
            parse_videos([_video(evidence_timestamps={"ev-09": 10})], {"ev-01"}, REQ)

    @pytest.mark.parametrize("seconds", [-1, 1.5, "312", True])
    def test_rejects_a_timestamp_that_is_not_whole_seconds(self, seconds):
        with pytest.raises(PaperPageError, match="whole seconds"):
            parse_videos([_video(evidence_timestamps={"ev-01": seconds})], {"ev-01"}, REQ)

    def test_rejects_a_published_at_that_is_not_iso(self):
        with pytest.raises(PaperPageError, match="ISO 8601"):
            parse_videos([_video(published_at="1 Oct 2026")], {"ev-01"}, REQ)

    def test_rejects_missing_evidence_timestamps(self):
        video = _video()
        del video["evidence_timestamps"]
        with pytest.raises(PaperPageError, match="evidence_timestamps"):
            parse_videos([video], {"ev-01"}, REQ)


class TestParseWriter:
    def test_absent_key_means_an_older_paper(self):
        assert parse_writer(None) is None

    def test_keeps_exactly_the_five_disclosure_fields(self):
        assert parse_writer({**WRITER, "brief_version": 3}) == WRITER

    def test_rejects_an_unknown_publication_mode(self):
        with pytest.raises(PaperPageError, match="writer.published"):
            parse_writer({**WRITER, "published": "auto"})

    def test_rejects_a_human_review_that_is_not_a_boolean(self):
        with pytest.raises(PaperPageError, match="human_review"):
            parse_writer({**WRITER, "human_review": "no"})

    def test_rejects_a_missing_model(self):
        with pytest.raises(PaperPageError, match="writer.model"):
            parse_writer({k: v for k, v in WRITER.items() if k != "model"})


class TestPaperExtras:
    def test_an_older_paper_has_nothing_to_add(self):
        assert paper_extras(_row()) == PaperExtras([], [], [], None)

    def test_a_video_may_keep_the_timestamp_of_a_retired_id(self):
        extras = paper_extras(
            _row(
                evidence=[_evidence("ev-01")],
                corrections=[{"date": "2026-10-04", "text": "Removed.", "evidence_id": "ev-05"}],
                videos=[_video(evidence_timestamps={"ev-01": 312, "ev-05": 400})],
            )
        )
        assert extras.corrections[0]["holds_anchor"] is True
        assert extras.videos[0]["evidence_timestamps"] == {"ev-01": 312, "ev-05": 400}

    def test_a_video_timing_an_id_nobody_knows_fails(self):
        with pytest.raises(PaperPageError, match="ev-05"):
            paper_extras(
                _row(
                    evidence=[_evidence("ev-01")],
                    videos=[_video(evidence_timestamps={"ev-05": 400})],
                )
            )

    def test_the_poster_path_is_the_rows_own_request_id(self):
        row = _row(evidence=[_evidence()], videos=[_video(poster=POSTER)])
        assert paper_extras(row).videos[0]["poster"] == POSTER
        other = "99999999-8888-7777-6666-555555555555"
        with pytest.raises(PaperPageError, match=r"videos\[0\]\.poster"):
            paper_extras(_row(id=other, evidence=[_evidence()], videos=[_video(poster=POSTER)]))


class TestEvidenceVideoMoments:
    def test_links_only_current_evidence_in_video_order(self):
        extras = paper_extras(
            _row(
                evidence=[_evidence("ev-01"), _evidence("ev-02", anchor_text="Other text")],
                corrections=[{"date": "2026-10-04", "text": "Removed.", "evidence_id": "ev-05"}],
                videos=[
                    _video(evidence_timestamps={"ev-01": 312, "ev-05": 400}),
                    _video(
                        youtube_id="aaaaaaaaaaa",
                        title="Short",
                        evidence_timestamps={"ev-01": 20, "ev-02": 45},
                    ),
                ],
            )
        )
        assert evidence_video_moments(extras) == {
            "ev-01": [
                VideoMoment("dQw4w9WgXcQ", 312, "Baalbek: the 1,000-tonne question"),
                VideoMoment("aaaaaaaaaaa", 20, "Short"),
            ],
            "ev-02": [VideoMoment("aaaaaaaaaaa", 45, "Short")],
        }


class TestPageExtrasPayload:
    def test_an_older_paper_adds_no_key(self):
        assert page_extras_payload(PaperExtras([], [], [], None)) == {}

    def test_each_key_appears_only_when_present(self):
        only_writer = page_extras_payload(PaperExtras([], [], [], dict(WRITER)))
        assert only_writer == {"writer": WRITER}

    def test_the_video_payload_carries_no_timestamps(self):
        extras = paper_extras(_row(evidence=[_evidence()], videos=[_video()]))
        assert page_extras_payload(extras) == {
            "videos": [
                {
                    "youtube_id": "dQw4w9WgXcQ",
                    "title": "Baalbek: the 1,000-tonne question",
                    "published_at": "2026-10-01T15:00:00+00:00",
                    "poster": None,
                }
            ]
        }

    def test_the_video_payload_carries_our_poster(self):
        extras = paper_extras(_row(evidence=[_evidence()], videos=[_video(poster=POSTER)]))
        assert page_extras_payload(extras)["videos"][0]["poster"] == POSTER
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_research_paper_extras.py -m "not integration and not live_llm" -q`
Expected: collection error, `ImportError: cannot import name 'PAPER_EXTRAS_COLUMNS' from 'pipeline.research_html_renderer'`.

- [ ] **Step 3: Update the module docstring and imports**

In `pipeline/research_html_renderer.py`, replace lines 1-13:

```python
"""
Markdown preparation for the public research papers.

The paper pages themselves render through React since the react-ssr
cutover (Task 12; Task 16 deleted the full-document renderers that lived
here). What stays Python is the stored-markdown massaging shared by the
paper route and its Medium copy (api/routes/research_html.py): reference
reflow, leading-title stripping and the Medium-safe caption rewrite.
"""

import re

from pipeline.lyra.theo_image_captions import _META_VOICE_RE
```

with:

```python
"""
Markdown preparation and post-render steps for the public research papers.

The paper pages themselves render through React since the react-ssr
cutover (Task 12; Task 16 deleted the full-document renderers that lived
here). What stays Python is the stored-markdown massaging shared by the
paper route and its Medium copy (api/routes/research_html.py): reference
reflow, leading-title stripping and the Medium-safe caption rewrite. Since
the studio (spec 2026-09-26 §2.7/§3.7) it also validates the optional
evidence/videos/corrections/writer keys of a Claude-written paper and
injects the #ev-NN evidence anchors into the rendered body.

Module-level imports stay stdlib-only: static_exporter and the landing
route import PUBLIC_PAPER_WHERE from here. What comes from
pipeline.lyra.theo_publishing (EVIDENCE_ID_RE, YOUTUBE_ID_RE,
poster_web_path, normalize_anchor_text, MIN_ANCHOR_CHARS) is imported
inside the functions that use it.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, NamedTuple

from pipeline.lyra.theo_image_captions import _META_VOICE_RE
```

- [ ] **Step 4: Append the extras block to the end of the file**

Append after `_orphan_re_with_stray` (the current last function):

```python


def paper_markdown(report: str, title: str) -> str:
    """The stored report, prepared for rendering: the leading title heading
    stripped and the References reflowed (the two helpers above).

    One definition for the paper page, its Medium copy and the publish gate's
    evidence-anchor check, so the gate resolves anchors against exactly the
    HTML the page will serve.
    """
    return format_references_md(strip_leading_title_heading(report, title))


# ── Claude-written papers: evidence, videos, corrections, writer ─────────────
# Studio spec 2026-09-26 §2.7/§3.7. Four optional result_json keys sit next to
# the report: evidence[] (checkable claims, each tied to one paragraph by its
# anchor_text), videos[] (registered YouTube videos, the second each evidence
# paragraph appears at and, optionally, our own poster image), corrections[]
# (the public log) and writer (who wrote and published the paper, the source
# of the AI disclosure line).
# The evidence stays out of the markdown on purpose: the citation gate, TTS,
# the Qdrant index and the CC BY API all read the report text, and none of
# them should see anchor syntax. Papers without these keys render as before.

# Selected next to PAPER_SUMMARY_COLUMNS (api/routes/public_v1.py) wherever a
# single paper is read. jsonb `->` hands psycopg2 a decoded list/dict, and
# NULL (key absent) arrives as None.
PAPER_EXTRAS_COLUMNS = """
    r.result_json::jsonb->'evidence' AS evidence,
    r.result_json::jsonb->'videos' AS videos,
    r.result_json::jsonb->'corrections' AS corrections,
    r.result_json::jsonb->'writer' AS writer
"""

# Evidence ids ("ev-NN") are linked from video descriptions forever: never
# renumbered, retired only by a correction that names them (spec §2.7). Their
# format is pipeline.lyra.theo_publishing.EVIDENCE_ID_RE, the one definition the
# publish gate, this page, the studio's local check and the case file share;
# parse_evidence and parse_corrections import it inside the function. A video's
# id format is theo_publishing.YOUTUBE_ID_RE and its poster's path
# theo_publishing.poster_web_path, both imported by parse_videos.
_ISO_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_WRITER_PUBLISHED = ("automatic", "manual")


class PaperPageError(ValueError):
    """A paper's result_json extras cannot be rendered as stored.

    Raised, never swallowed: the publish gate runs the same checks before a
    paper goes public, so meeting this on a page means gate and page disagree,
    which is a bug to fix rather than a state to paper over.
    """


class VideoMoment(NamedTuple):
    """One "video at m:ss" link: where in which video an evidence paragraph is shown."""

    youtube_id: str
    seconds: int
    title: str


@dataclass(frozen=True)
class PaperExtras:
    """The validated optional keys of one paper (see parse_* below)."""

    evidence: list[dict[str, Any]]
    videos: list[dict[str, Any]]
    corrections: list[dict[str, Any]]
    writer: dict[str, Any] | None


def _text_field(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaperPageError(f"{where} must be a non-empty string, got {value!r}")
    return value


def _objects(value: Any, key: str) -> list[dict[str, Any]]:
    """A list of JSON objects; None means the paper has no such key."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise PaperPageError(f"result_json.{key} must be a list of objects, got {value!r}")
    return value


def parse_evidence(raw: Any) -> list[dict[str, Any]]:
    """result_json.evidence -> [{id, anchor_text, claim}] with unique ev-NN ids."""
    # Imported here, not at module level: the light importers of this module
    # (static_exporter, the landing route) never need the publish module, and
    # theo_publishing's gates import this module back.
    from pipeline.lyra.theo_publishing import EVIDENCE_ID_RE

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, item in enumerate(_objects(raw, "evidence")):
        ev_id = item.get("id")
        if not isinstance(ev_id, str) or not EVIDENCE_ID_RE.fullmatch(ev_id):
            raise PaperPageError(f"evidence[{i}].id must look like ev-NN, got {ev_id!r}")
        if ev_id in seen:
            raise PaperPageError(f"evidence id {ev_id} appears twice")
        seen.add(ev_id)
        entries.append(
            {
                "id": ev_id,
                "anchor_text": _text_field(item.get("anchor_text"), f"{ev_id}.anchor_text"),
                "claim": _text_field(item.get("claim"), f"{ev_id}.claim"),
            }
        )
    return entries


def parse_corrections(raw: Any, evidence_ids: set[str]) -> list[dict[str, Any]]:
    """result_json.corrections -> [{date, text, evidence_id, holds_anchor}].

    A correction may name the evidence paragraph it concerns. When that id is
    no longer among the paper's evidence, a correction retired it: the last
    entry naming it (the publish gate lets earlier entries name the id only
    while it was current, and never lets anyone name it once retired). That
    entry carries the id itself (holds_anchor): a video description that links
    #ev-NN then lands on the correction that explains the change instead of
    nowhere.
    """
    # Lazy for the same reason as in parse_evidence.
    from pipeline.lyra.theo_publishing import EVIDENCE_ID_RE

    entries: list[dict[str, Any]] = []
    for i, item in enumerate(_objects(raw, "corrections")):
        day = item.get("date")
        if not isinstance(day, str) or not _ISO_DAY_RE.fullmatch(day):
            raise PaperPageError(f"corrections[{i}].date must be YYYY-MM-DD, got {day!r}")
        try:
            date.fromisoformat(day)
        except ValueError as exc:
            raise PaperPageError(f"corrections[{i}].date {day!r} is not a calendar day") from exc
        ev_id = item.get("evidence_id")
        if ev_id is not None and (
            not isinstance(ev_id, str) or not EVIDENCE_ID_RE.fullmatch(ev_id)
        ):
            raise PaperPageError(
                f"corrections[{i}].evidence_id must look like ev-NN, got {ev_id!r}"
            )
        entries.append(
            {
                "date": day,
                "text": _text_field(item.get("text"), f"corrections[{i}].text"),
                "evidence_id": ev_id,
                "holds_anchor": False,
            }
        )
    anchored: set[str] = set()
    for entry in reversed(entries):
        ev_id = entry["evidence_id"]
        if ev_id is not None and ev_id not in evidence_ids and ev_id not in anchored:
            entry["holds_anchor"] = True
            anchored.add(ev_id)
    return entries


def parse_videos(raw: Any, anchor_ids: set[str], request_id: str) -> list[dict[str, Any]]:
    """result_json.videos -> [{youtube_id, title, published_at, evidence_timestamps, poster}].

    anchor_ids are the ids a timestamp may name: the current evidence ids plus
    the ids retired by a correction (a video published before the correction
    keeps its timestamps). `poster` is our own studio thumbnail (owner
    decision #13, spec §2.7), stored only when the video was registered with
    one and then exactly theo_publishing.poster_web_path(request_id,
    youtube_id); the page draws it from our server inside the click-to-play
    link. None means the video was registered without one, a valid state:
    the page shows the posterless player. Either way the page loads nothing
    from YouTube before the click.
    """
    # Lazy for the same reason as in parse_evidence.
    from pipeline.lyra.theo_publishing import YOUTUBE_ID_RE, poster_web_path

    entries: list[dict[str, Any]] = []
    for i, item in enumerate(_objects(raw, "videos")):
        youtube_id = item.get("youtube_id")
        if not isinstance(youtube_id, str) or not YOUTUBE_ID_RE.fullmatch(youtube_id):
            raise PaperPageError(f"videos[{i}].youtube_id must be a YouTube id, got {youtube_id!r}")
        poster = item.get("poster")
        if "poster" in item:
            expected = poster_web_path(request_id, youtube_id)
            if poster != expected:
                raise PaperPageError(f"videos[{i}].poster must be {expected}, got {poster!r}")
        published_at = _text_field(item.get("published_at"), f"videos[{i}].published_at")
        try:
            datetime.fromisoformat(published_at)
        except ValueError as exc:
            raise PaperPageError(
                f"videos[{i}].published_at {published_at!r} is not ISO 8601"
            ) from exc
        stamps = item.get("evidence_timestamps")
        if not isinstance(stamps, dict):
            raise PaperPageError(f"videos[{i}].evidence_timestamps must be an object")
        for ev_id, seconds in stamps.items():
            if ev_id not in anchor_ids:
                raise PaperPageError(
                    f"videos[{i}] times {ev_id!r}, which is neither an evidence id "
                    "nor retired by a correction"
                )
            if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
                raise PaperPageError(f"videos[{i}] time for {ev_id} must be whole seconds >= 0")
        entries.append(
            {
                "youtube_id": youtube_id,
                "title": _text_field(item.get("title"), f"videos[{i}].title"),
                "published_at": published_at,
                "evidence_timestamps": dict(stamps),
                "poster": poster,
            }
        )
    return entries


def parse_writer(raw: Any) -> dict[str, Any] | None:
    """result_json.writer -> the five disclosure fields, or None for older papers."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PaperPageError(f"result_json.writer must be an object, got {raw!r}")
    published = raw.get("published")
    if published not in _WRITER_PUBLISHED:
        raise PaperPageError(
            f"writer.published must be one of {_WRITER_PUBLISHED}, got {published!r}"
        )
    human_review = raw.get("human_review")
    if not isinstance(human_review, bool):
        raise PaperPageError(f"writer.human_review must be true or false, got {human_review!r}")
    return {
        "model": _text_field(raw.get("model"), "writer.model"),
        "tool": _text_field(raw.get("tool"), "writer.tool"),
        "research_model": _text_field(raw.get("research_model"), "writer.research_model"),
        "published": published,
        "human_review": human_review,
    }


def paper_extras(row: Any) -> PaperExtras:
    """Validate a paper row's PAPER_EXTRAS_COLUMNS in one pass.

    row.id is the request id in text form, as PAPER_SUMMARY_COLUMNS selects it
    (r.id::text) and the publish gate's check_page passes it: it names the one
    valid poster path of each video. Other attributes are ignored.
    """
    evidence = parse_evidence(row.evidence)
    current = {entry["id"] for entry in evidence}
    corrections = parse_corrections(row.corrections, current)
    retired = {c["evidence_id"] for c in corrections if c["holds_anchor"]}
    videos = parse_videos(row.videos, current | retired, row.id)
    return PaperExtras(evidence, videos, corrections, parse_writer(row.writer))


def evidence_video_moments(extras: PaperExtras) -> dict[str, list[VideoMoment]]:
    """ev id -> its moments in the paper's videos, in video order.

    Only current evidence ids get a link: a retired id has no paragraph left,
    its anchor lives on the correction that retired it.
    """
    current = {entry["id"] for entry in extras.evidence}
    moments: dict[str, list[VideoMoment]] = {}
    for video in extras.videos:
        for ev_id, seconds in video["evidence_timestamps"].items():
            if ev_id in current:
                moments.setdefault(ev_id, []).append(
                    VideoMoment(video["youtube_id"], seconds, video["title"])
                )
    return moments


def page_extras_payload(extras: PaperExtras) -> dict[str, Any]:
    """The SSR payload keys for the extras, each present only when the paper has it.

    An older paper gets {}, so its route payload stays byte-identical to the
    one before this feature (ResearchRoute declares the keys optional). A
    video's poster is its web path or None (ResearchVideo.poster).
    """
    payload: dict[str, Any] = {}
    if extras.videos:
        payload["videos"] = [
            {key: video[key] for key in ("youtube_id", "title", "published_at", "poster")}
            for video in extras.videos
        ]
    if extras.corrections:
        payload["corrections"] = extras.corrections
    if extras.writer is not None:
        payload["writer"] = extras.writer
    return payload
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_research_paper_extras.py -m "not integration and not live_llm" -q`
Expected: `59 passed`.

Then run: `./.venv/Scripts/python.exe -m ruff check pipeline/research_html_renderer.py && ./.venv/Scripts/python.exe -m ruff format --check pipeline/research_html_renderer.py && ./.venv/Scripts/python.exe -m vulture pipeline/research_html_renderer.py .vulture_whitelist.py --min-confidence 80`
Expected: `All checks passed!`, `1 file already formatted`, no vulture output.

- [ ] **Step 6: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add pipeline/research_html_renderer.py tests/pipeline/test_research_paper_extras.py
git commit -m "Validate a Claude-written paper's evidence, videos, corrections and writer record for the paper page" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- pipeline/research_html_renderer.py tests/pipeline/test_research_paper_extras.py
```

---

### Task 2: Inject the evidence anchors after sanitising (Python)

**Prerequisite:** CS-2 is merged (`grep -cE "def normalize_anchor_text|^MIN_ANCHOR_CHARS|^EVIDENCE_ID_RE|^YOUTUBE_ID_RE|def poster_web_path" pipeline/lyra/theo_publishing.py` prints `5`; Task 1 already needed it).

**Files:**
- Modify: `pipeline/research_html_renderer.py` (one import line; append a block at the end)
- Test: `tests/pipeline/test_research_evidence_anchors.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_research_evidence_anchors.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""#ev-NN anchors on the research paper page (studio spec 2026-09-26 §2.7, §4.5).

Video descriptions deep-link claims as /research/{slug}#ev-NN, and the studio
captures the paper scrolled to them. nh3 strips id attributes from the markdown
output, so the anchors are injected into the finished HTML, the way
_heading_anchors restores h2/h3 ids. The paragraph is the one whose text opens
with the evidence entry's anchor_text, compared through normalize_anchor_text
(pipeline/lyra/theo_publishing, stream A: the publish gate's contract C9), and
these tests also pin the one property of that function the page relies on: a
markdown paragraph and its rendered text normalise to the same key.
"""

from __future__ import annotations

import pytest

from pipeline.article_html_renderer import markdown_to_html
from pipeline.lyra.theo_publishing import MIN_ANCHOR_CHARS, normalize_anchor_text
from pipeline.research_html_renderer import (
    PaperPageError,
    VideoMoment,
    _paragraph_text,
    inject_evidence_anchors,
    paper_markdown,
    resolve_evidence_anchors,
)

REPORT = (
    "## The Quarry\n\n"
    'The "Stone of the Pregnant Woman" weighs about 1,000 tonnes -- roughly the mass of '
    "*three* jumbo jets [1] [2].\n\n"
    "Ruprechtsberger's team dated the quarry face to the 1st century AD... "
    "a date others dispute [3].\n\n"
    "## References\n\n"
    "[1] Doe, J. (2020). Baalbek quarries. https://example.org/paper\n"
)
# An anchor is the opening of its paragraph; two entries may open the same one.
EVIDENCE = [
    {"id": "ev-01", "anchor_text": 'The "Stone of the Pregnant Woman" weighs about 1,000 tonnes -- roughly'},
    {"id": "ev-02", "anchor_text": "Ruprechtsberger's team dated the quarry face"},
    {"id": "ev-03", "anchor_text": "Ruprechtsberger's team dated the quarry face to the 1st"},
]
MOMENTS = {"ev-01": [VideoMoment("dQw4w9WgXcQ", 312, "Baalbek: the 1,000-tonne question")]}
NOWHERE = {"id": "ev-07", "anchor_text": "Machu Picchu was built by the Inca"}
TOO_SHORT = {"id": "ev-08", "anchor_text": "the"}

P1 = (
    "The \u201cStone of the Pregnant Woman\u201d weighs about 1,000 tonnes \u2013 roughly "
    "the mass of <em>three</em> jumbo jets [1] [2]."
)
P2 = (
    "Ruprechtsberger\u2019s team dated the quarry face to the 1st century AD\u2026 "
    "a date others dispute [3]."
)
REFS = (
    '<h2 id="references">References</h2>\n'
    '<p>[1] Doe, J. (2020). Baalbek quarries. <a href="https://example.org/paper" '
    'rel="noopener noreferrer" target="_blank">https://example.org/paper</a></p>'
)
VIDEO_LINK = (
    ' <a class="theo-evidence-video" '
    'href="https://www.youtube.com/watch?v=dQw4w9WgXcQ&amp;t=312s" target="_blank" '
    'rel="noopener noreferrer" '
    'title="Watch this passage in the video: Baalbek: the 1,000-tonne question">'
    "Video at 5:12</a>"
)


def rendered() -> str:
    return markdown_to_html(paper_markdown(REPORT, "Baalbek"))


class TestNormalizeAnchorTextContract:
    """What the page needs from stream A's normalize_anchor_text."""

    @pytest.mark.parametrize(
        "paragraph",
        [
            'The "Stone" weighs 1,000 tonnes -- or --- so [1].',
            "Ruprechtsberger's team dated it to the 1st century AD... others dispute it [3].",
            "A paragraph with a [linked source](https://example.org/x) and **strong** words [4].",
            "It is *very likely* that the blocks were moved on sledges & rollers [5].",
            "Two   spaces\nand a soft line break stay one space [6].",
            "See <https://example.org/x> for the survey [8].",
            "A backslash \\*escaped\\* star [9].",
            "Aa &amp; bb [12].",
        ],
    )
    def test_markdown_and_its_rendered_text_share_one_key(self, paragraph):
        inner = markdown_to_html(paragraph, toc=False).removeprefix("<p>").removesuffix("</p>")
        assert normalize_anchor_text(paragraph) == normalize_anchor_text(_paragraph_text(inner))


class TestResolveEvidenceAnchors:
    def test_maps_each_id_to_its_paragraph_index(self):
        # <p> order in the rendered body: P1, P2, the reference line.
        assert resolve_evidence_anchors(rendered(), EVIDENCE) == {"ev-01": 0, "ev-02": 1, "ev-03": 1}

    def test_an_anchor_found_nowhere_fails(self):
        with pytest.raises(PaperPageError, match="ev-07 matches 0 paragraphs"):
            resolve_evidence_anchors(rendered(), [NOWHERE])

    def test_an_anchor_from_the_middle_of_a_paragraph_does_not_resolve(self):
        # Contract C9: the paragraph must START WITH the anchor, as the
        # writer brief asks ("anchor_text is the opening of that paragraph").
        with pytest.raises(PaperPageError, match="ev-09 matches 0 paragraphs"):
            resolve_evidence_anchors(
                rendered(), [{"id": "ev-09", "anchor_text": "a date others dispute"}]
            )

    def test_an_opening_that_recurs_inside_another_paragraph_still_resolves(self):
        html = markdown_to_html(
            "The Stone of the Pregnant Woman weighs roughly 1,000 tonnes [1].\n\n"
            "In fact the Stone of the Pregnant Woman weighs roughly as much as three jets [2].",
            toc=False,
        )
        anchor = {"id": "ev-01", "anchor_text": "The Stone of the Pregnant Woman weighs roughly"}
        assert resolve_evidence_anchors(html, [anchor]) == {"ev-01": 0}

    def test_an_anchor_opening_two_paragraphs_fails(self):
        html = markdown_to_html(
            "Roman engineers moved blocks with capstans [1].\n\n"
            "Roman engineers moved blocks with ramps too [2].",
            toc=False,
        )
        with pytest.raises(PaperPageError, match="ev-08 matches 2 paragraphs"):
            resolve_evidence_anchors(
                html, [{"id": "ev-08", "anchor_text": "Roman engineers moved blocks"}]
            )

    def test_an_anchor_shorter_than_the_minimum_fails(self):
        with pytest.raises(
            PaperPageError,
            match=f"ev-08: anchor_text shorter than {MIN_ANCHOR_CHARS} characters after normalisation",
        ):
            resolve_evidence_anchors(rendered(), [TOO_SHORT])

    def test_every_unresolved_entry_is_named_at_once(self):
        with pytest.raises(PaperPageError) as err:
            resolve_evidence_anchors(rendered(), [NOWHERE, TOO_SHORT])
        assert "ev-07" in str(err.value) and "ev-08" in str(err.value)


class TestInjectEvidenceAnchors:
    def test_exact_markup_for_the_fixture_paper(self):
        assert inject_evidence_anchors(rendered(), EVIDENCE, MOMENTS) == (
            '<h2 id="the-quarry">The Quarry</h2>\n'
            f'<p id="ev-01" class="theo-evidence">{P1}{VIDEO_LINK}</p>\n'
            '<p id="ev-02" class="theo-evidence">'
            f'<span class="theo-evidence-anchor" id="ev-03"></span>{P2}</p>\n'
            f"{REFS}"
        )

    def test_a_paper_without_evidence_is_returned_unchanged(self):
        html = rendered()
        assert inject_evidence_anchors(html, [], {}) == html

    def test_anchors_survive_only_because_they_are_injected_after_nh3(self):
        # attr_list ids in the markdown are stripped by the sanitizer ...
        assert 'id="ev-01"' not in markdown_to_html("A claim [1].\n{: #ev-01 }")
        # ... while the injected ones are in the served HTML.
        assert 'id="ev-01"' in inject_evidence_anchors(rendered(), EVIDENCE[:1])

    def test_markdown_to_html_itself_never_adds_evidence_ids(self):
        # Journals and the Medium copy share markdown_to_html: the anchors are
        # a research-page step only.
        assert "theo-evidence" not in rendered()

    def test_video_time_past_an_hour_reads_h_mm_ss(self):
        html = inject_evidence_anchors(
            rendered(), EVIDENCE[:1], {"ev-01": [VideoMoment("dQw4w9WgXcQ", 3725, "Long")]}
        )
        assert "&amp;t=3725s" in html
        assert "Video at 1:02:05</a>" in html

    def test_the_same_moment_named_by_two_ids_of_one_paragraph_links_once(self):
        moment = VideoMoment("dQw4w9WgXcQ", 400, "V")
        html = inject_evidence_anchors(
            rendered(), EVIDENCE[1:], {"ev-02": [moment], "ev-03": [moment]}
        )
        assert html.count("Video at 6:40") == 1

    def test_the_video_title_is_escaped_in_the_attribute(self):
        html = inject_evidence_anchors(
            rendered(), EVIDENCE[:1], {"ev-01": [VideoMoment("dQw4w9WgXcQ", 1, 'A "quoted" <b>')]}
        )
        assert 'title="Watch this passage in the video: A &quot;quoted&quot; &lt;b&gt;"' in html

    def test_unresolvable_evidence_raises_instead_of_dropping_the_anchor(self):
        with pytest.raises(PaperPageError, match="ev-07 matches 0 paragraphs"):
            inject_evidence_anchors(rendered(), [NOWHERE])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_research_evidence_anchors.py -m "not integration and not live_llm" -q`
Expected: collection error, `ImportError: cannot import name '_paragraph_text' from 'pipeline.research_html_renderer'`. If the error names `pipeline.lyra.theo_publishing` instead, CS-2 is not merged yet: stop and follow "Dependencies and order".

- [ ] **Step 3: Add the html import**

In `pipeline/research_html_renderer.py`, replace:

```python
from datetime import date, datetime
from typing import Any, NamedTuple
```

with:

```python
from datetime import date, datetime
from html import escape, unescape
from typing import Any, NamedTuple
```

- [ ] **Step 4: Append the anchor block to the end of the file**

Append after `page_extras_payload` (added in Task 1):

```python


# ── Evidence anchors in the rendered body ────────────────────────────────────
# nh3 drops every id attribute (article_html_renderer._sanitize_html), so the
# anchors are added to the finished HTML, like _heading_anchors does for h2/h3.
# Only research pages call this; journals and the Medium copy never see it.
# The additions are built from regex-validated ids, a regex-validated YouTube
# id, integer seconds and an html-escaped title, never from raw input.

_PARAGRAPH_RE = re.compile(r"<p>(.*?)</p>", re.DOTALL)
_BR_RE = re.compile(r"<br\s*/?>")
_TAG_RE = re.compile(r"<[^>]+>")


def _paragraph_text(inner_html: str) -> str:
    """The visible text of a paragraph's inner HTML: tags dropped, entities decoded."""
    return unescape(_TAG_RE.sub("", _BR_RE.sub(" ", inner_html)))


def resolve_evidence_anchors(html: str, evidence: list[dict[str, Any]]) -> dict[str, int]:
    """ev id -> index of the one plain <p> of `html` whose text opens with its anchor_text.

    The rule is contract C9 of the publish gate (pipeline/lyra/theo_publishing):
    both sides go through normalize_anchor_text, which maps the markdown a
    writer copies an anchor from and the smartypants-rendered paragraph text
    to the same key; the normalised anchor must be at least MIN_ANCHOR_CHARS
    long, and exactly one paragraph's normalised text may START WITH it.
    Several entries may open the same paragraph. Raises PaperPageError naming
    every entry that is too short or matches zero or several paragraphs.
    """
    # Imported here, not at module level: the light importers of this module
    # (static_exporter, the landing route) never need the publish module, and
    # theo_publishing's gates import this module back.
    from pipeline.lyra.theo_publishing import MIN_ANCHOR_CHARS, normalize_anchor_text

    texts = [
        normalize_anchor_text(_paragraph_text(match.group(1)))
        for match in _PARAGRAPH_RE.finditer(html)
    ]
    found: dict[str, int] = {}
    problems: list[str] = []
    for entry in evidence:
        ev_id = entry["id"]
        key = normalize_anchor_text(entry["anchor_text"])
        if len(key) < MIN_ANCHOR_CHARS:
            problems.append(
                f"{ev_id}: anchor_text shorter than {MIN_ANCHOR_CHARS} characters after normalisation"
            )
            continue
        hits = [index for index, text in enumerate(texts) if text.startswith(key)]
        if len(hits) == 1:
            found[ev_id] = hits[0]
        else:
            problems.append(f"{ev_id} matches {len(hits)} paragraphs")
    if problems:
        raise PaperPageError(
            "evidence anchors do not resolve to exactly one paragraph: " + "; ".join(problems)
        )
    return found


def _clock(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _video_link(moment: VideoMoment) -> str:
    url = f"https://www.youtube.com/watch?v={moment.youtube_id}&amp;t={moment.seconds}s"
    title = escape(f"Watch this passage in the video: {moment.title}", quote=True)
    return (
        f' <a class="theo-evidence-video" href="{url}" target="_blank" '
        f'rel="noopener noreferrer" title="{title}">Video at {_clock(moment.seconds)}</a>'
    )


def inject_evidence_anchors(
    html: str,
    evidence: list[dict[str, Any]],
    moments: dict[str, list[VideoMoment]] | None = None,
) -> str:
    """Give each evidence paragraph its id="ev-NN" (and a video link per moment).

    The first evidence id of a paragraph becomes the <p>'s id; further ids of
    the same paragraph get an empty <span class="theo-evidence-anchor"> at its
    start (an element carries one id). The class theo-evidence is the CSS hook
    for scroll-margin-top and :target (paper-extras.css). A paper without
    evidence gets `html` back unchanged.
    """
    if not evidence:
        return html
    where = resolve_evidence_anchors(html, evidence)
    by_id = moments or {}
    ids_at: dict[int, list[str]] = {}
    for entry in evidence:
        ids_at.setdefault(where[entry["id"]], []).append(entry["id"])
    parts: list[str] = []
    pos = 0
    for index, match in enumerate(_PARAGRAPH_RE.finditer(html)):
        ids = ids_at.get(index)
        if ids is None:
            continue
        first, *extra = ids
        spans = "".join(f'<span class="theo-evidence-anchor" id="{ev}"></span>' for ev in extra)
        links: list[str] = []
        seen: set[tuple[str, int]] = set()
        for ev_id in ids:
            for moment in by_id.get(ev_id, ()):
                if (moment.youtube_id, moment.seconds) not in seen:
                    seen.add((moment.youtube_id, moment.seconds))
                    links.append(_video_link(moment))
        parts.append(html[pos : match.start()])
        parts.append(
            f'<p id="{first}" class="theo-evidence">{spans}{match.group(1)}{"".join(links)}</p>'
        )
        pos = match.end()
    parts.append(html[pos:])
    return "".join(parts)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/pipeline/test_research_evidence_anchors.py tests/pipeline/test_research_paper_extras.py tests/pipeline/test_article_figures.py -m "not integration and not live_llm" -q`
Expected: `95 passed` (23 + 59 + 13).

If `TestNormalizeAnchorTextContract` fails, stream A's `normalize_anchor_text` does not satisfy the contract in CS-2. Do not work around it here, and do not add a second normaliser: A Task 2's function is the only definition. Report the failing parametrised case to the stream A implementer. (Measured while this plan was fixed: the autolink, backslash-escape and `&amp;` cases fail without A Task 2's `html.unescape`, `<https://…>` and backslash-escape folds and pass with them; the other 20 tests pass either way.)

Then run: `./.venv/Scripts/python.exe -m ruff check pipeline/research_html_renderer.py && ./.venv/Scripts/python.exe -m ruff format --check pipeline/research_html_renderer.py && ./.venv/Scripts/python.exe -m vulture pipeline/research_html_renderer.py .vulture_whitelist.py --min-confidence 80`
Expected: `All checks passed!`, `1 file already formatted`, no vulture output.

- [ ] **Step 6: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add pipeline/research_html_renderer.py tests/pipeline/test_research_evidence_anchors.py
git commit -m "Inject #ev-NN evidence anchors and video-moment links into the rendered paper body after nh3" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- pipeline/research_html_renderer.py tests/pipeline/test_research_evidence_anchors.py
```

---

### Task 3: Hand the extras to the paper page (SSR payload)

**Files:**
- Modify: `api/routes/research_html.py:25-30` (imports), `:88-99` (`fetch_paper`), `:111-124` (`report_markdown`), `:127-152` (`research_paper_page`)
- Test: `tests/api/test_research_html_ssr.py` (modify)
- Locate each edit by the function name or the quoted old text; the line numbers are from the base commit (see "Read this first").

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_research_html_ssr.py`, replace the import line:

```python
from api.routes.research_html import research_listing, research_paper_page
```

with:

```python
import pytest

from api.routes.research_html import (
    fetch_paper,
    research_listing,
    research_medium_copy,
    research_paper_page,
)
from pipeline.article_html_renderer import markdown_to_html
from pipeline.research_html_renderer import PaperPageError
from tests.fake_sql import RecordingSession
```

In `_paper_row`, replace:

```python
        "published_report": "## Findings\n\nObsidian moved far.",
        "report": "raw draft",
    }
```

with:

```python
        "published_report": "## Findings\n\nObsidian moved far.",
        "report": "raw draft",
        # PAPER_EXTRAS_COLUMNS: jsonb NULL for every paper published before
        # the studio (the keys are absent from its result_json).
        "evidence": None,
        "videos": None,
        "corrections": None,
        "writer": None,
    }
```

Append to the end of the file:

```python


# ── Claude-written papers (studio spec 2026-09-26 §2.7, §3.7) ─────────────────

WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}
OLD_KEYS = {
    "type",
    "slug",
    "title",
    "summary",
    "author",
    "published_at",
    "hero_image_url",
    "body_html",
}
# An evidence anchor opens its paragraph and has at least MIN_ANCHOR_CHARS (20)
# normalised characters (contract C9), which the fixture's "Obsidian moved
# far." paragraph is too short for.
EVIDENCE_REPORT = "## Findings\n\nObsidian moved far across Anatolia."
EVIDENCE_ANCHOR = "Obsidian moved far across"
VIDEO = {
    "youtube_id": "dQw4w9WgXcQ",
    "title": "Obsidian roads",
    "published_at": "2026-10-01T15:00:00+00:00",
    "evidence_timestamps": {},
}


def _route_for(row) -> dict:
    render, shell = _patched()
    with render as render_mock, shell:
        asyncio.run(research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([row])))
    return render_mock.call_args[0][0]


def test_a_paper_without_extras_keeps_its_exact_payload():
    """All papers published before the studio: same keys, same body bytes."""
    route = _route_for(_paper_row())
    assert set(route) == OLD_KEYS
    assert route["body_html"] == markdown_to_html("## Findings\n\nObsidian moved far.")


def test_writer_corrections_and_videos_join_the_payload():
    route = _route_for(
        _paper_row(
            writer=WRITER,
            corrections=[{"date": "2026-10-02", "text": "Typo in a date."}],
            videos=[VIDEO],
        )
    )
    assert route["writer"] == WRITER
    assert route["corrections"] == [
        {"date": "2026-10-02", "text": "Typo in a date.", "evidence_id": None, "holds_anchor": False}
    ]
    assert route["videos"] == [
        {
            "youtube_id": "dQw4w9WgXcQ",
            "title": "Obsidian roads",
            "published_at": "2026-10-01T15:00:00+00:00",
            "poster": None,
        }
    ]


def test_a_registered_poster_joins_the_video_payload():
    """Owner decision #13: our own studio thumbnail, under the paper's own request id."""
    poster = "/data/research-images/7f00aa00-0000-4000-8000-000000000000/video_dQw4w9WgXcQ.jpg"
    route = _route_for(_paper_row(videos=[{**VIDEO, "poster": poster}]))
    assert route["videos"][0]["poster"] == poster


def test_a_poster_from_another_papers_folder_fails_the_page():
    poster = "/data/research-images/99999999-8888-7777-6666-555555555555/video_dQw4w9WgXcQ.jpg"
    row = _paper_row(videos=[{**VIDEO, "poster": poster}])
    render, shell = _patched()
    with render as render_mock, shell, pytest.raises(PaperPageError, match="poster must be"):
        asyncio.run(research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([row])))
    render_mock.assert_not_called()


def test_evidence_paragraphs_carry_their_anchor_and_video_link():
    route = _route_for(
        _paper_row(
            published_report=EVIDENCE_REPORT,
            evidence=[{"id": "ev-01", "anchor_text": EVIDENCE_ANCHOR, "claim": "It did."}],
            videos=[
                {
                    "youtube_id": "dQw4w9WgXcQ",
                    "title": "Obsidian roads",
                    "published_at": "2026-10-01",
                    "evidence_timestamps": {"ev-01": 75},
                }
            ],
        )
    )
    body = route["body_html"]
    assert (
        '<p id="ev-01" class="theo-evidence">Obsidian moved far across Anatolia. '
        '<a class="theo-evidence-video"' in body
    )
    assert "https://www.youtube.com/watch?v=dQw4w9WgXcQ&amp;t=75s" in body
    assert "Video at 1:15</a>" in body
    # The evidence entries stay server-side: their anchors are in body_html.
    assert "evidence" not in route


def test_an_evidence_anchor_that_resolves_nowhere_fails_the_page():
    row = _paper_row(
        published_report=EVIDENCE_REPORT,
        evidence=[{"id": "ev-01", "anchor_text": "Nothing in this paper says so", "claim": "x"}],
    )
    render, shell = _patched()
    with render as render_mock, shell, pytest.raises(PaperPageError, match="ev-01 matches 0"):
        asyncio.run(research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([row])))
    render_mock.assert_not_called()


def test_malformed_extras_fail_the_page():
    row = _paper_row(writer={**WRITER, "published": "sometimes"})
    render, shell = _patched()
    with render, shell, pytest.raises(PaperPageError, match="writer.published"):
        asyncio.run(research_paper_page("obsidian-trade-networks-anatolia", db=FakeDb([row])))


def test_the_medium_copy_gets_no_evidence_anchors_and_no_disclosure_line():
    """Owner decision #23: the AI disclosure line stays off the Medium copy.

    The line is a React component of the paper page (PaperDisclosure); the
    Medium copy is server HTML from the report alone.
    """
    row = _paper_row(
        published_report=EVIDENCE_REPORT,
        evidence=[{"id": "ev-01", "anchor_text": EVIDENCE_ANCHOR, "claim": "x"}],
        writer=WRITER,
    )
    resp = asyncio.run(research_medium_copy("obsidian-trade-networks-anatolia", db=FakeDb([row])))
    body = resp.body.decode()
    assert resp.status_code == 200
    assert "Obsidian moved far across Anatolia." in body
    assert 'id="ev-01"' not in body
    assert "theo-paper-disclosure" not in body
    assert "Researched by Theo" not in body


def test_fetch_paper_selects_the_extras_columns():
    db = RecordingSession({"WHERE r.slug = :slug": [_paper_row()]})
    fetch_paper("obsidian-trade-networks-anatolia", db)
    sql = db.statement_with("WHERE r.slug = :slug")
    for key in ("evidence", "videos", "corrections", "writer"):
        assert f"r.result_json::jsonb->'{key}' AS {key}" in sql
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_research_html_ssr.py -m "not integration and not live_llm" -q`
Expected: `7 failed, 8 passed`. The failures are `test_writer_corrections_and_videos_join_the_payload` (KeyError `'writer'`), `test_a_registered_poster_joins_the_video_payload` (KeyError `'videos'`), `test_evidence_paragraphs_carry_their_anchor_and_video_link`, `test_a_poster_from_another_papers_folder_fails_the_page`, `test_an_evidence_anchor_that_resolves_nowhere_fails_the_page` and `test_malformed_extras_fail_the_page` (the last three `DID NOT RAISE`), and `test_fetch_paper_selects_the_extras_columns`. The two regression guards (`..._keeps_its_exact_payload`, `..._medium_copy_gets_no_evidence_anchors_and_no_disclosure_line`) already pass and must stay green.

- [ ] **Step 3: Implement the route change**

In `api/routes/research_html.py`, replace the renderer import (lines 25-30):

```python
from pipeline.research_html_renderer import (
    PUBLIC_PAPER_WHERE,
    format_image_captions_medium,
    format_references_md,
    strip_leading_title_heading,
)
```

with:

```python
from pipeline.research_html_renderer import (
    PAPER_EXTRAS_COLUMNS,
    PUBLIC_PAPER_WHERE,
    evidence_video_moments,
    format_image_captions_medium,
    inject_evidence_anchors,
    page_extras_payload,
    paper_extras,
    paper_markdown,
)
```

Replace the start of `fetch_paper` (lines 89-95):

```python
    """Load one public paper row incl. report content, or None."""
    return db.execute(
        text(f"""
            SELECT {PAPER_SUMMARY_COLUMNS},
                   r.result_json::jsonb->>'published_report' AS published_report,
                   r.result_json::jsonb->>'report' AS report
            FROM research_requests r
```

with:

```python
    """Load one public paper row incl. report content and extras, or None."""
    return db.execute(
        text(f"""
            SELECT {PAPER_SUMMARY_COLUMNS},
                   r.result_json::jsonb->>'published_report' AS published_report,
                   r.result_json::jsonb->>'report' AS report,
                   {PAPER_EXTRAS_COLUMNS}
            FROM research_requests r
```

Replace the body of `report_markdown` (lines 122-124):

```python
    return format_references_md(
        strip_leading_title_heading(row.published_report or row.report or "", title)
    )
```

with:

```python
    return paper_markdown(row.published_report or row.report or "", title)
```

In `research_paper_page`, replace (lines 134-152):

```python
    # Raw snake_case row fields (react-ssr Task 12); date formatting and
    # author defaults are display decisions and live in src/seo/. body_html
    # stays Python-markdown on purpose (nh3-sanitized in markdown_to_html) —
    # React injects the finished HTML instead of re-rendering the markdown.
    paper = paper_summary_kwargs(row)
    return ssr_shell_response(
        "research.html",
        {
            "type": "research",
            "slug": paper["slug"],
            "title": paper["title"],
            "summary": paper["summary"],
            "author": paper["author"],
            "published_at": paper["published_at"],
            "hero_image_url": paper["hero_image_url"],
            "body_html": markdown_to_html(report_markdown(row, paper["title"])),
        },
        _HTML_HEADERS,
    )
```

with:

```python
    # Raw snake_case row fields (react-ssr Task 12); date formatting and
    # author defaults are display decisions and live in src/seo/. body_html
    # stays Python-markdown on purpose (nh3-sanitized in markdown_to_html) —
    # React injects the finished HTML instead of re-rendering the markdown.
    # Evidence anchors (#ev-NN) are added to that finished HTML, because nh3
    # drops id attributes; the optional videos/corrections/writer keys join
    # the payload only when the paper has them, so older papers keep their
    # exact payload (studio spec 2026-09-26 §2.7, §3.7).
    paper = paper_summary_kwargs(row)
    extras = paper_extras(row)
    body_html = inject_evidence_anchors(
        markdown_to_html(report_markdown(row, paper["title"])),
        extras.evidence,
        evidence_video_moments(extras),
    )
    return ssr_shell_response(
        "research.html",
        {
            "type": "research",
            "slug": paper["slug"],
            "title": paper["title"],
            "summary": paper["summary"],
            "author": paper["author"],
            "published_at": paper["published_at"],
            "hero_image_url": paper["hero_image_url"],
            "body_html": body_html,
            **page_extras_payload(extras),
        },
        _HTML_HEADERS,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_research_html_ssr.py tests/pipeline/test_research_paper_extras.py tests/pipeline/test_research_evidence_anchors.py -m "not integration and not live_llm" -q`
Expected: `97 passed` (15 + 59 + 23).

Then run: `./.venv/Scripts/python.exe -m ruff check api/routes/research_html.py && ./.venv/Scripts/python.exe -m ruff format --check api/routes/research_html.py && ./.venv/Scripts/python.exe -m vulture api/routes/research_html.py pipeline/research_html_renderer.py .vulture_whitelist.py --min-confidence 80`
Expected: `All checks passed!`, `1 file already formatted`, no vulture output (the removed imports `format_references_md` and `strip_leading_title_heading` must not linger).

- [ ] **Step 5: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add api/routes/research_html.py tests/api/test_research_html_ssr.py
git commit -m "Hand evidence anchors, videos, corrections and the writer record to the paper page, only when a paper has them" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- api/routes/research_html.py tests/api/test_research_html_ssr.py
```

---

### Task 4: Expose the extras in `GET /api/v1/research/{slug}`

**Files:**
- Modify: `api/schemas/public_v1.py:590-595` (`ResearchPaperDetail`; this stream owns the file, Step 0)
- Modify: `api/routes/public_v1.py:13-15` (imports), `:67-68` (imports), after `paper_summary_kwargs` (`:105-132`), `get_research_paper` (`:1656-1701`)
- Test: `tests/api/test_public_v1_research_extras.py` (create)
- Locate each edit by the class or function name or the quoted old text, not by the line numbers (see "Read this first").

- [ ] **Step 0: Extend the public schema (its own commit)**

In `api/schemas/public_v1.py`, replace:

```python
class ResearchPaperDetail(ResearchPaperSummary):
    """Full research paper including the Markdown body with references."""

    content: str = Field(
        description="Full paper in Markdown, including numbered citations and references"
    )
```

with:

```python
class ResearchEvidenceRef(BaseModel):
    """One checkable claim of a Claude-written paper and its stable page anchor."""

    id: str = Field(
        description="Stable evidence id; never renumbered, retired only by a correction",
        json_schema_extra={"example": "ev-03"},
    )
    claim: str = Field(description="The claim the evidence paragraph makes")
    url: str = Field(description="Deep link to the evidence paragraph on the paper page")


class ResearchVideoRef(BaseModel):
    """A YouTube video made from the paper."""

    youtube_id: str = Field(json_schema_extra={"example": "dQw4w9WgXcQ"})
    title: str
    published_at: str = Field(description="YouTube publication time (ISO 8601)")
    url: str = Field(description="YouTube watch URL")
    evidence_timestamps: dict[str, int] = Field(
        description="Second of the video at which each evidence id is shown"
    )
    poster: str | None = Field(
        default=None,
        description=(
            "Web path of the video's poster on ancientnerds.com "
            "(/data/research-images/<id>/video_<youtube_id>.jpg); null when none was registered"
        ),
    )


class ResearchCorrectionOut(BaseModel):
    """One entry of the paper's public corrections log."""

    date: str = Field(description="Correction day (YYYY-MM-DD)")
    text: str
    evidence_id: str | None = Field(default=None, description="Evidence id the correction concerns")


class ResearchWriterOut(BaseModel):
    """Who wrote and published the paper (the source of its AI disclosure)."""

    model: str = Field(json_schema_extra={"example": "claude-opus-5-5"})
    tool: str = Field(json_schema_extra={"example": "claude-code"})
    research_model: str = Field(json_schema_extra={"example": "MiniMax-M3"})
    published: str = Field(description="automatic | manual")
    human_review: bool = Field(description="Whether a human editor reviewed the text")


class ResearchPaperDetail(ResearchPaperSummary):
    """Full research paper including the Markdown body with references."""

    content: str = Field(
        description="Full paper in Markdown, including numbered citations and references"
    )
    evidence: list[ResearchEvidenceRef] = Field(
        default_factory=list,
        description="Checkable claims with deep links (Claude-written papers; empty otherwise)",
    )
    videos: list[ResearchVideoRef] = Field(
        default_factory=list, description="YouTube videos made from this paper"
    )
    corrections: list[ResearchCorrectionOut] = Field(
        default_factory=list, description="Public corrections log, oldest first"
    )
    writer: ResearchWriterOut | None = Field(
        default=None,
        description="Writer record of a Claude-written paper; null for older papers",
    )
```

`ResearchPaperSummary.ai_generated`/`ai_system` stay unchanged (`tests/api/test_ai_act_marking.py` pins their defaults). Then run:

```bash
cd C:/PythonProjects/AncientMap-studio
./.venv/Scripts/python.exe -m ruff check api/schemas/public_v1.py && ./.venv/Scripts/python.exe -m ruff format --check api/schemas/public_v1.py
./.venv/Scripts/python.exe -m pytest tests/api/test_ai_act_marking.py tests/api/test_scope_consumers.py tests/api/test_research_html_ssr.py -m "not integration and not live_llm" -q
```

Expected: `All checks passed!`, `1 file already formatted`, and the three test files show the same result as before the edit (the new fields all have defaults): `78 passed` on 622a20d, `87 passed` once Task 3 has added its 9 tests to `test_research_html_ssr.py`. Commit the schema alone:

```bash
git add api/schemas/public_v1.py
git commit -m "Add evidence, videos, corrections and writer to the public research paper schema" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- api/schemas/public_v1.py
```

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_public_v1_research_extras.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""GET /api/v1/research/{slug} carries the extras of a Claude-written paper.

Studio spec 2026-09-26 §2.7/§3.7: evidence (with deep links to #ev-NN), videos,
corrections and the writer record are open data like the paper itself (CC BY
4.0). An older paper answers with empty lists and writer null, and its
Markdown content is untouched: the evidence never enters the report text.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.fake_sql import RecordingSession

SLUG = "obsidian-trade-networks-anatolia"
PAPER_ID = "7f00aa00-0000-4000-8000-000000000000"
# Owner decision #13: our own studio thumbnail, stored as its web path.
POSTER = f"/data/research-images/{PAPER_ID}/video_dQw4w9WgXcQ.jpg"
WRITER = {
    "model": "claude-opus-5-5",
    "tool": "claude-code",
    "research_model": "MiniMax-M3",
    "published": "automatic",
    "human_review": False,
}


def _row(**overrides) -> SimpleNamespace:
    row = {
        "id": PAPER_ID,
        "slug": SLUG,
        "question": "How did obsidian move through Neolithic Anatolia?",
        "published_by": "Theo",
        "published_at": datetime(2026, 10, 1, 4, 15),
        "sites_found": 12,
        "title": "Obsidian Trade Networks in Neolithic Anatolia",
        "card_description": "Two exchange spheres.",
        "score": "91",
        "badge": "Claim-checked",
        "word_count": "5200",
        "hero_src": None,
        "published_report": "## Findings\n\nObsidian moved far [1].",
        "report": "raw draft",
        "evidence": None,
        "videos": None,
        "corrections": None,
        "writer": None,
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def _get(row):
    from api.routes import public_v1

    app = public_v1.create_public_api()
    db = RecordingSession({"WHERE r.slug = :slug": [row]})
    app.dependency_overrides[public_v1.get_db] = lambda: db
    app.dependency_overrides[public_v1.rate_limit_dependency] = lambda: None
    with (
        patch.object(public_v1, "cache_get", return_value=None),
        patch.object(public_v1, "cache_set"),
    ):
        resp = TestClient(app, raise_server_exceptions=False).get(f"/research/{SLUG}")
    return resp, db


def test_an_older_paper_answers_with_empty_extras():
    resp, _ = _get(_row())
    body = resp.json()
    assert resp.status_code == 200
    assert body["content"] == "## Findings\n\nObsidian moved far [1]."
    assert body["evidence"] == []
    assert body["videos"] == []
    assert body["corrections"] == []
    assert body["writer"] is None
    assert body["ai_system"] == "theo-research"


def test_a_claude_written_paper_exposes_evidence_videos_corrections_and_writer():
    resp, _ = _get(
        _row(
            evidence=[
                {
                    "id": "ev-01",
                    "anchor_text": "Obsidian moved far",
                    "claim": "Obsidian moved hundreds of kilometres.",
                    "quote": "moved far",
                }
            ],
            videos=[
                {
                    "youtube_id": "dQw4w9WgXcQ",
                    "title": "Obsidian roads",
                    "published_at": "2026-10-01T15:00:00+00:00",
                    "evidence_timestamps": {"ev-01": 75},
                    "poster": POSTER,
                },
                {
                    "youtube_id": "aaaaaaaaaaa",
                    "title": "Obsidian roads, the short",
                    "published_at": "2026-10-03T15:00:00+00:00",
                    "evidence_timestamps": {},
                },
            ],
            corrections=[{"date": "2026-10-02", "text": "Typo in a date."}],
            writer=WRITER,
        )
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["evidence"] == [
        {
            "id": "ev-01",
            "claim": "Obsidian moved hundreds of kilometres.",
            "url": f"https://ancientnerds.com/research/{SLUG}#ev-01",
        }
    ]
    assert body["videos"] == [
        {
            "youtube_id": "dQw4w9WgXcQ",
            "title": "Obsidian roads",
            "published_at": "2026-10-01T15:00:00+00:00",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "evidence_timestamps": {"ev-01": 75},
            "poster": POSTER,
        },
        {
            "youtube_id": "aaaaaaaaaaa",
            "title": "Obsidian roads, the short",
            "published_at": "2026-10-03T15:00:00+00:00",
            "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
            "evidence_timestamps": {},
            "poster": None,
        },
    ]
    assert body["corrections"] == [
        {"date": "2026-10-02", "text": "Typo in a date.", "evidence_id": None}
    ]
    assert body["writer"] == WRITER
    assert body["ai_system"] == "theo-research (MiniMax-M3) + claude-opus-5-5 (claude-code)"
    assert body["ai_generated"] is True


def test_the_detail_query_selects_the_extras():
    _, db = _get(_row())
    sql = db.statement_with("WHERE r.slug = :slug")
    for key in ("evidence", "videos", "corrections", "writer"):
        assert f"r.result_json::jsonb->'{key}' AS {key}" in sql


def test_malformed_extras_are_a_server_error_not_a_silent_omission():
    resp, _ = _get(_row(writer={**WRITER, "human_review": "no"}))
    assert resp.status_code == 500
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_public_v1_research_extras.py -m "not integration and not live_llm" -q`
Expected: `3 failed, 1 passed`. The older-paper test passes on the Step 0 schema defaults; the Claude-paper test, the query test and the malformed test fail.

- [ ] **Step 3: Implement**

In `api/routes/public_v1.py`, replace:

```python
from datetime import UTC
```

with:

```python
from datetime import UTC
from urllib.parse import quote
```

Replace:

```python
from pipeline.database import get_db
from pipeline.utils.public_sites import RETIRED, is_retired, not_retired
```

with:

```python
from pipeline.database import get_db
from pipeline.research_html_renderer import PAPER_EXTRAS_COLUMNS, PaperExtras, paper_extras
from pipeline.utils.public_sites import RETIRED, is_retired, not_retired
from pipeline.utils.slugs import BASE_URL
```

Insert right after the end of `paper_summary_kwargs` (after its closing `    }` at line 132, before the `# E4 scope (migration 0020)` comment):

```python


def paper_detail_extras(extras: PaperExtras, slug: str) -> dict:
    """The optional parts of a Claude-written paper for GET /research/{slug}.

    Studio spec 2026-09-26 §2.7/§3.7. An older paper gets empty lists and no
    writer. A writer record also names both AI systems in ai_system (Art. 50(2)
    machine-readable marking); without one the schema default stays.
    """
    page = f"{BASE_URL}/research/{quote(slug)}"
    fields: dict = {
        "evidence": [
            {"id": e["id"], "claim": e["claim"], "url": f"{page}#{e['id']}"}
            for e in extras.evidence
        ],
        "videos": [
            {
                "youtube_id": v["youtube_id"],
                "title": v["title"],
                "published_at": v["published_at"],
                "url": f"https://www.youtube.com/watch?v={v['youtube_id']}",
                "evidence_timestamps": v["evidence_timestamps"],
                "poster": v["poster"],
            }
            for v in extras.videos
        ],
        "corrections": [
            {"date": c["date"], "text": c["text"], "evidence_id": c["evidence_id"]}
            for c in extras.corrections
        ],
        "writer": extras.writer,
    }
    if extras.writer is not None:
        w = extras.writer
        fields["ai_system"] = f"theo-research ({w['research_model']}) + {w['model']} ({w['tool']})"
    return fields
```

In the `@public_app.get("/research/{slug}", …)` decorator's `description`, replace:

```python
            "Full research paper as Markdown, including numbered citations and the "
            "complete reference list.\n\n"
```

with:

```python
            "Full research paper as Markdown, including numbered citations and the "
            "complete reference list.\n\n"
            "Papers written by Claude from a Theo research dossier also carry "
            "`evidence` (checkable claims with deep links to `#ev-NN` on the paper "
            "page), `videos` (YouTube videos made from the paper, with the second "
            "each evidence item is shown at and the web path of our own poster "
            "image, or null), `corrections` (the public log) and "
            "`writer` (the AI disclosure record). Older papers return empty lists "
            "and `writer: null`.\n\n"
```

In `get_research_paper`, replace the query:

```python
                SELECT {PAPER_SUMMARY_COLUMNS},
                       r.result_json::jsonb->>'published_report' AS published_report,
                       r.result_json::jsonb->>'report' AS report
                FROM research_requests r
                WHERE r.slug = :slug AND r.is_public = TRUE AND r.status = 'completed'
```

with:

```python
                SELECT {PAPER_SUMMARY_COLUMNS},
                       r.result_json::jsonb->>'published_report' AS published_report,
                       r.result_json::jsonb->>'report' AS report,
                       {PAPER_EXTRAS_COLUMNS}
                FROM research_requests r
                WHERE r.slug = :slug AND r.is_public = TRUE AND r.status = 'completed'
```

and replace:

```python
        response = ResearchPaperDetail(**paper_summary_kwargs(row), content=content)
```

with:

```python
        response = ResearchPaperDetail(
            **paper_summary_kwargs(row),
            content=content,
            **paper_detail_extras(paper_extras(row), row.slug),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_public_v1_research_extras.py tests/api/test_ai_act_marking.py tests/api/test_scope_consumers.py tests/api/test_research_html_ssr.py -m "not integration and not live_llm" -q`
Expected: `91 passed`: 4 in the new file and 87 in the other three, which is their result before this task (baseline on 622a20d: 78 passed for the three files, plus the 9 tests Task 3 added to `test_research_html_ssr.py`; `test_ai_act_marking.py` loads a module from `scripts/remediation/`).

Then run: `./.venv/Scripts/python.exe -m ruff check api/routes/public_v1.py && ./.venv/Scripts/python.exe -m ruff format --check api/routes/public_v1.py && ./.venv/Scripts/lint-imports.exe`
Expected: `All checks passed!`, `1 file already formatted`, `Contracts: 2 kept, 0 broken.` (`api.** -> pipeline.research_html_renderer` and `pipeline.utils.**` are sanctioned families.)

mypy is clean on the merged base (measured 2026-09-26 on 622a20d). `./.venv/Scripts/python.exe -m mypy api/routes/public_v1.py api/routes/research_html.py 2>&1 | tail -1` must print `Success: no issues found in 2 source files`, and the CI gate `./.venv/Scripts/python.exe -m mypy api/ 2>&1 | tail -1` must print `Success: no issues found in <N> source files` (N = 80 unless another stream added api/ modules). Any error in api/ after Tasks 3-4 is this stream's to fix: CI's lint-backend runs `mypy api/ --no-error-summary` as a blocking gate.

- [ ] **Step 5: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add api/routes/public_v1.py tests/api/test_public_v1_research_extras.py
git commit -m "Expose a Claude-written paper's evidence, videos, corrections and writer in /api/v1/research/{slug}" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- api/routes/public_v1.py tests/api/test_public_v1_research_extras.py
```

---

### Task 5: Payload types and shared helpers (frontend)

**Files:**
- Modify: `ancient-nerds-map/src/types/anRoute.ts:199-217`
- Create: `ancient-nerds-map/src/components/theo/paperExtras.ts`
- Test: `ancient-nerds-map/src/components/theo/__tests__/paperExtras.test.ts` (create)
- Locate the `anRoute.ts` edit by the quoted old text, not by the line numbers (see "Read this first").

- [ ] **Step 1: Write the failing test**

Create `ancient-nerds-map/src/components/theo/__tests__/paperExtras.test.ts`:

```ts
/**
 * The pure helpers the paper extras share with researchMeta: the newest
 * correction day and the two YouTube URLs.
 */

import { describe, expect, it } from 'vitest'

import { latestCorrectionDate, youtubeThumbnailUrl, youtubeWatchUrl } from '../paperExtras'

describe('latestCorrectionDate', () => {
  it('picks the newest day whatever the order', () => {
    expect(
      latestCorrectionDate([
        { date: '2026-10-04', text: 'b', evidence_id: null, holds_anchor: false },
        { date: '2026-10-02', text: 'a', evidence_id: null, holds_anchor: false },
        { date: '2026-11-01', text: 'c', evidence_id: null, holds_anchor: false },
      ]),
    ).toBe('2026-11-01')
  })
})

describe('YouTube URLs', () => {
  it('builds the watch page from the id', () => {
    expect(youtubeWatchUrl('dQw4w9WgXcQ')).toBe('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
  })

  it('builds the thumbnail every video has (hqdefault)', () => {
    expect(youtubeThumbnailUrl('dQw4w9WgXcQ')).toBe('https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/paperExtras.test.ts`
Expected: FAIL, `Failed to resolve import "../paperExtras"`.

- [ ] **Step 3: Add the types**

In `ancient-nerds-map/src/types/anRoute.ts`, directly above the doc comment of `ResearchRoute` (line 199: the `/**` above line 200 ` * One public research paper — the raw paper_summary_kwargs fields the`), insert:

```ts
/**
 * A YouTube video made from a paper (result_json.videos, registered by
 * `theo_publish --register-video`). The evidence timestamps stay in Python:
 * they arrive as "Video at m:ss" links inside body_html.
 */
export interface ResearchVideo {
  youtube_id: string
  title: string
  /** Raw ISO 8601 publication time on YouTube; date display is a TS decision. */
  published_at: string
  /**
   * Our own studio thumbnail, served from our server:
   * /data/research-images/<request_id>/video_<youtube_id>.jpg (owner decision
   * #13, spec §2.7; pipeline.lyra.theo_publishing.poster_web_path). Null when
   * the video was registered without one: the page then shows the posterless
   * player. Either way nothing is requested from YouTube before the click.
   */
  poster: string | null
}

/** One entry of a paper's public corrections log (result_json.corrections). */
export interface ResearchCorrection {
  /** YYYY-MM-DD. */
  date: string
  text: string
  /** The evidence paragraph (ev-NN) this correction concerns, or null. */
  evidence_id: string | null
  /**
   * True when the correction retired evidence_id: this entry then carries that
   * id itself, so a video description linking #ev-NN lands on the correction.
   * False with an evidence_id: the entry links to the corrected paragraph.
   */
  holds_anchor: boolean
}

/**
 * Who wrote and published a paper (result_json.writer): the source of the
 * visible AI disclosure line (EU AI Act Art. 50(4), studio spec §3.7).
 */
export interface ResearchWriter {
  model: string
  tool: string
  research_model: string
  published: 'automatic' | 'manual'
  human_review: boolean
}

```

In `ResearchRoute`, replace:

```ts
  hero_image_url: string | null
  body_html: string
}

/**
 * The research library listing.
```

with:

```ts
  hero_image_url: string | null
  body_html: string
  /**
   * The parts of a Claude-written paper (studio spec 2026-09-26 §2.7, §3.7).
   * Present only when the paper has them: api/routes/research_html.py adds a
   * key only then, so the payload of every older paper stays byte-identical.
   * Evidence anchors need no field: they are ids inside body_html.
   */
  videos?: ResearchVideo[]
  corrections?: ResearchCorrection[]
  writer?: ResearchWriter
}

/**
 * The research library listing.
```

- [ ] **Step 4: Create the helpers**

Create `ancient-nerds-map/src/components/theo/paperExtras.ts`:

```ts
/**
 * Pure helpers for the optional parts of a Claude-written paper (studio spec
 * 2026-09-26 §2.7, §3.7), shared by the page components and researchMeta so
 * the visible markup and the JSON-LD cannot drift apart.
 */

import type { ResearchCorrection } from '../../types/anRoute'

/** The YouTube watch page of a video. */
export function youtubeWatchUrl(youtubeId: string): string {
  return `https://www.youtube.com/watch?v=${youtubeId}`
}

/**
 * A thumbnail every YouTube video has (hqdefault; maxresdefault exists only
 * for HD uploads). Used in JSON-LD only (a crawler reads it, the visitor's
 * browser does not): the page itself shows our own poster
 * (ResearchVideo.poster) or none, and never loads an image from YouTube
 * before the visitor clicks play.
 */
export function youtubeThumbnailUrl(youtubeId: string): string {
  return `https://i.ytimg.com/vi/${youtubeId}/hqdefault.jpg`
}

/** The newest correction day. The dates are YYYY-MM-DD, which order as strings. */
export function latestCorrectionDate(corrections: ResearchCorrection[]): string {
  return corrections.reduce((latest, c) => (c.date > latest ? c.date : latest), '')
}
```

- [ ] **Step 5: Run the test and the type check**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/paperExtras.test.ts && npm run type-check`
Expected: `3 passed`; type-check prints no errors.

- [ ] **Step 6: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add ancient-nerds-map/src/types/anRoute.ts ancient-nerds-map/src/components/theo/paperExtras.ts ancient-nerds-map/src/components/theo/__tests__/paperExtras.test.ts
git commit -m "Declare the paper extras in the research route payload and share their URL and date helpers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ancient-nerds-map/src/types/anRoute.ts ancient-nerds-map/src/components/theo/paperExtras.ts ancient-nerds-map/src/components/theo/__tests__/paperExtras.test.ts
```

---

### Task 6: The AI disclosure line and the extras stylesheet

**Files:**
- Create: `ancient-nerds-map/src/styles/paper-extras.css`, `ancient-nerds-map/src/components/theo/PaperDisclosure.tsx`
- Test: `ancient-nerds-map/src/components/theo/__tests__/PaperDisclosure.test.tsx` (create)

The stylesheet is created whole here, because PaperDisclosure, PaperCorrections and PaperArticle all import it. (`src/styles/paper-article.css` has mixed CR/LF line terminators and git treats it as binary, so do not add to it.)

- [ ] **Step 1: Write the failing test**

Create `ancient-nerds-map/src/components/theo/__tests__/PaperDisclosure.test.tsx`:

```tsx
/**
 * The visible AI disclosure line of a Claude-written paper (studio spec
 * 2026-09-26 §3.7, EU AI Act Art. 50(4)/(5)), rendered as the SSR sidecar
 * renders it.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ResearchWriter } from '../../../types/anRoute'
import PaperDisclosure, { disclosureText } from '../PaperDisclosure'

const WRITER: ResearchWriter = {
  model: 'claude-opus-5-5',
  tool: 'claude-code',
  research_model: 'MiniMax-M3',
  published: 'automatic',
  human_review: false,
}

describe('disclosureText', () => {
  it('is the spec §3.7 line for an automatic publish without review', () => {
    expect(disclosureText(WRITER)).toBe(
      'Researched by Theo (AI research agent) · written by Claude (Anthropic) · ' +
        'published automatically after automated source checks, without human editorial review',
    )
  })

  it('names a manual publish and a human review when the record says so', () => {
    expect(disclosureText({ ...WRITER, published: 'manual', human_review: true })).toBe(
      'Researched by Theo (AI research agent) · written by Claude (Anthropic) · ' +
        'published by the editor after automated source checks, with human editorial review',
    )
  })

  it('prints a non-Claude model id as stored', () => {
    expect(disclosureText({ ...WRITER, model: 'other-model-1' })).toContain(
      'written by other-model-1 ·',
    )
  })
})

describe('PaperDisclosure', () => {
  it('renders the line as a machine-readable AI notice', () => {
    expect(renderToString(<PaperDisclosure writer={WRITER} />)).toBe(
      `<p class="theo-paper-disclosure" data-ai-generated="true">${disclosureText(WRITER)}</p>`,
    )
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/PaperDisclosure.test.tsx`
Expected: FAIL, `Failed to resolve import "../PaperDisclosure"`.

- [ ] **Step 3: Create the stylesheet**

Create `ancient-nerds-map/src/styles/paper-extras.css`:

```css
/* ═══════════════════════════════════════════
   Research paper extras of a Claude-written
   paper (studio spec 2026-09-26 §2.7, §3.7):
   evidence anchors in the body, the "video at
   m:ss" links, the AI disclosure line and the
   corrections log. Imported by PaperArticle,
   PaperDisclosure and PaperCorrections.
   ═══════════════════════════════════════════ */

/* — Evidence anchors (#ev-NN) —
   pipeline/research_html_renderer.inject_evidence_anchors gives an evidence
   paragraph id="ev-NN" class="theo-evidence" (further ids of the same
   paragraph an empty span.theo-evidence-anchor) after nh3 sanitising. The
   page header is sticky (page-header.css, z-index 10000), so without a scroll
   margin a deep link lands underneath it. 80px matches .theo-ref-item. */
.theo-md-body .theo-evidence,
.theo-md-body .theo-evidence-anchor,
.theo-paper-corrections,
.theo-paper-corrections li {
  scroll-margin-top: 80px;
}

.theo-md-body .theo-evidence-anchor {
  display: block;
  height: 0;
}

/* The paragraph a video description linked to, marked in Theo's amber. */
.theo-md-body .theo-evidence:target,
.theo-md-body .theo-evidence:has(> .theo-evidence-anchor:target),
.theo-paper-corrections li:target {
  background: rgba(212, 145, 42, 0.1);
  outline: 1px solid rgba(212, 145, 42, 0.35);
  outline-offset: 4px;
}

/* "Video at 5:12": a small chip at the end of the paragraph. Overrides the
   body's break-all for links so the time never splits across lines. */
.theo-md-body a.theo-evidence-video {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  font-size: 12px;
  line-height: 1.6;
  white-space: nowrap;
  word-break: normal;
  border: 1px solid rgba(0, 200, 200, 0.35);
  border-radius: var(--nerv-panel-radius, 0);
}

/* — AI disclosure line (PaperDisclosure) — */
.theo-paper-disclosure {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
}

/* "Corrected 2026-10-04" in the meta line, linking to the log. */
.theo-paper-corrected {
  font-size: 12px;
  color: var(--text-link);
  text-decoration: none;
}

/* — Corrections log (PaperCorrections) — */
.theo-paper-corrections {
  margin: 32px 0 0;
  padding-top: 16px;
  border-top: 1px solid var(--border-default);
}

.theo-paper-corrections h2 {
  font-family: var(--font-heading);
  font-size: 18px;
  letter-spacing: 1px;
  color: var(--text-primary);
  margin: 0 0 8px;
}

.theo-paper-corrections ol {
  margin: 0;
  padding-left: 20px;
}

.theo-paper-corrections li {
  margin: 6px 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-body);
}

.theo-paper-corrections time {
  font-size: 12px;
  color: var(--text-muted);
}

.theo-paper-correction-link {
  margin-left: 6px;
  color: var(--text-link);
  text-decoration: none;
}
```

- [ ] **Step 4: Create the component**

Create `ancient-nerds-map/src/components/theo/PaperDisclosure.tsx`:

```tsx
/**
 * PaperDisclosure — the visible AI disclosure line of a Claude-written paper.
 *
 * EU AI Act Art. 50(4)/(5) (in force since 2026-08-02): AI-written text on
 * matters of public interest, published without human editorial review,
 * must say so at the latest on first exposure. So the line sits in the
 * paper header, right under the meta line, and carries the same
 * machine-readable marker as AiNoticeBanner (data-ai-generated).
 * The wording follows result_json.writer (studio spec 2026-09-26 §3.7).
 */

import type { ResearchWriter } from '../../types/anRoute'

import '../../styles/paper-extras.css'

/** "Claude (Anthropic)" for any claude-* model id; other ids are printed as stored. */
function writerName(model: string): string {
  return model.startsWith('claude') ? 'Claude (Anthropic)' : model
}

export function disclosureText(writer: ResearchWriter): string {
  const published =
    writer.published === 'automatic'
      ? 'published automatically after automated source checks'
      : 'published by the editor after automated source checks'
  const review = writer.human_review ? 'with human editorial review' : 'without human editorial review'
  return `Researched by Theo (AI research agent) · written by ${writerName(writer.model)} · ${published}, ${review}`
}

export default function PaperDisclosure({ writer }: { writer: ResearchWriter }) {
  return (
    <p className="theo-paper-disclosure" data-ai-generated="true">
      {disclosureText(writer)}
    </p>
  )
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/PaperDisclosure.test.tsx`
Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add ancient-nerds-map/src/styles/paper-extras.css ancient-nerds-map/src/components/theo/PaperDisclosure.tsx ancient-nerds-map/src/components/theo/__tests__/PaperDisclosure.test.tsx
git commit -m "Show the writer's AI disclosure line on Claude-written papers" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ancient-nerds-map/src/styles/paper-extras.css ancient-nerds-map/src/components/theo/PaperDisclosure.tsx ancient-nerds-map/src/components/theo/__tests__/PaperDisclosure.test.tsx
```

---

### Task 7: The corrections log

**Files:**
- Create: `ancient-nerds-map/src/components/theo/PaperCorrections.tsx`
- Test: `ancient-nerds-map/src/components/theo/__tests__/PaperCorrections.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `ancient-nerds-map/src/components/theo/__tests__/PaperCorrections.test.tsx`:

```tsx
/**
 * The corrections log under a paper: a correction of a current evidence
 * paragraph links to it, one that retired an evidence id carries the id
 * itself (so old video links land on it), and dates render in the fixed
 * longDate format that hydrates identically in the UTC sidecar and a browser.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ResearchCorrection } from '../../../types/anRoute'
import PaperCorrections from '../PaperCorrections'

const CORRECTIONS: ResearchCorrection[] = [
  { date: '2026-10-02', text: 'Quarry date re-sourced.', evidence_id: 'ev-02', holds_anchor: false },
  { date: '2026-10-04', text: 'Fourth monolith removed.', evidence_id: 'ev-05', holds_anchor: true },
  { date: '2026-10-05', text: 'Typo in a date.', evidence_id: null, holds_anchor: false },
]

describe('PaperCorrections', () => {
  const html = renderToString(<PaperCorrections corrections={CORRECTIONS} />)

  it('is a section with an h2, the target of the meta line link', () => {
    expect(html).toContain('<section id="corrections" class="theo-paper-corrections"')
    expect(html).toContain('<h2 id="corrections-title">Corrections</h2>')
  })

  it('a correction of a current paragraph links to it', () => {
    expect(html).toContain(
      '<li><time dateTime="2026-10-02">October 02, 2026</time> Quarry date re-sourced.' +
        '<a class="theo-paper-correction-link" href="#ev-02">See the corrected passage</a></li>',
    )
  })

  it('a correction that retired an id carries the id itself', () => {
    expect(html).toContain(
      '<li id="ev-05"><time dateTime="2026-10-04">October 04, 2026</time> Fourth monolith removed.</li>',
    )
  })

  it('a correction without an evidence id has neither', () => {
    expect(html).toContain(
      '<li><time dateTime="2026-10-05">October 05, 2026</time> Typo in a date.</li>',
    )
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/PaperCorrections.test.tsx`
Expected: FAIL, `Failed to resolve import "../PaperCorrections"`.

- [ ] **Step 3: Create the component**

Create `ancient-nerds-map/src/components/theo/PaperCorrections.tsx`:

```tsx
/**
 * PaperCorrections — the public corrections log under a paper
 * (result_json.corrections, appended by `theo_publish --correct`).
 *
 * An entry that concerns an evidence paragraph links to it (#ev-NN). An
 * entry that retired an evidence id carries that id itself (holds_anchor,
 * decided in pipeline/research_html_renderer.parse_corrections): video
 * descriptions link #ev-NN for good, and the link then lands here, on the
 * explanation, instead of nowhere.
 *
 * Dates go through longDate, never new Date(): the SSR sidecar runs in UTC
 * and a browser in local time (display.ts, the hydration note at shortDate).
 * Each text is one string child, so the indexed HTML has no <!-- --> splits.
 */

import { longDate } from '../../seo/display'
import type { ResearchCorrection } from '../../types/anRoute'

import '../../styles/paper-extras.css'

export default function PaperCorrections({ corrections }: { corrections: ResearchCorrection[] }) {
  return (
    <section id="corrections" className="theo-paper-corrections" aria-labelledby="corrections-title">
      <h2 id="corrections-title">Corrections</h2>
      <ol>
        {corrections.map((c, i) => {
          const anchorId = c.holds_anchor ? c.evidence_id : null
          const linkId = c.holds_anchor ? null : c.evidence_id
          return (
            <li key={`${c.date}-${i}`} id={anchorId ?? undefined}>
              <time dateTime={c.date}>{longDate(c.date)}</time>
              {` ${c.text}`}
              {linkId && (
                <a className="theo-paper-correction-link" href={`#${linkId}`}>
                  See the corrected passage
                </a>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/PaperCorrections.test.tsx`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add ancient-nerds-map/src/components/theo/PaperCorrections.tsx ancient-nerds-map/src/components/theo/__tests__/PaperCorrections.test.tsx
git commit -m "Render a paper's public corrections log, with retired evidence ids anchored on their correction" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ancient-nerds-map/src/components/theo/PaperCorrections.tsx ancient-nerds-map/src/components/theo/__tests__/PaperCorrections.test.tsx
```

---

### Task 8: The video figure

**Files:**
- Create: `ancient-nerds-map/src/components/theo/PaperVideo.tsx`
- Test: `ancient-nerds-map/src/components/theo/__tests__/PaperVideo.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `ancient-nerds-map/src/components/theo/__tests__/PaperVideo.test.tsx`:

```tsx
/**
 * A video made from the paper, rendered as the SSR sidecar renders it: a real
 * YouTube link around our own poster image (owner decision #13, spec §2.7),
 * or the framed posterless player for a video registered without one. No
 * image from YouTube and no iframe until a visitor clicks.
 */

import { renderToString } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { ResearchVideo } from '../../../types/anRoute'
import PaperVideo from '../PaperVideo'

const POSTER = '/data/research-images/7f00aa00-0000-4000-8000-000000000000/video_dQw4w9WgXcQ.jpg'
const VIDEO: ResearchVideo = {
  youtube_id: 'dQw4w9WgXcQ',
  title: 'Baalbek: the 1,000-tonne question',
  published_at: '2026-10-01T15:00:00+00:00',
  poster: POSTER,
}

describe('PaperVideo', () => {
  it('draws our own poster inside the real YouTube link, no iframe before the click', () => {
    const html = renderToString(<PaperVideo video={VIDEO} />)
    expect(html).toContain(
      '<a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ" target="_blank" rel="noopener noreferrer" ' +
        `class="story-video-link"><img src="${POSTER}" alt="" loading="lazy"/>`,
    )
    expect(html).not.toContain('is-posterless')
    expect(html).not.toContain('<iframe')
    expect(html).not.toContain('i.ytimg.com')
  })

  it('a video registered without a poster keeps the posterless player', () => {
    const html = renderToString(<PaperVideo video={{ ...VIDEO, poster: null }} />)
    expect(html).toContain('<a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ" target="_blank"')
    expect(html).toContain('class="story-video-link is-posterless"')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<iframe')
    expect(html).not.toContain('i.ytimg.com')
  })

  it('captions the title and the publication day', () => {
    const html = renderToString(<PaperVideo video={VIDEO} />)
    expect(html).toContain('Baalbek: the 1,000-tonne question</a> · October 01, 2026</figcaption>')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/PaperVideo.test.tsx`
Expected: FAIL, `Failed to resolve import "../PaperVideo"`.

- [ ] **Step 3: Create the component**

Create `ancient-nerds-map/src/components/theo/PaperVideo.tsx`:

```tsx
/**
 * PaperVideo — a YouTube video made from the paper, as a click-to-play figure.
 *
 * Same player as the story page (InlineVideo, the StoryArticle figure): the
 * server renders a real link to YouTube, the iframe mounts only after a
 * click, so no request reaches YouTube before the visitor asks for it. The
 * poster is our own studio thumbnail from our server (owner decision #13,
 * spec §2.7), loaded lazily so it never competes with the hero image; the
 * .story-video img rule (story-page.css) reserves its 16:9 frame, so its late
 * arrival moves no #ev-NN target (useEvidenceHashScroll does not wait for lazy
 * images). A video registered without one keeps the framed posterless variant
 * (.is-posterless) with the play glyph.
 */

import InlineVideo from '../news/InlineVideo'
import { longDate } from '../../seo/display'
import type { ResearchVideo } from '../../types/anRoute'
import { youtubeWatchUrl } from './paperExtras'

import '../../styles/story-page.css'

export default function PaperVideo({ video }: { video: ResearchVideo }) {
  const watchUrl = youtubeWatchUrl(video.youtube_id)
  return (
    <figure className="story-video theo-paper-video">
      <InlineVideo
        videoId={video.youtube_id}
        title={video.title}
        watchUrl={watchUrl}
        embedClassName="story-video-embed"
      >
        {play => (
          // A real link: right-, middle- and ctrl-click keep working, a plain
          // click plays the video here.
          <a
            href={watchUrl}
            target="_blank"
            rel="noopener noreferrer"
            className={`story-video-link${video.poster ? '' : ' is-posterless'}`}
            onClick={e => {
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
              e.preventDefault()
              play()
            }}
          >
            {video.poster && <img src={video.poster} alt="" loading="lazy" />}
            <span className="story-play" aria-hidden="true">▶</span>
          </a>
        )}
      </InlineVideo>
      <figcaption>
        {'Video: '}
        <a href={watchUrl} target="_blank" rel="noopener noreferrer">
          {video.title}
        </a>
        {` · ${longDate(video.published_at)}`}
      </figcaption>
    </figure>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/PaperVideo.test.tsx`
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add ancient-nerds-map/src/components/theo/PaperVideo.tsx ancient-nerds-map/src/components/theo/__tests__/PaperVideo.test.tsx
git commit -m "Embed a paper's YouTube videos as click-to-play figures behind our own poster" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ancient-nerds-map/src/components/theo/PaperVideo.tsx ancient-nerds-map/src/components/theo/__tests__/PaperVideo.test.tsx
```

---

### Task 9: Wire the extras into PaperArticle

**Files:**
- Modify: `ancient-nerds-map/src/components/theo/PaperArticle.tsx` (whole file)
- Modify: `ancient-nerds-map/src/seo/__tests__/fixtures.ts` (append `RESEARCH_WITH_EXTRAS`)
- Test: `ancient-nerds-map/src/seo/__tests__/render.test.tsx` (modify)
- Locate the `render.test.tsx` edits by the quoted old text, not by line numbers; after a merge keep both sides' tests (see "Read this first").

- [ ] **Step 1: Add the fixture**

Append to the end of `ancient-nerds-map/src/seo/__tests__/fixtures.ts`:

```ts

/**
 * A Claude-written paper with every optional part (studio spec 2026-09-26
 * §2.7, §3.7), handwritten on top of the frozen research payload — like
 * landing.route.json there is no Python head to freeze for it. body_html is
 * byte for byte what pipeline/research_html_renderer.inject_evidence_anchors
 * emits for REPORT/EVIDENCE/MOMENTS in
 * tests/pipeline/test_research_evidence_anchors.py (the reference line cut).
 */
export const RESEARCH_WITH_EXTRAS: ResearchRoute = {
  ...FIXTURES.research,
  body_html:
    '<h2 id="the-quarry">The Quarry</h2>\n' +
    '<p id="ev-01" class="theo-evidence">The “Stone of the Pregnant Woman” weighs about 1,000 tonnes – roughly the mass of <em>three</em> jumbo jets [1] [2].' +
    ' <a class="theo-evidence-video" href="https://www.youtube.com/watch?v=dQw4w9WgXcQ&amp;t=312s" target="_blank" rel="noopener noreferrer" title="Watch this passage in the video: Baalbek: the 1,000-tonne question">Video at 5:12</a></p>\n' +
    '<p id="ev-02" class="theo-evidence"><span class="theo-evidence-anchor" id="ev-03"></span>Ruprechtsberger’s team dated the quarry face to the 1st century AD… a date others dispute [3].</p>',
  videos: [
    {
      youtube_id: 'dQw4w9WgXcQ',
      title: 'Baalbek: the 1,000-tonne question',
      published_at: '2026-10-01T15:00:00+00:00',
      // Our own studio thumbnail (owner decision #13); the posterless variant
      // is covered by PaperVideo.test.tsx.
      poster: '/data/research-images/7f00aa00-0000-4000-8000-000000000000/video_dQw4w9WgXcQ.jpg',
    },
  ],
  corrections: [
    {
      date: '2026-10-02',
      text: 'The quarry date now cites the 2014 excavation report.',
      evidence_id: 'ev-02',
      holds_anchor: false,
    },
    {
      date: '2026-10-04',
      text: 'Removed the claim about a fourth monolith; the cited survey does not support it.',
      evidence_id: 'ev-05',
      holds_anchor: true,
    },
  ],
  writer: {
    model: 'claude-opus-5-5',
    tool: 'claude-code',
    research_model: 'MiniMax-M3',
    published: 'automatic',
    human_review: false,
  },
}
```

- [ ] **Step 2: Write the failing render tests**

In `ancient-nerds-map/src/seo/__tests__/render.test.tsx`, replace:

```tsx
import { FIXTURES, pyrefRoute } from './fixtures'
```

with:

```tsx
import { FIXTURES, RESEARCH_WITH_EXTRAS, pyrefRoute } from './fixtures'
```

In the `describe('Hydration: der erste Client-Render gleicht dem Server', …)` block, replace:

```tsx
  for (const type of Object.keys(FIXTURES) as (keyof typeof FIXTURES)[]) {
    it(`${type}: liest beim Rendern keinen Browser-Speicher`, () => {
      expect(renderWithStorageSpy(FIXTURES[type])).toEqual([])
    })
  }
```

with:

```tsx
  for (const type of Object.keys(FIXTURES) as (keyof typeof FIXTURES)[]) {
    it(`${type}: liest beim Rendern keinen Browser-Speicher`, () => {
      expect(renderWithStorageSpy(FIXTURES[type])).toEqual([])
    })
  }

  it('research with video, corrections and writer reads no browser storage', () => {
    expect(renderWithStorageSpy(RESEARCH_WITH_EXTRAS)).toEqual([])
  })
```

Append to the end of the file:

```tsx

describe('research: Claude-written paper extras (studio spec 2026-09-26 §2.7, §3.7)', () => {
  const html = renderRoute(RESEARCH_WITH_EXTRAS)

  it('keeps the evidence anchors and video links of body_html verbatim', () => {
    expect(html).toContain('<p id="ev-01" class="theo-evidence">')
    expect(html).toContain('<span class="theo-evidence-anchor" id="ev-03"></span>')
    expect(html).toContain('href="https://www.youtube.com/watch?v=dQw4w9WgXcQ&amp;t=312s"')
  })

  it('renders the video as a click-to-play link around our own poster, no iframe on the server', () => {
    expect(html).toContain('class="story-video theo-paper-video"')
    expect(html).toContain('href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"')
    expect(html).toContain(
      'class="story-video-link"><img src="/data/research-images/7f00aa00-0000-4000-8000-000000000000/video_dQw4w9WgXcQ.jpg" alt="" loading="lazy"/>',
    )
    expect(html).not.toContain('is-posterless')
    expect(html).not.toContain('<iframe')
    expect(html).not.toContain('i.ytimg.com')
  })

  it('shows the writer disclosure, visible and machine-readable', () => {
    expect(html).toContain('<p class="theo-paper-disclosure" data-ai-generated="true">')
    expect(html).toContain(
      'Researched by Theo (AI research agent) · written by Claude (Anthropic) · published automatically after automated source checks, without human editorial review',
    )
  })

  it('renders the corrections log: the retired id is its anchor, the current one a link', () => {
    expect(html).toContain('<section id="corrections"')
    expect(html).toContain('<li id="ev-05">')
    expect(html).toContain('href="#ev-02"')
    expect(html).toContain('<time dateTime="2026-10-04">October 04, 2026</time>')
    expect(html).toContain('href="#corrections"')
    expect(html).toContain('Corrected 2026-10-04')
  })

  it('still has exactly one h1 (the log heading is an h2)', () => {
    expect(html.match(/<h1/g)).toHaveLength(1)
  })

  it('a paper without the extras renders none of their markup', () => {
    const plain = renderRoute(FIXTURES.research)
    for (const marker of [
      'theo-paper-disclosure',
      'theo-paper-video',
      'id="corrections"',
      'Corrected ',
      'theo-evidence',
    ]) {
      expect(plain).not.toContain(marker)
    }
  })
})
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/seo/__tests__/render.test.tsx`
Expected: FAIL in the new describe block: `renders the video …`, `shows the writer disclosure …` and `renders the corrections log …` fail because PaperArticle ignores the new fields. The anchor test, the h1 test, the plain-paper test and the storage-spy test already pass.

- [ ] **Step 4: Replace PaperArticle**

Replace the whole content of `ancient-nerds-map/src/components/theo/PaperArticle.tsx` with:

```tsx
/**
 * PaperArticle — one public research paper as an article: hero image,
 * header, meta line, lead-in summary and the report body the pipeline's
 * markdown renderer produced (nh3-sanitized, injected verbatim).
 *
 * Extracted from ResearchPaperPage (2026-09-10) so the paper markup is one
 * definition, separate from the page shell around it. Lives under
 * components/theo/ with the rest of Theo's paper rendering (TheoPaperBody,
 * theo.css).
 *
 * Everything that needs page state stays in the page and arrives through a
 * slot: `lead` is what goes above the title (breadcrumbs), `actions` is the
 * tail of the meta line (share, Medium copy, the TTS player — all effect
 * driven), `children` is the tail below the body (back link, Discord CTA).
 *
 * A Claude-written paper (studio spec 2026-09-26 §2.7, §3.7) adds three
 * optional parts: the writer disclosure under the meta line, its videos
 * between summary and body, and the corrections log after the body. Its
 * evidence anchors are already inside body_html. A paper without these
 * fields renders exactly the markup it always did.
 */

import SanitizedMarkdownHtml from '../../seo/SanitizedMarkdownHtml'
import { isoDate } from '../../seo/display'
import type { ResearchCorrection, ResearchVideo, ResearchWriter } from '../../types/anRoute'
import PaperCorrections from './PaperCorrections'
import PaperDisclosure from './PaperDisclosure'
import PaperVideo from './PaperVideo'
import { latestCorrectionDate } from './paperExtras'

import '../../styles/paper-article.css'
import '../../styles/paper-extras.css'

/** The fields /research/{slug} carries. */
export interface PaperArticleData {
  title: string
  summary: string | null
  /** published_by; null means the Theo pipeline. */
  author: string | null
  published_at: string | null
  hero_image_url: string | null
  body_html: string
  videos?: ResearchVideo[]
  corrections?: ResearchCorrection[]
  writer?: ResearchWriter
}

interface Props {
  paper: PaperArticleData
  lead?: React.ReactNode
  actions?: React.ReactNode
  children?: React.ReactNode
}

/** ~200 words/min over the visible text of the rendered body HTML. */
function readingMinutes(bodyHtml: string): number {
  const words = bodyHtml
    .replace(/<[^>]+>/g, ' ')
    .split(/\s+/)
    .filter(Boolean).length
  return Math.max(1, Math.ceil(words / 200))
}

export default function PaperArticle({ paper, lead, actions, children }: Props) {
  const title = paper.title
  const author = paper.author || 'Theo'
  const pubDate = isoDate(paper.published_at)
  const summary = (paper.summary || '').trim()
  const minutes = readingMinutes(paper.body_html)
  const corrections = paper.corrections ?? []
  const correctedOn = corrections.length > 0 ? latestCorrectionDate(corrections) : ''

  return (
    <>
      {paper.hero_image_url && (
        <figure className="theo-paper-hero">
          <img src={paper.hero_image_url} alt={title} className="theo-paper-hero-img" />
        </figure>
      )}

      <div className="theo-paper-page">
        {/* Paper header */}
        <div className="theo-paper-header">
          {lead}
          <h1 className="theo-paper-title">{title}</h1>
          <div className="theo-paper-meta">
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>
              {`${minutes} min read`}
            </span>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              {`by ${author}${author === 'Theo' ? ' · AI research agent' : ''}`}
            </span>
            {pubDate && (
              <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>{pubDate}</span>
            )}
            {correctedOn && (
              <a href="#corrections" className="theo-paper-corrected">{`Corrected ${correctedOn}`}</a>
            )}
            <span style={{ color: 'var(--text-dimmed)', fontSize: 12 }}>CC BY 4.0</span>
            {actions}
          </div>
          {paper.writer && <PaperDisclosure writer={paper.writer} />}
        </div>

        {/* Lead-in summary, exactly like the Python fragment rendered it. */}
        {summary && (
          <p>
            <strong>{summary}</strong>
          </p>
        )}

        {paper.videos?.map((video, i) => (
          <PaperVideo key={`${video.youtube_id}-${i}`} video={video} />
        ))}

        {/* Paper body — the pipeline's markdown rendering, verbatim. */}
        <SanitizedMarkdownHtml
          html={paper.body_html}
          className="theo-paper-body theo-md-body"
        />

        {corrections.length > 0 && <PaperCorrections corrections={corrections} />}

        {children}
      </div>
    </>
  )
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/seo/__tests__ src/components/theo/__tests__ && npm run type-check`
Expected: every test file passes (`render.test.tsx` gains 7 tests); type-check prints no errors. `meta.test.ts` must stay green: the pyref byte-parity loop is unaffected.

Byte-identity note (already measured while this plan was written): for the pyref `research` and `research_person` payloads and a variant with `published_at`/`summary` null, `renderToString` of the new PaperArticle equals the old one byte for byte. The plain-paper test above guards the markers. Do not add a snapshot of the old component.

- [ ] **Step 6: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add ancient-nerds-map/src/components/theo/PaperArticle.tsx ancient-nerds-map/src/seo/__tests__/fixtures.ts ancient-nerds-map/src/seo/__tests__/render.test.tsx
git commit -m "Wire disclosure, videos and corrections into PaperArticle; older papers render byte-identically" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ancient-nerds-map/src/components/theo/PaperArticle.tsx ancient-nerds-map/src/seo/__tests__/fixtures.ts ancient-nerds-map/src/seo/__tests__/render.test.tsx
```

---

### Task 10: dateModified and VideoObject in the paper JSON-LD

**Files:**
- Modify: `ancient-nerds-map/src/seo/meta.ts:19-31` (imports), `:365-392` (`researchMeta`)
- Test: `ancient-nerds-map/src/seo/__tests__/meta.test.ts` (modify)

- [ ] **Step 1: Write the failing test**

In `ancient-nerds-map/src/seo/__tests__/meta.test.ts`, replace:

```ts
import { FIXTURES, PYREF_DIR, pyrefHead, pyrefRoute } from './fixtures'
```

with:

```ts
import { FIXTURES, PYREF_DIR, RESEARCH_WITH_EXTRAS, pyrefHead, pyrefRoute } from './fixtures'
```

Append to the end of the file:

```ts

describe('researchMeta: Claude-written paper extras (studio spec §2.7)', () => {
  const schema = JSON.parse(researchMeta(RESEARCH_WITH_EXTRAS).schema!)

  it('dateModified is the newest correction day', () => {
    expect(schema.datePublished).toBe('2026-07-02')
    expect(schema.dateModified).toBe('2026-10-04')
  })

  it('a correction older than the current publication sets no dateModified', () => {
    // Unpublished and published again: published_at is new, the log is kept.
    const republished = JSON.parse(
      researchMeta({ ...RESEARCH_WITH_EXTRAS, published_at: '2026-11-01T09:00:00' }).schema!,
    )
    expect(republished.datePublished).toBe('2026-11-01')
    expect(republished).not.toHaveProperty('dateModified')
  })

  it('one VideoObject per registered video', () => {
    expect(schema.video).toEqual([
      {
        '@type': 'VideoObject',
        name: 'Baalbek: the 1,000-tonne question',
        description:
          'Video companion to the research paper: Obsidian Trade Networks in Neolithic Anatolia',
        uploadDate: '2026-10-01T15:00:00+00:00',
        thumbnailUrl: 'https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg',
        embedUrl: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      },
    ])
  })

  it('a paper without extras gets neither key (the pyref heads above stay byte-identical)', () => {
    const plain = JSON.parse(researchMeta(FIXTURES.research).schema!)
    expect(plain).not.toHaveProperty('dateModified')
    expect(plain).not.toHaveProperty('video')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/seo/__tests__/meta.test.ts`
Expected: FAIL: `dateModified is the newest correction day` (received `undefined`) and `one VideoObject per registered video` (received `undefined`). The republished-paper test and all pyref parity tests pass.

- [ ] **Step 3: Implement**

In `ancient-nerds-map/src/seo/meta.ts`, replace in the type import:

```ts
  ResearchRoute,
  SiteRoute,
```

with:

```ts
  ResearchRoute,
  ResearchVideo,
  SiteRoute,
```

Replace:

```ts
import { isoDate } from './display'
```

with:

```ts
import {
  latestCorrectionDate,
  youtubeThumbnailUrl,
  youtubeWatchUrl,
} from '../components/theo/paperExtras'
import { isoDate } from './display'
```

Directly above `/** research_page(): das Payload trägt die rohen Zeilenfelder — Defaults entstehen hier. */` (the comment before `researchMeta`), insert:

```ts
/**
 * One schema.org VideoObject per registered video of a paper. The thumbnail
 * is YouTube's own: crawler metadata only (the page never loads it), and it
 * exists for every video, with or without our own poster.
 */
function videoObject(video: ResearchVideo, paperTitle: string): string {
  return (
    '{"@type": "VideoObject", ' +
    `"name": ${jsonStr(video.title)}, ` +
    `"description": ${jsonStr(`Video companion to the research paper: ${paperTitle}`)}, ` +
    `"uploadDate": ${jsonStr(video.published_at)}, ` +
    `"thumbnailUrl": "${youtubeThumbnailUrl(video.youtube_id)}", ` +
    `"embedUrl": "https://www.youtube.com/embed/${video.youtube_id}", ` +
    `"url": "${youtubeWatchUrl(video.youtube_id)}"}`
  )
}

```

In `researchMeta`, replace:

```ts
      : `{"@type": "Person", "name": ${jsonStr(author)}}`
  const schema =
    '{"@context": "https://schema.org", "@type": "ScholarlyArticle", ' +
    '"digitalSourceType": "https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia", ' +
    `"headline": ${jsonStr(route.title)}, "description": ${jsonStr(cut(summary, 300))}, ` +
    `"datePublished": "${isoDate(route.published_at)}", "author": ${authorSchema}, ` +
    `"publisher": ${PUBLISHER}, ` +
    (route.hero_image_url ? `"image": ${jsonStr(absoluteUrl(route.hero_image_url))}, ` : '') +
    '"license": "https://creativecommons.org/licenses/by/4.0/", ' +
```

with:

```ts
      : `{"@type": "Person", "name": ${jsonStr(author)}}`
  // A Claude-written paper's corrections and videos (studio spec §2.7) join
  // the schema only when present: the frozen pyref heads carry neither.
  const corrections = route.corrections ?? []
  const videos = route.videos ?? []
  const published = isoDate(route.published_at)
  const modified = corrections.length > 0 ? latestCorrectionDate(corrections) : ''
  const schema =
    '{"@context": "https://schema.org", "@type": "ScholarlyArticle", ' +
    '"digitalSourceType": "https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia", ' +
    `"headline": ${jsonStr(route.title)}, "description": ${jsonStr(cut(summary, 300))}, ` +
    `"datePublished": "${published}", ` +
    // An unpublished paper published again gets a new published_at and keeps
    // its corrections log, so the newest correction can predate the
    // publication: dateModified never goes before datePublished.
    (modified > published ? `"dateModified": "${modified}", ` : '') +
    `"author": ${authorSchema}, ` +
    `"publisher": ${PUBLISHER}, ` +
    (route.hero_image_url ? `"image": ${jsonStr(absoluteUrl(route.hero_image_url))}, ` : '') +
    (videos.length > 0
      ? `"video": [${videos.map(v => videoObject(v, route.title)).join(', ')}], `
      : '') +
    '"license": "https://creativecommons.org/licenses/by/4.0/", ' +
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/seo/__tests__ && npm run type-check`
Expected: all SEO test files pass. `meta.test.ts` has 42 tests (38 on 622a20d plus these 4), and in particular `research: renderHead() == Python-Head minus <style>` and `research_person: …` stay green. Type-check prints no errors.

- [ ] **Step 5: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add ancient-nerds-map/src/seo/meta.ts ancient-nerds-map/src/seo/__tests__/meta.test.ts
git commit -m "Add dateModified and VideoObject to a paper's JSON-LD when it has corrections or videos" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ancient-nerds-map/src/seo/meta.ts ancient-nerds-map/src/seo/__tests__/meta.test.ts
```

---

### Task 11: Land `#ev-NN` deep links after the images settle

**Files:**
- Create: `ancient-nerds-map/src/components/theo/useEvidenceHashScroll.ts`
- Modify: `ancient-nerds-map/src/pages/ResearchPaperPage.tsx:18` (import), `:44` (hook call)
- Test: `ancient-nerds-map/src/components/theo/__tests__/useEvidenceHashScroll.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `ancient-nerds-map/src/components/theo/__tests__/useEvidenceHashScroll.test.tsx`:

```tsx
/**
 * A #ev-NN deep link from a video description re-scrolls to its paragraph
 * once the images above it have settled (loaded or failed), and nothing
 * happens for any other hash.
 *
 * @vitest-environment jsdom
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { useEvidenceHashScroll } from '../useEvidenceHashScroll'

// React only flushes effects inside act() when this flag is set.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function Probe() {
  useEvidenceHashScroll()
  return null
}

let root: Root | null = null
let scrolled: string[] = []

/** jsdom never fetches images: say explicitly whether each one is still loading. */
function setComplete(img: HTMLImageElement, complete: boolean): void {
  Object.defineProperty(img, 'complete', { configurable: true, value: complete })
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

async function mount(): Promise<void> {
  root = createRoot(document.getElementById('mount')!)
  await act(async () => {
    root!.render(<Probe />)
    await flush()
  })
}

beforeEach(() => {
  scrolled = []
  Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
    scrolled.push(this.id)
  })
  document.body.innerHTML =
    '<div class="theo-page"><img id="hero" src="/h.jpg">' +
    '<div class="theo-paper-body"><p id="ev-07" class="theo-evidence">x</p></div></div>' +
    '<div id="mount"></div>'
  setComplete(document.getElementById('hero') as HTMLImageElement, true)
})

afterEach(() => {
  act(() => root?.unmount())
  root = null
  window.location.hash = ''
  document.body.innerHTML = ''
})

it('scrolls to the evidence paragraph once the images above it have loaded', async () => {
  window.location.hash = '#ev-07'
  const hero = document.getElementById('hero') as HTMLImageElement
  setComplete(hero, false)
  await mount()
  expect(scrolled).toEqual([])
  await act(async () => {
    hero.dispatchEvent(new Event('load'))
    await flush()
  })
  expect(scrolled).toEqual(['ev-07'])
})

it('an image that fails to load does not hold the scroll back', async () => {
  window.location.hash = '#ev-07'
  const hero = document.getElementById('hero') as HTMLImageElement
  setComplete(hero, false)
  await mount()
  await act(async () => {
    hero.dispatchEvent(new Event('error'))
    await flush()
  })
  expect(scrolled).toEqual(['ev-07'])
})

it('does not wait for a lazy image, which never loads off-screen', async () => {
  window.location.hash = '#ev-07'
  const hero = document.getElementById('hero') as HTMLImageElement
  hero.setAttribute('loading', 'lazy')
  setComplete(hero, false)
  await mount()
  expect(scrolled).toEqual(['ev-07'])
})

it('ignores a hash that is not an evidence or corrections anchor', async () => {
  window.location.hash = '#the-quarry'
  await mount()
  expect(scrolled).toEqual([])
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__/useEvidenceHashScroll.test.tsx`
Expected: FAIL, `Failed to resolve import "../useEvidenceHashScroll"`.

- [ ] **Step 3: Create the hook**

Create `ancient-nerds-map/src/components/theo/useEvidenceHashScroll.ts`:

```ts
/**
 * useEvidenceHashScroll — land a #ev-NN deep link on its paragraph for real.
 *
 * Video descriptions link evidence as /research/{slug}#ev-NN. The browser
 * jumps to the anchor while parsing the server HTML, but the hero and the
 * body images have no reserved height, so every image that loads above the
 * target pushes it down again (Chrome's scroll anchoring may compensate,
 * Safari has none). This effect waits until the images that are still
 * loading have settled and scrolls once more. Effects never run during
 * server rendering, so the SSR markup is untouched.
 */

import { useEffect } from 'react'

/**
 * The anchors a paper page hands out: evidence paragraphs and the corrections log.
 * The ev-NN part mirrors pipeline.lyra.theo_publishing.EVIDENCE_ID_RE (`ev-[0-9]{2,}`,
 * applied with fullmatch), the one definition of the evidence-id format; change both
 * together. A JavaScript `\d` always means [0-9], so it accepts exactly the same ids.
 */
const PAPER_HASH_RE = /^#(ev-\d{2,}|corrections)$/

export function useEvidenceHashScroll(): void {
  useEffect(() => {
    const match = PAPER_HASH_RE.exec(window.location.hash)
    if (!match) return
    const targetId = match[1]
    // A lazy image off-screen never loads, so waiting for it would never end.
    const pending = Array.from(document.querySelectorAll<HTMLImageElement>('.theo-page img')).filter(
      img => !img.complete && img.getAttribute('loading') !== 'lazy',
    )
    let cancelled = false
    void Promise.all(
      pending.map(
        img =>
          new Promise<void>(resolve => {
            img.addEventListener('load', () => resolve(), { once: true })
            img.addEventListener('error', () => resolve(), { once: true })
          }),
      ),
    ).then(() => {
      if (cancelled) return
      // The hash comes from the address bar: an id the paper does not have is
      // a stale link, not an error — the browser's own jump did nothing either.
      document.getElementById(targetId)?.scrollIntoView({ block: 'start' })
    })
    return () => {
      cancelled = true
    }
  }, [])
}
```

- [ ] **Step 4: Call it from the page**

In `ancient-nerds-map/src/pages/ResearchPaperPage.tsx`, replace:

```tsx
import PaperArticle from '../components/theo/PaperArticle'
```

with:

```tsx
import PaperArticle from '../components/theo/PaperArticle'
import { useEvidenceHashScroll } from '../components/theo/useEvidenceHashScroll'
```

and replace:

```tsx
  const route = useRoute()
```

with:

```tsx
  // #ev-NN deep links from video descriptions land after the images settle.
  useEvidenceHashScroll()

  const route = useRoute()
```

(The call sits before the `if (!paper) return null` early return, so the hook order is the same on every render.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npx vitest run src/components/theo/__tests__ src/seo/__tests__ && npm run type-check`
Expected: all pass (`useEvidenceHashScroll.test.tsx` 4 passed; the render storage-spy tests stay green because effects do not run under `renderToString`). Type-check prints no errors.

- [ ] **Step 6: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add ancient-nerds-map/src/components/theo/useEvidenceHashScroll.ts ancient-nerds-map/src/components/theo/__tests__/useEvidenceHashScroll.test.tsx ancient-nerds-map/src/pages/ResearchPaperPage.tsx
git commit -m "Re-scroll #ev-NN deep links once the images above them have loaded" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ancient-nerds-map/src/components/theo/useEvidenceHashScroll.ts ancient-nerds-map/src/components/theo/__tests__/useEvidenceHashScroll.test.tsx ancient-nerds-map/src/pages/ResearchPaperPage.tsx
```

---

### Task 12: Corrections move the paper's sitemap `lastmod`

A `theo_publish --correct` run changes the served page (its text and the corrections log) but leaves `published_at` alone, so today's sitemap would never announce it. The paper's `lastmod` becomes the later of its publication and its newest correction day. The `/research/` hub keeps taking the newest paper date, as it does today.

**Files:**
- Modify: `api/routes/sitemap.py` (new constant `_RESEARCH_SQL` after `_COUNTRIES_SQL`, lines 121-129; `sitemap_research`, lines 273-286)
- Test: `tests/api/test_sitemap_lastmod.py` (append)
- Locate each edit by the constant or function name or the quoted old text, not by the line numbers; after a merge keep both sides' tests (see "Read this first").

- [ ] **Step 1: Write the failing tests**

Append to the end of `tests/api/test_sitemap_lastmod.py` (it already imports `asyncio`, `ET`, `datetime`, `SimpleNamespace`, `MagicMock`, `sm` and defines `NS`):

```python


# ── Research papers: a correction changes the served paper (studio spec 2026-09-26 §2.7) ──

PAPER_LASTMOD = (
    "GREATEST( COALESCE(published_at, created_at), "
    "(SELECT MAX((c->>'date')::date)::timestamp "
    "FROM jsonb_array_elements( COALESCE(result_json::jsonb->'corrections', '[]'::jsonb) ) c) "
    ") AS lastmod"
)


def test_a_paper_correction_advances_its_research_page():
    """`theo_publish --correct` appends to result_json.corrections and changes the page (its text
    and the corrections log) without touching published_at, so the paper's lastmod is the later of
    its publication and its newest correction day. jsonb_array_elements has no SQLite stand-in, so
    the clause is pinned as a string (whitespace folded); checked read-only against the 31
    production papers on 2026-09-26."""
    assert PAPER_LASTMOD in " ".join(str(sm._RESEARCH_SQL).split())


def test_the_research_part_reads_the_paper_lastmod():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [
        SimpleNamespace(slug="obsidian-trade-networks-anatolia", lastmod=datetime(2026, 10, 4))
    ]
    body = asyncio.run(sm.sitemap_research(db=db)).body.decode("utf-8")
    assert db.execute.call_args[0][0] is sm._RESEARCH_SQL
    urls = ET.fromstring(body).findall(f"{NS}url")
    assert [url.findtext(f"{NS}loc") for url in urls] == [
        "https://ancientnerds.com/research/",
        "https://ancientnerds.com/research/obsidian-trade-networks-anatolia",
    ]
    assert [url.findtext(f"{NS}lastmod") for url in urls] == ["2026-10-04", "2026-10-04"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_sitemap_lastmod.py -m "not integration and not live_llm" -q`
Expected: `2 failed, 9 passed`, both with `AttributeError: module 'api.routes.sitemap' has no attribute '_RESEARCH_SQL'`.

- [ ] **Step 3: Implement**

In `api/routes/sitemap.py`, replace:

```python
    + " GROUP BY u.country ORDER BY u.country"
)
```

with:

```python
    + " GROUP BY u.country ORDER BY u.country"
)

# A paper's page changes when it is published and again when
# `theo_publish --correct` appends to result_json.corrections (studio spec
# 2026-09-26 §2.7), which leaves published_at alone: the lastmod is the later
# of the two. GREATEST ignores the NULL of a paper without corrections.
_RESEARCH_SQL = text("""
    SELECT slug,
           GREATEST(
               COALESCE(published_at, created_at),
               (SELECT MAX((c->>'date')::date)::timestamp
                FROM jsonb_array_elements(
                    COALESCE(result_json::jsonb->'corrections', '[]'::jsonb)
                ) c)
           ) AS lastmod
    FROM research_requests
    WHERE is_public = TRUE AND status = 'completed' AND slug IS NOT NULL
    ORDER BY published_at DESC NULLS LAST
""")
```

and in `sitemap_research` replace:

```python
    """The /research/ hub + all published open-access papers."""
    rows = db.execute(
        text("""
            SELECT slug, COALESCE(published_at, created_at) AS lastmod
            FROM research_requests
            WHERE is_public = TRUE AND status = 'completed' AND slug IS NOT NULL
            ORDER BY published_at DESC NULLS LAST
        """)
    ).fetchall()
```

with:

```python
    """The /research/ hub + all published open-access papers."""
    rows = db.execute(_RESEARCH_SQL).fetchall()
```

(`published_at`, `created_at` and the cast correction day are all `timestamp without time zone`, so `GREATEST` needs no cast and `_newest` compares naive datetimes as before; measured read-only on production 2026-09-26: all 31 public papers evaluate, none to NULL.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/api/test_sitemap_lastmod.py tests/api/test_sitemap.py -m "not integration and not live_llm" -q`
Expected: `22 passed` (11 + 11).

Then run: `./.venv/Scripts/python.exe -m ruff check api/routes/sitemap.py && ./.venv/Scripts/python.exe -m ruff format --check api/routes/sitemap.py`
Expected: `All checks passed!`, `1 file already formatted`.

- [ ] **Step 5: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add api/routes/sitemap.py tests/api/test_sitemap_lastmod.py
git commit -m "Move a research paper's sitemap lastmod to its newest correction day" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- api/routes/sitemap.py tests/api/test_sitemap_lastmod.py
```

---

### Task 13: Name the anchor injection in the body_html justification

`SanitizedMarkdownHtml` injects `body_html` with `dangerouslySetInnerHTML`, and both its doc comment and its `nosemgrep` justification say the HTML comes only from `markdown_to_html`. Since Task 3, a research page's body also passes through `inject_evidence_anchors` after sanitising. Comment only; no behaviour changes.

**Files:**
- Modify: `ancient-nerds-map/src/seo/SanitizedMarkdownHtml.tsx:1-11` (doc comment), `:23` (nosemgrep comment)

- [ ] **Step 1: Update the doc comment**

In `ancient-nerds-map/src/seo/SanitizedMarkdownHtml.tsx`, replace:

```tsx
 * beseitigt. markdown_to_html() jagt seine Ausgabe durch nh3.clean()
 * (Allowlist-Sanitizer), BEVOR sie ins Payload gelangt; body_html hat keine
 * andere Quelle.
 */
```

with:

```tsx
 * beseitigt. markdown_to_html() jagt seine Ausgabe durch nh3.clean()
 * (Allowlist-Sanitizer), BEVOR sie ins Payload gelangt. Auf Forschungsseiten
 * setzt pipeline/research_html_renderer.inject_evidence_anchors danach nur
 * regex-geprüfte ev-NN-ids, eine regex-geprüfte YouTube-id, ganze Sekunden
 * und einen html-escapten Titel ein (Studio-Spec 2026-09-26 §2.7); eine
 * andere Quelle hat body_html nicht.
 */
```

- [ ] **Step 2: Update the nosemgrep justification**

Replace:

```tsx
      dangerouslySetInnerHTML={/* nosemgrep: semgrep.tsx-dangerously-set-inner-html -- body_html is produced exclusively by pipeline/article_html_renderer.markdown_to_html, which nh3-sanitizes (allowlist) before the payload is built */ { __html: html }}
```

with:

```tsx
      dangerouslySetInnerHTML={/* nosemgrep: semgrep.tsx-dangerously-set-inner-html -- body_html is produced by pipeline/article_html_renderer.markdown_to_html, which nh3-sanitizes (allowlist) before the payload is built; on research pages pipeline/research_html_renderer.inject_evidence_anchors then adds only regex-validated ev-NN ids, the regex-validated YouTube id, integer seconds and an html-escaped title */ { __html: html }}
```

- [ ] **Step 3: Verify**

Run: `cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map && npm run type-check && npx vitest run src/seo/__tests__/render.test.tsx`
Expected: type-check prints no errors; `render.test.tsx` passes unchanged. If semgrep is installed: `semgrep scan --config .semgrep ancient-nerds-map/src/seo/SanitizedMarkdownHtml.tsx` (from the repo root) reports 0 findings; if it is not installed, say so.

- [ ] **Step 4: Commit**

```bash
cd C:/PythonProjects/AncientMap-studio
git add ancient-nerds-map/src/seo/SanitizedMarkdownHtml.tsx
git commit -m "Name the evidence-anchor injection in the body_html sanitising justification" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- ancient-nerds-map/src/seo/SanitizedMarkdownHtml.tsx
```

---

### Task 14: Full gate run for this stream

No new code. Run every gate the pre-push hook and CI run over the touched areas, and fix only failures caused by this stream's files. Anything else is reported, not fixed.

- [ ] **Step 1: Backend gates**

```bash
cd C:/PythonProjects/AncientMap-studio
LYRA_ANTHROPIC_API_KEY=dummy-for-tests ./.venv/Scripts/python.exe -m pytest -q -rs --timeout 90 -m "not integration and not live_llm"
./.venv/Scripts/python.exe -m ruff check api/ pipeline/
./.venv/Scripts/python.exe -m ruff format --check api/routes/research_html.py api/routes/public_v1.py api/schemas/public_v1.py api/routes/sitemap.py pipeline/research_html_renderer.py
./.venv/Scripts/python.exe -m mypy api/
./.venv/Scripts/lint-imports.exe
./.venv/Scripts/python.exe -m vulture api/ pipeline/ .vulture_whitelist.py --min-confidence 80
./.venv/Scripts/python.exe -c "import sys; sys.modules['markdown']=None; sys.modules['nh3']=None; import pipeline.lyra.orchestrator"
```

Expected: pytest shows `0 failed`. The worktree has no `.env` and must not get a copy of the production one; the dummy `LYRA_ANTHROPIC_API_KEY` only lets `tests/api/lyra/test_backends.py::TestGetBackend` build a client. Baseline on 622a20d (2026-09-26): 8231 passed, 119 skipped, 57 deselected with the dummy key (without it, exactly the three TestGetBackend tests fail). This stream adds 97 tests: 59 in `test_research_paper_extras.py`, 23 in `test_research_evidence_anchors.py`, 9 new in `test_research_html_ssr.py`, 4 in `test_public_v1_research_extras.py` and 2 new in `test_sitemap_lastmod.py`. The absolute total also moves with the other streams' merges, so the criteria are `0 failed` plus all five files passing. Then: ruff `All checks passed!`; format `5 files already formatted`; mypy `Success: no issues found in <N> source files` (N = 80 unless another stream added api/ modules; the post-merge baseline is 0 errors, and CI's lint-backend blocks on any); lint-imports `Contracts: 2 kept, 0 broken.`; vulture prints nothing; the Lyra import check exits 0. `research_html_renderer` imports only stdlib and `theo_image_captions` at module level, and Lyra does not import it.

- [ ] **Step 2: Frontend gates**

```bash
cd C:/PythonProjects/AncientMap-studio/ancient-nerds-map
npm run type-check
npm run test
npx knip --no-progress --include files,dependencies,devDependencies
npm run build:ssr
```

Expected: type-check clean; vitest all files pass (baseline on 622a20d: type-check clean, vitest 109 files / 1052 tests; this stream adds 5 files with 18 tests plus 7 tests in `render.test.tsx` and 4 in `meta.test.ts`); knip reports nothing (every new file is reachable: the components through PaperArticle, `paperExtras.ts` also through `meta.ts`, the hook through ResearchPaperPage, and `paper-extras.css` through its imports); `build:ssr` ends with `✓ built`.

- [ ] **Step 3: Optional gates if installed on this machine**

`semgrep scan --config .semgrep api/ pipeline/ ancient-nerds-map/src/`: there is no new `dangerouslySetInnerHTML` (body_html still goes through `SanitizedMarkdownHtml`, whose justification Task 13 updated) and no SQL f-string with user input (`PAPER_EXTRAS_COLUMNS` and `_RESEARCH_SQL` are constants). If semgrep is not installed, say so; do not claim it passed.

- [ ] **Step 4: No commit**

This task changes no files. If a gate forced a fix in one of this plan's files, commit that fix with a pathspec and a message naming the gate, for example: `git commit -m "Keep vulture green after the paper extras" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <file>`.

---

## Spec coverage

| Spec requirement | Task |
|---|---|
| §2.7 display: evidence anchors resolve to one paragraph (the gate's C9 rule: prefix, ≥ 20 normalised characters, exactly one), ids never renumbered, retired ids handled | 1 (`parse_corrections` holds_anchor on the retiring entry), 2, 3, 7 |
| §2.7 display: `result_json.videos[]` with `evidence_timestamps` → "video at mm:ss" deep link | 1 (`parse_videos`, `evidence_video_moments`), 2 (`_video_link`), 8 (click-to-play embed) |
| Owner decision #13, spec §2.7 `poster?`: our own studio thumbnail as the video poster, served from our server, no YouTube request before the click; a video registered without one keeps the posterless player | 1 (`parse_videos`: exactly `poster_web_path(request_id, youtube_id)`), 3 (payload `poster`), 4 (API `ResearchVideoRef.poster`), 5 (`ResearchVideo.poster`), 8 (`<img>` inside the link, `.is-posterless` only without one), 9 (SSR render) |
| §2.7 display: corrections log | 1, 3, 7, 9, 10 (`dateModified`, never before `datePublished`), 12 (sitemap `lastmod`) |
| §3.7 disclosure line from `writer`, exact wording | 1 (`parse_writer`), 6, 9 |
| Owner decision #23: no AI disclosure in the Medium copy | 3 (`test_the_medium_copy_gets_no_evidence_anchors_and_no_disclosure_line`) |
| Fact 10: anchors injected after nh3, research pages only | 2 (post-sanitise, scoping tests), 3 (Medium copy test), 13 (sanitising justification names the injection) |
| Sticky header must not cover the target | 6 (`scroll-margin-top`), 11 (re-scroll after images) |
| Old papers byte-identical | 3 (exact payload keys + body), 9 (markers absent; measured byte-identical markup), 10 (pyref parity untouched) |
| Public API exposes evidence/videos/corrections/writer | 4 (Step 0 extends the schema) |
| §4.5 studio captures the paper at `#ev-NN` | 2, 6, 11 |
| §7 frontend SSR test with anchors, video, corrections, disclosure, no browser storage | 9. §7's "pyref fixtures updated" is met by the handwritten `RESEARCH_WITH_EXTRAS` in `fixtures.ts`: the frozen `pyref/*` files stay unchanged, because the deleted Python renderer can no longer regenerate them |

## Cross-stream requests

**CS-1: withdrawn, now this stream's own work.** This stream owns `api/schemas/public_v1.py`: Task 4 Step 0 applies the schema additions (`ResearchEvidenceRef`, `ResearchVideoRef`, `ResearchCorrectionOut`, `ResearchWriterOut` and the extended `ResearchPaperDetail`) as its own commit. The number stays so that CS-2 to CS-9 keep their meaning.

**CS-2: stream A Task 2, `pipeline/lyra/theo_publishing.py`: `normalize_anchor_text(text: str) -> str`, `MIN_ANCHOR_CHARS` (20), `EVIDENCE_ID_RE` (`re.compile(r"ev-[0-9]{2,}")`: ASCII digits only, always applied with `.fullmatch`), `YOUTUBE_ID_RE` (`re.compile(r"[A-Za-z0-9_-]{11}")`, next to `EVIDENCE_ID_RE`, always applied with `.fullmatch`) and `poster_web_path(request_id: str, youtube_id: str) -> str` (`f"/data/research-images/{request_id}/video_{youtube_id}.jpg"`, owner decision #13).** A Task 2's definitions are the only ones; this plan carries no second normaliser, no copy of either id regex and no copy of the poster path (the TypeScript `PAPER_HASH_RE` of Task 11 mirrors the evidence-id regex and names it as its source; Task 1 pins the ASCII-only property with an `ev-\u0661\u0662` case, and the 12-character case of `test_rejects_a_malformed_youtube_id` pins the whole-string YouTube-id match: with `.match` instead of `.fullmatch` it fails). The page imports `normalize_anchor_text` and `MIN_ANCHOR_CHARS` inside `resolve_evidence_anchors`, `EVIDENCE_ID_RE` inside `parse_evidence` and `parse_corrections`, and `YOUTUBE_ID_RE` and `poster_web_path` inside `parse_videos` (none at module level). Required property, pinned by `TestNormalizeAnchorTextContract` in Task 2: for every prose paragraph `P` of a report, `normalize_anchor_text(P) == normalize_anchor_text(visible_text(markdown_to_html(P)))`, where the visible text is the `<p>` content with tags dropped and entities decoded (`_paragraph_text`). So the function bridges Python-Markdown's smarty output (curly quotes, en and em dashes from `--`/`---`, `…` from `...`), HTML entities (`&amp;`) and markdown syntax (`*`, `_` at word edges, backticks, backslash escapes, `[text](url)`, `<https://…>` autolinks, citation markers), collapses whitespace and casefolds. The eight parametrised cases in Task 2 are the contract; the autolink, backslash-escape and `&amp;` cases need A Task 2's `html.unescape`, autolink and backslash-escape folds. The matching rule built on it is A's C9 (the normalised paragraph starts with the normalised anchor, the anchor has at least `MIN_ANCHOR_CHARS` normalised characters, exactly one paragraph matches, several entries may share one), which Task 2 applies to the served `<p>` elements.

**CS-3: stream A, the `publish_paper`, `correct_paper` and `register_video` gates and the founder publish route (A Task 21).** Run the page's own functions on exactly what will be stored, so that "gate passed" means "page renders": `resolve_evidence_anchors(markdown_to_html(paper_markdown(report, title)), parse_evidence(evidence))` next to A's markdown resolution (an entry must resolve both among `report_paragraphs` and among the `<p>` elements of the HTML the page serves), and `paper_extras(SimpleNamespace(id=request_id, evidence=…, videos=…, corrections=…, writer=…))` on the would-be `result_json` after merging corrections and videos (`id` is the canonical lowercase request id, as A's `check_page` passes it: it names the only valid poster path). Imports: `from pipeline.article_html_renderer import markdown_to_html` and `from pipeline.research_html_renderer import PaperPageError, paper_extras, paper_markdown, parse_evidence, resolve_evidence_anchors` **inside** the gate function (`research_html_renderer` imports `theo_publishing` back lazily, and `article_html_renderer` needs markdown/nh3, which only the API image has). Record a `PaperPageError` message as the failed gate's reason. A's gate tasks start after this plan's Tasks 1-2 (see "Dependencies and order"). This closes the CLI's path to a 500 on a live paper page. The second path is the founder route: after an unpublish, `PATCH /research/{id}` or `PATCH /research/{id}/section` can rewrite the report of a completed non-public row, and `POST /research/{id}/publish` (`publish_research` in `api/routes/theo.py`, `?repair=1` included) assembles `published_report` itself. A Task 21 (d) runs the same checks there before its UPDATE: `check_page(request_id, result)` and, when `result` carries `evidence`, `check_evidence_anchors(assembled["published_report"], paper_title, result["evidence"])` (A's acceptance function, which ends in this plan's `resolve_evidence_anchors` on the served HTML). Any issue answers HTTP 409 with the issue list, and `override` cannot bypass it (A contract C7). Together the two close every path to a 500 on a live paper page.

**CS-4: stream A, stored shapes in `result_json`** (the page raises on anything else): `evidence[]` entries with `id` matching `EVIDENCE_ID_RE` (`ev-[0-9]{2,}`) in full (unique), non-empty `anchor_text` and `claim` (other keys pass through unused); `corrections[]` entries `{date: "YYYY-MM-DD", text, evidence_id?}`, where the entry that retires an id is the last one naming it (a retired id is never named again; the page anchors the id on that entry); `videos[]` entries `{youtube_id: matching YOUTUBE_ID_RE (11 chars [A-Za-z0-9_-]) in full, title, published_at: ISO 8601, evidence_timestamps: {"ev-NN": int >= 0}, poster?}`, where `poster`, stored only when one was registered, is exactly `poster_web_path(request_id, youtube_id)` (spec §2.7, owner decision #13; any other value, `null` included, raises). A timestamp may name only a current evidence id or one retired by a correction. `writer` is `{model, tool, research_model, published: "automatic"|"manual", human_review: bool}`.

**CS-5: stream A: IndexNow after `--correct` and `--register-video`.** Both change the served page. Task 12 moves the sitemap `lastmod` to the newest correction day, but a crawler reads the sitemap on its own schedule, and a video registration does not move `lastmod` at all. Ping `indexnow_url(f"/research/{slug}")` as `publish_paper` does and journal the result in `side_effects`.

**CS-6: stream owning `pipeline/studio/paper/gates.py` (spec §3.4 gate 6).** Resolve `anchor_text` with the same `resolve_evidence_anchors(markdown_to_html(paper_markdown(paper_md, title)), evidence)` (directly or through stream A's shared acceptance, CS-3), so that the local check, the publish gate and the page agree on the paragraph under the one C9 rule (CS-2).

**CS-7: streams A and C, the video poster (owner decision #13, spec §2.7 `poster?` and §4.9; A, B and C land it together).** One definition: `poster` = `pipeline.lyra.theo_publishing.poster_web_path(request_id, youtube_id)` = `/data/research-images/<request_id>/video_<youtube_id>.jpg`, our own studio thumbnail served from our server. **A** (Tasks 2, 18): defines `poster_web_path` in Task 2 (CS-2); `ENVELOPES['register_video']` takes `poster` as its one optional key; `check_video_shape` reports any other value as `poster must be /data/research-images/<request_id>/video_<youtube_id>.jpg`; `register_video` gates the file under `images_root` with the existing `check_images` (gate `images`, between `duplicate` and `page`); the stored `videos[]` entry carries `poster` only when one was sent. **C** (Tasks 12, 13, 26): `video_payload(..., with_poster=True)` adds the key; `paper register-video --poster FILE` and `episode register-youtube --poster K` copy the JPEG to `video_<youtube_id>.jpg`, run a dry run without poster, upload it with `remote.upload_research_images` (verified scp), run a dry run with poster, then apply. **B** (this plan): `parse_videos` accepts exactly that path (Task 1), the payload, the API and `ResearchVideo` carry it (Tasks 3, 4, 5), and `PaperVideo` draws `<img src={poster} alt="" loading="lazy">` inside the click-to-play link (Task 8); a video registered without a poster keeps the posterless player, a valid contract state. Either way the page loads nothing from YouTube before the click; the JSON-LD `VideoObject` keeps YouTube's `thumbnailUrl` (crawler metadata, Task 10). Send `evidence_timestamps` as whole seconds.

**CS-8: withdrawn, now this stream's Task 12** (`api/routes/sitemap.py`: a paper's `lastmod` is the later of its publication and its newest correction day).

**CS-9: withdrawn, now this stream's Task 13** (`ancient-nerds-map/src/seo/SanitizedMarkdownHtml.tsx`, comment only: the justification names `inject_evidence_anchors`).
