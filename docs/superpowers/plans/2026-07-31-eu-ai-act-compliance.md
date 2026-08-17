# EU AI Act Compliance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make AncientNerds compliant with the EU AI Act transparency obligations (Art. 50) — visible AI labels on every surface by 2026-08-02 (Phase A), machine-readable AI marking by 2026-12-02 (Phase B, AI-Omnibus grace period for Art. 50(2)).

**Architecture:** Phase A closes the visible-disclosure gaps found in the 2026-07-31 audit: two missing frontend banners, a persistent AI notice in the Lyra chat, corrected "Theo" attribution, visible AI notices in the server-rendered SEO pages, and consistent legal texts (the imprint currently claims editorial review that does not exist). Phase B adds machine-readable marking: `ai_generated`/`ai_system` fields on all content API responses (via Pydantic field defaults — no serialization changes needed), IPTC `digitalSourceType` in JSON-LD, and ID3 tags in generated TTS MP3s.

**Tech Stack:** React/TypeScript (Vite) frontend, FastAPI + Pydantic backend, Python HTML renderers in `pipeline/`, pytest, mutagen (new dep, Phase B).

**Legal background (from the 2026-07-31 audit):**
- Art. 50(1) (chatbot disclosure) and Art. 50(4) (labeling of published AI text on matters of public interest — explicitly includes scientific/cultural topics) apply from **2026-08-02**, no grace period.
- Art. 50(2) (machine-readable marking) has an AI-Omnibus grace period until **2026-12-02** for systems in service before 2026-08-02 (applies to Lyra/Theo).
- The human-review exception to Art. 50(4) does NOT apply: Lyra news, weekly journals, and batch Theo papers are published fully automatically (LLM-only gates). Commission guidelines (2026-07-20) require substantive review by natural persons.
- Content generated before 2026-08-02 needs no retroactive labeling (page-level banners cover it anyway).

**Deployment notes (read before executing):**
- Commit locally per task. **NEVER push without the user's explicit OK** (pushing to main deploys to prod).
- Run `ruff format api/ pipeline/` and `ruff check api/ pipeline/` before any push — CI enforces both (ruff 0.15.11).
- CI deploy rebuilds only the `api` container and the frontend. Task 12 (TTS tagging) touches code that runs in the **lyra** container — after deploy it needs a manual `ssh ancientnerds "cd /var/www/ancientnerds && docker compose up -d --build lyra"`.
- Frontend has no unit-test runner; verification is `npx tsc --noEmit` per task plus one full `npm run build` at the end of Phase A.

**Consciously out of scope (with rationale):**
- Per-`NewsCard` AI labels: every container that renders cards (Stories panel/page, journal reading view, Library after Task 2, Lyra chat after Task 3) carries a banner.
- DB columns recording the generating model per row: not required by Art. 50; model identity lives in config. Revisit only if audit-readiness demands it.
- The weekly video pipeline uploads to YouTube as `privacy="private"`. **If videos are ever made public:** the ElevenLabs voiceover is synthetic audio → enable YouTube's "altered content" AI disclosure and add a description note.
- Signing the Code of Practice on marking/labelling: voluntary; implementing the measures suffices for a micro-operator.

---

## Phase A — visible disclosure (deadline 2026-08-02)

### Task 1: AI banner on the Journal listing view

The journal reading view already has a banner (`ArticlesPage.tsx:728`); the listing view (hero + grid) has none.

**Files:**
- Modify: `ancient-nerds-map/src/pages/ArticlesPage.tsx` (~line 723)

- [ ] **Step 1: Add the listing-view banner**

In `ArticlesPage.tsx`, directly BEFORE the `{view === 'reading' && (` block (currently line 723), add:

```tsx
      {view === 'listing' && (
        <AiNoticeBanner message="Journals are AI-generated from YouTube video content. Always verify with original sources." />
      )}
```

`AiNoticeBanner` is already imported in this file (used at line 728). The result around line 723 should read:

```tsx
      {view === 'listing' && (
        <AiNoticeBanner message="Journals are AI-generated from YouTube video content. Always verify with original sources." />
      )}

      {view === 'reading' && (
        <>
          <div className="articles-progress-track">
```

- [ ] **Step 2: Type-check**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: exit 0, no output.

- [ ] **Step 3: Commit**

```bash
git add ancient-nerds-map/src/pages/ArticlesPage.tsx
git commit -m "feat(compliance): AI notice banner on journal listing view (Art. 50(4) EU AI Act)"
```

---

### Task 2: AI banner on the Library page

The Library page aggregates Stories/Journals/Research sources with no AI disclosure at all.

**Files:**
- Modify: `ancient-nerds-map/src/pages/LibraryPage.tsx` (imports + ~line 144)

- [ ] **Step 1: Add import**

At the top of `LibraryPage.tsx`, with the other component imports, add:

```tsx
import AiNoticeBanner from '../components/layout/AiNoticeBanner'
```

- [ ] **Step 2: Render the banner**

Directly after the closing `</PageHeader>` (currently line 144), before `<div className="library-content">`, add:

```tsx
      <AiNoticeBanner message="Stories, journals, and research papers in this library are AI-generated. Always verify with original sources." />
```

- [ ] **Step 3: Type-check**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add ancient-nerds-map/src/pages/LibraryPage.tsx
git commit -m "feat(compliance): AI notice banner on Library page (Art. 50(4) EU AI Act)"
```

---

### Task 3: Persistent AI disclosure in the Lyra chat (Art. 50(1))

Today the only "AI" wording is the one-time welcome subtitle "Archaeological AI Agent" (`LyraWelcome.tsx:61`). Art. 50(1)+(5) require clear, persistent disclosure at the latest at first interaction. Add a permanent note under the input (shared by modal and page mode) and put "AI" into the in-conversation status line.

**Files:**
- Modify: `ancient-nerds-map/src/components/LyraChatModal.tsx` (~line 1027 and ~line 1584)
- Modify: `ancient-nerds-map/src/styles/index.css` (after the `.lyra-chat-input-area` rule at ~line 15028)

- [ ] **Step 1: Update the in-conversation status line**

In `LyraChatModal.tsx` line 1027, change:

```tsx
            <div className="lyra-chat-header-status">Archaeological Agent</div>
```

to:

```tsx
            <div className="lyra-chat-header-status">AI Archaeological Agent</div>
```

- [ ] **Step 2: Add the persistent note under the input**

In the input area (currently lines 1559-1584), directly after the closing `</div>` of `lyra-chat-input-row` and still inside `lyra-chat-input-area`, add:

```tsx
              <div className="lyra-chat-ai-note">
                Lyra is an AI assistant — responses are AI-generated and may contain errors.
              </div>
```

The end of the input area should read:

```tsx
                </button>
              </div>
              <div className="lyra-chat-ai-note">
                Lyra is an AI assistant — responses are AI-generated and may contain errors.
              </div>
            </div>
```

- [ ] **Step 3: Add the CSS rule**

In `ancient-nerds-map/src/styles/index.css`, immediately after the `.lyra-chat-input-area { ... }` rule block that starts at line 15028, add:

```css
.lyra-chat-ai-note {
  font-size: 10px;
  color: var(--text-muted);
  text-align: center;
  padding: 4px 8px 0;
  opacity: 0.8;
}
```

(`--text-muted`, not `--text-dimmed`: with the note's 0.8 opacity against the CRT-dark background, `--text-muted` yields ~5:1 contrast (WCAG AA pass) while `--text-dimmed` would fail at ~3.4:1 — a legally required disclosure must be clearly visible, Art. 50(5).)

- [ ] **Step 4: Type-check**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/src/components/LyraChatModal.tsx ancient-nerds-map/src/styles/index.css
git commit -m "feat(compliance): persistent AI disclosure in Lyra chat (Art. 50(1) EU AI Act)"
```

---

### Task 4: Research paper page — honest byline and OG description

Two fixes in `ResearchPaperPage.tsx`: (a) the runtime OG-meta update currently REMOVES the static "AI-generated" wording; (b) the byline renders "by Theo" as if Theo were a human author.

**Files:**
- Modify: `ancient-nerds-map/src/pages/ResearchPaperPage.tsx` (line 244 and lines 524-526)

- [ ] **Step 1: Keep AI wording in the OG description**

Line 244, change:

```tsx
        setMeta('og:description', `Research paper by ${data.published_by} on Ancient Nerds Research`)
```

to:

```tsx
        setMeta('og:description', `AI-generated research paper by ${data.published_by} on Ancient Nerds Research`)
```

- [ ] **Step 2: Qualify the Theo byline**

Lines 524-526, change:

```tsx
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              by {paper.published_by}
            </span>
```

to:

```tsx
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
              by {paper.published_by}{paper.published_by === 'Theo' ? ' · AI research agent' : ''}
            </span>
```

- [ ] **Step 3: Type-check**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add ancient-nerds-map/src/pages/ResearchPaperPage.tsx
git commit -m "fix(compliance): keep AI wording in research OG description, label Theo byline as AI"
```

---

### Task 5: Visible AI notice on server-rendered journal/story/archive pages

The SEO HTML pages (`/articles/{slug}`, `/news-archive/*`) served by `api/routes/articles_html.py` have no explicit AI label on individual pages. Add a shared notice constant and render it on every content page. TDD: renderers are pure functions.

**Files:**
- Modify: `pipeline/article_html_renderer.py`
- Test: `tests/pipeline/test_ai_act_notices.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/pipeline/test_ai_act_notices.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Art. 50 EU AI Act: visible AI notices on server-rendered content pages."""

from datetime import datetime

from pipeline.article_html_renderer import (
    AI_NOTICE_HTML,
    render_article_html,
    render_news_archive_html,
    render_story_html,
)


def _story() -> dict:
    return {
        "id": 1,
        "headline": "Test Discovery",
        "summary": "A summary.",
        "post_text": "Body paragraph one.\nBody paragraph two.",
        "facts": [],
        "site_name": None,
        "site_id": None,
        "youtube_url": None,
        "channel_name": None,
        "video_title": None,
        "news_category": None,
        "created_at": datetime(2026, 7, 1),
        "published_at": datetime(2026, 7, 1),
        "screenshot_url": None,
    }


def test_ai_notice_constant_is_explicit():
    assert "AI-generated" in AI_NOTICE_HTML
    assert 'data-ai-generated="true"' in AI_NOTICE_HTML


def test_article_page_has_ai_notice():
    html = render_article_html(
        title="Test Journal",
        content_md="Hello **world**",
        summary="Sum",
        published_at=datetime(2026, 7, 1),
        week_start=datetime(2026, 6, 22),
        week_end=datetime(2026, 6, 28),
        slug="test-journal",
    )
    assert AI_NOTICE_HTML in html


def test_story_page_has_ai_notice():
    assert AI_NOTICE_HTML in render_story_html(_story())


def test_news_archive_listing_has_ai_notice():
    html = render_news_archive_html(
        [("July 30, 2026", [_story()])], total_count=1, page=1, total_pages=1
    )
    assert AI_NOTICE_HTML in html
```

Note: `_story()` supplies a superset of keys; if `render_story_html` requires an additional key at runtime, add it to `_story()` — do not change the renderer for the test's sake.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_ai_act_notices.py -v`
Expected: FAIL / ERROR with `ImportError: cannot import name 'AI_NOTICE_HTML'`.

- [ ] **Step 3: Add the shared notice constant**

In `pipeline/article_html_renderer.py`, after the `_footer_html()` function (ends ~line 236), add:

```python
# Art. 50(4) EU AI Act: visible disclosure on every AI-generated content page.
# The data attribute doubles as a lightweight machine-readable marker.
AI_NOTICE_HTML = (
    '<p class="ai-notice" data-ai-generated="true" '
    'style="border:1px solid rgba(176,141,87,.45);background:rgba(176,141,87,.1);'
    'padding:8px 12px;border-radius:6px;font-size:.85em;">'
    "AI-generated content: this page was produced automatically by an AI system. "
    "Always verify with the original sources.</p>"
)
```

- [ ] **Step 4: Render the notice on the three page types**

(a) In `render_article_html` (body at ~lines 314-324), insert `{AI_NOTICE_HTML}` between the closing `</div>` of the `meta` div and `<div class="article-body">`:

```html
                <span class="copy-ok" id="copyOk">Copied!</span>
            </div>
            {AI_NOTICE_HTML}
            <div class="article-body">
```

(b) In `render_story_html` (body at ~lines 680-686), same pattern:

```html
                &middot; <a href="/news.html">Live Feed</a>
            </div>
            {AI_NOTICE_HTML}
            <div class="article-body">
```

(c) In `render_news_archive_html`, locate the return f-string's `<main>` block (after line 520) and insert `{AI_NOTICE_HTML}` directly after the `<h1>...</h1>` heading line, e.g.:

```html
    <main class="container">
        <h1>Archaeology News Archive</h1>
        {AI_NOTICE_HTML}
```

(Anchor on the `<h1>` inside `<main>`; the exact heading text may differ — do not change it.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/pipeline/test_ai_act_notices.py -v`
Expected: 4 passed.

- [ ] **Step 6: Lint and commit**

```bash
ruff format pipeline/article_html_renderer.py tests/pipeline/test_ai_act_notices.py
ruff check pipeline/article_html_renderer.py tests/pipeline/test_ai_act_notices.py
git add pipeline/article_html_renderer.py tests/pipeline/test_ai_act_notices.py
git commit -m "feat(compliance): visible AI notice on SEO journal/story/archive pages (Art. 50(4))"
```

---

### Task 6: Research SEO pages — AI notice, honest wording, JSON-LD author fix

Three problems in `pipeline/research_html_renderer.py`: no explicit AI label on paper pages, the listing claims papers are "reviewed before publication" (false for batch papers), and JSON-LD declares `"author": {"@type": "Person", "name": "Theo"}` — an AI agent marked up as a human.

**Files:**
- Modify: `pipeline/research_html_renderer.py`
- Test: `tests/pipeline/test_ai_act_notices.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/pipeline/test_ai_act_notices.py`:

```python
from pipeline.research_html_renderer import render_research_paper_html


def _paper(author: str = "Theo") -> dict:
    return {
        "title": "Test Paper",
        "question": "What is tested?",
        "slug": "test-paper",
        "author": author,
        "summary": "Abstract.",
        "published_at": datetime(2026, 7, 1),
        "hero_image_url": None,
        "word_count": 1000,
        "sources_analyzed": 10,
        "quality_badge": "Gold",
        "attribution": f"{author}, Ancient Nerds — https://ancientnerds.com",
    }


def test_research_page_has_ai_notice():
    assert AI_NOTICE_HTML in render_research_paper_html(_paper(), "# Body")


def test_research_jsonld_theo_is_not_a_person():
    html = render_research_paper_html(_paper("Theo"), "# Body")
    assert '"@type": "Person", "name": "Theo"' not in html
    assert "AI research pipeline" in html


def test_research_jsonld_human_author_stays_person():
    html = render_research_paper_html(_paper("MrSchneebly"), "# Body")
    assert '"@type": "Person"' in html
    assert "MrSchneebly" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_ai_act_notices.py -v`
Expected: the three new tests FAIL (notice absent, Person-Theo present).

- [ ] **Step 3: Import the notice constant**

In `research_html_renderer.py`, extend the existing import block (starts line 15):

```python
from pipeline.article_html_renderer import (
    AI_NOTICE_HTML,
    ...existing names...
)
```

- [ ] **Step 4: Fix the JSON-LD author**

In `render_research_paper_html`, before the `schema = f"""..."""` block (~line 193), add:

```python
    if author == "Theo":
        author_schema = (
            '{"@type": "Organization", "name": "Ancient Nerds", '
            '"description": "Generated by Theo, the Ancient Nerds AI research pipeline"}'
        )
    else:
        author_schema = (
            f'{{"@type": "Person", "name": {_json_str(author)}, '
            f'"affiliation": {{"@type": "Organization", "name": "Ancient Nerds"}}}}'
        )
```

and in the schema f-string replace the hardcoded author line (currently line 199) with:

```python
        "author": {author_schema},
```

(`_json_str` is already imported from `article_html_renderer` — if not, add it to the import block.)

- [ ] **Step 5: Render the notice and qualify the byline**

(a) Insert `{AI_NOTICE_HTML}` before `<div class="article-body">` (~line 262):

```html
            </div>
            {AI_NOTICE_HTML}
            <div class="article-body">
```

(b) In the paper-meta-box byline (~line 258), change:

```html
                &middot; by {escape(author)}{word_count}{sources}
```

to (add before the f-string return, next to the `author_schema` logic):

```python
    author_label = f"{escape(author)} (AI research pipeline)" if author == "Theo" else escape(author)
```

```html
                &middot; by {author_label}{word_count}{sources}
```

(c) In the license box (~lines 265-270), after the "Machine-readable version via the public API." sentence, add:

```html
                This paper was generated by an AI system.
```

- [ ] **Step 6: Fix the listing wording**

In the Research Library listing (~lines 162-163), change:

```html
        <p class="meta">Deep-research papers on archaeology and ancient history, produced by the
        Theo convergence research pipeline and reviewed before publication.
```

to:

```html
        <p class="meta">Deep-research papers on archaeology and ancient history — AI-generated by
        Theo, the Ancient Nerds AI research pipeline, and published after automated quality and
        citation checks.
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/pipeline/test_ai_act_notices.py -v`
Expected: 7 passed.

- [ ] **Step 8: Lint and commit**

```bash
ruff format pipeline/research_html_renderer.py tests/pipeline/test_ai_act_notices.py
ruff check pipeline/research_html_renderer.py tests/pipeline/test_ai_act_notices.py
git add pipeline/research_html_renderer.py tests/pipeline/test_ai_act_notices.py
git commit -m "feat(compliance): AI notice + honest authorship on research SEO pages (Art. 50(4))"
```

---

### Task 7: Legal texts — imprint consistency and disclaimer scope

The imprint claims "journalistically-edited telemedia content" (editorial review) while Stories/Journals/batch papers publish fully automatically — this undermines Art. 50(4) compliance (the labeling route requires NOT claiming the review exception falsely). Also: the imprint's AI section omits research papers, and the landing-page disclaimer accordion scopes AI disclosure to "Story items" only.

**Files:**
- Modify: `ancient-nerds-map/imprint.html` (lines 65-68 and 82-83)
- Modify: `ancient-nerds-map/src/shared/disclaimerContent.ts` ("AI-Generated Content" accordion, ~lines 232-253)

- [ ] **Step 1: Rewrite the § 18 MStV paragraph**

In `imprint.html`, keep the heading "Responsible for Editorial Content", the "§ 18 (2) MStV" reference, and the named person (lines 65-67). Replace the paragraph at line 68:

```html
      <p>§ 18 MStV applies because Ancient Nerds publishes journalistically-edited telemedia content: curated archaeological stories, weekly journals (compilations summarising the previous week's stories), and the Lyra research assistant.</p>
```

with:

```html
      <p>Martin Dominiak is responsible for this service and its own content. Stories, weekly journals, and research papers on this platform are generated automatically by AI systems and are published without prior human editorial review; in accordance with Article 50(4) of Regulation (EU) 2024/1689 (AI Act), this content is labeled as AI-generated wherever it appears. Reported errors are reviewed and corrected by the operator (see Notice and Take-Down below).</p>
```

- [ ] **Step 2: Extend the AI-Generated Content section**

In `imprint.html` line 83, change the opening of the sentence:

```html
      <p>Stories, weekly journals, the Lyra research assistant, and other generated content on this platform are produced automatically by large language models from publicly available sources.
```

to:

```html
      <p>Stories, weekly journals, research papers, the Lyra research assistant, and other generated content on this platform are produced automatically by large language models from publicly available sources, without prior human editorial review.
```

(rest of the paragraph unchanged).

- [ ] **Step 3: Widen the disclaimer accordion scope**

In `disclaimerContent.ts`, locate the "AI-Generated Content" accordion (~lines 232-253). Its text currently scopes disclosure to "Story items"/"news content". Extend the first sentence so it covers all three content types — replace the sentence beginning "Story items are automatically generated by AI..." with:

```
Stories, weekly journals, and research papers are automatically generated by AI from publicly available sources (YouTube videos, academic databases, and open archaeological data).
```

Keep the remaining sentences ("...should be treated as AI-generated summaries, not original reporting..." etc.) unchanged, adjusting only subjects that say "Story items"/"news content" to "this content" where needed for grammar.

- [ ] **Step 4: Type-check**

Run: `cd ancient-nerds-map && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add ancient-nerds-map/imprint.html ancient-nerds-map/src/shared/disclaimerContent.ts
git commit -m "fix(compliance): imprint no longer claims editorial review; disclaimer covers all AI content"
```

---

### Task 8: AI literacy record (Art. 4)

Art. 4 has applied since 2025-02-02; a short written record is the whole compliance measure for a solo operator.

**Files:**
- Create: `docs/compliance/ai-literacy.md`

- [ ] **Step 1: Write the record**

Create `docs/compliance/ai-literacy.md`:

```markdown
# AI Literacy Record (Art. 4 EU AI Act)

**Operator:** Dominiak Consulting (sole proprietorship), Martin Dominiak — sole operator and developer.
**Last reviewed:** 2026-07-31

## Scope

Art. 4 AI Act requires providers and deployers to ensure a sufficient level of AI literacy
of persons operating AI systems on their behalf. AncientNerds is operated and developed by
a single person; no employees or contractors operate the AI systems.

## AI systems in operation

| System | Purpose | Models |
|---|---|---|
| Lyra news pipeline | Generates news stories from YouTube transcripts | Anthropic Claude (Haiku/Sonnet/Opus) |
| Lyra weekly journal | Weekly digest article generation | Anthropic Claude Opus |
| Lyra chat | Interactive RAG assistant | Anthropic Claude + Voyage AI embeddings |
| Theo research pipeline | Deep-research papers | MiniMax M3 |
| Theo TTS | Paper narration audio | MiniMax speech-2.8-hd |
| Radar site discovery | Site identification/enrichment | Claude + Mercury (Inception Labs) |

## Literacy measures

- The operator designs, builds, tests, and monitors all pipelines personally, including
  prompt design, output verification gates (hallucination gate, citation integrity gate,
  LLM quality judges), and incident handling — demonstrating working knowledge of LLM
  capabilities and failure modes (hallucination, citation fabrication, quota-related
  empty outputs).
- Known limitations are documented in-repo (`docs/research/`, project memory) and
  disclosed to users on every content surface ("AI-generated ... may contain errors").
- Regulatory tracking: EU AI Act obligations reviewed 2026-03-19 (initial analysis) and
  2026-07-31 (full audit, this plan); Commission guidelines of 2026-07-20 and the Code of
  Practice on marking/labelling (final 2026-06-10) reviewed.

## Review cadence

Revisit this record when: a new AI system goes into operation, a person other than the
operator begins operating the systems, or the Commission issues new Art. 4 guidance.
```

- [ ] **Step 2: Commit**

```bash
git add docs/compliance/ai-literacy.md
git commit -m "docs(compliance): AI literacy record (Art. 4 EU AI Act)"
```

---

### Task 9: Phase A verification gate

- [ ] **Step 1: Full frontend build**

Run: `cd ancient-nerds-map && npm run build`
Expected: build succeeds; verify `dist/` was produced (`ls dist/`). (Remember: `set -e` doesn't catch `&&`-chain failures — check output explicitly.)

- [ ] **Step 2: Full backend test suite**

Run: `python -m pytest tests/ -x -q`
Expected: all pass (same set that passed before this plan; no new failures).

- [ ] **Step 3: Lint gate**

Run: `ruff format --check api/ pipeline/ && ruff check api/ pipeline/`
Expected: clean.

- [ ] **Step 4: STOP — ask the user for permission to push/deploy**

Do NOT push without an explicit OK. Deploy is required before 2026-08-02 for Phase A to count.

---

## Phase B — machine-readable marking, Art. 50(2) (deadline 2026-12-02)

### Task 10: `ai_generated` / `ai_system` fields on all content API responses

> Follow-up from Task 4 review: the frontend byline hardcodes `'Theo'` (duplicating
> `THEO_AUTO_PUBLISH_AUTHOR` in `api/services/theo_config.py:27`) — once these API fields
> exist, consider switching `ResearchPaperPage.tsx` to key off them instead of the name.

Add machine-readable marking via Pydantic field defaults — the schemas are used exclusively for AI-generated content, so defaults are correct and no serialization call sites change.

**Files:**
- Modify: `api/schemas/public_v1.py` (`NewsItemPublic` ~line 172, `ArticleSummary` ~line 396, `ResearchPaperSummary` ~line 482)
- Modify: `api/routes/news.py` (`NewsItemResponse` ~line 76, `NewsArticleResponse` ~line 113)
- Test: `tests/api/test_ai_act_marking.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_ai_act_marking.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Art. 50(2) EU AI Act: machine-readable AI marking on content API schemas."""

import pytest

from api.routes.news import NewsArticleResponse, NewsItemResponse
from api.schemas.public_v1 import ArticleSummary, NewsItemPublic, ResearchPaperSummary


@pytest.mark.parametrize(
    ("schema", "expected_system"),
    [
        (NewsItemPublic, "lyra-news"),
        (NewsItemResponse, "lyra-news"),
        (ArticleSummary, "lyra-journal"),
        (NewsArticleResponse, "lyra-journal"),
        (ResearchPaperSummary, "theo-research"),
    ],
)
def test_content_schemas_carry_ai_marking(schema, expected_system):
    assert schema.model_fields["ai_generated"].default is True
    assert schema.model_fields["ai_system"].default == expected_system
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_ai_act_marking.py -v`
Expected: FAIL with `KeyError: 'ai_generated'`.

- [ ] **Step 3: Add the fields**

To each of the five schemas add (adjusting the `ai_system` default per the table in Step 1):

```python
    ai_generated: bool = Field(
        True,
        description=(
            "Machine-readable AI marking (Art. 50(2) EU AI Act): the text content of "
            "this item was generated by an AI system. Embedded images are sourced from "
            "the cited references, not AI-generated."
        ),
    )
    ai_system: str = Field(
        "lyra-news",
        description="Identifier of the generating AI pipeline",
    )
```

Note: `ArticleDetail`/`ResearchPaperDetail`/`NewsFeedPublicResponse` etc. inherit or embed these — no further changes. In `api/routes/news.py` the response models may use plain defaults without `Field`; match the file's existing style (`Field` is fine if already imported).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_ai_act_marking.py -v`
Expected: 5 passed.

- [ ] **Step 5: Update the public API self-description**

In `api/routes/public_v1.py`, in the FastAPI app description (~lines 193-201), append the line:

```
All news, article, and research content on this API is AI-generated and carries machine-readable `ai_generated` / `ai_system` fields (Art. 50 EU AI Act).
```

In the `/research` endpoint's OpenAPI description (~lines 1468-1478), replace "produced by the **Theo convergence research pipeline** and reviewed before publication" with "AI-generated by the **Theo research pipeline** and published after automated quality and citation checks".

- [ ] **Step 6: Lint and commit**

```bash
ruff format api/ tests/api/test_ai_act_marking.py
ruff check api/ tests/api/test_ai_act_marking.py
git add api/schemas/public_v1.py api/routes/news.py api/routes/public_v1.py tests/api/test_ai_act_marking.py
git commit -m "feat(compliance): machine-readable ai_generated/ai_system fields on content APIs (Art. 50(2))"
```

---

### Task 11: IPTC digitalSourceType in JSON-LD (all SEO renderers)

The IPTC "trainedAlgorithmicMedia" digital source type is the recognized machine-readable AI marker for web content (referenced by C2PA and the Code of Practice).

> **SCOPE CORRECTION (2026-07-31, post-Phase-A):** Embedded images in papers/articles are
> NOT AI-generated (real photos from Wikimedia/external sources — the pipeline only selects,
> never generates). The `digitalSourceType` marker describes the article TEXT. Never attach
> AI markers to `image` objects in JSON-LD, and the `ai_generated` API fields (Task 10) must
> be documented as covering the text content only (see the corrected field descriptions).

**Files:**
- Modify: `pipeline/article_html_renderer.py` (Article schema ~line 265, NewsArticle schema ~line 631)
- Modify: `pipeline/research_html_renderer.py` (ScholarlyArticle schema ~line 193)
- Test: `tests/pipeline/test_ai_act_notices.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/pipeline/test_ai_act_notices.py`:

```python
IPTC_AI_MARKER = "https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"


def test_jsonld_ai_marker_on_all_page_types():
    article = render_article_html(
        title="T", content_md="B", summary=None, published_at=datetime(2026, 7, 1),
        week_start=None, week_end=None, slug="t",
    )
    assert IPTC_AI_MARKER in article
    assert IPTC_AI_MARKER in render_story_html(_story())
    assert IPTC_AI_MARKER in render_research_paper_html(_paper(), "# Body")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/pipeline/test_ai_act_notices.py -v`
Expected: new test FAILS.

- [ ] **Step 3: Add the property to all three JSON-LD blocks**

In each `schema = f"""{{...}}"""` block (Article at ~265, NewsArticle at ~631, ScholarlyArticle at ~193), add directly after the `"@type"` line:

```
        "digitalSourceType": "https://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/pipeline/test_ai_act_notices.py -v`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
ruff format pipeline/ tests/pipeline/test_ai_act_notices.py
ruff check pipeline/ tests/pipeline/test_ai_act_notices.py
git add pipeline/article_html_renderer.py pipeline/research_html_renderer.py tests/pipeline/test_ai_act_notices.py
git commit -m "feat(compliance): IPTC trainedAlgorithmicMedia marker in JSON-LD (Art. 50(2))"
```

---

### Task 12: ID3 AI marking in generated TTS MP3s

Theo paper narration (MiniMax speech-2.8-hd) is synthetic audio → needs machine-readable marking. Embed ID3 TXXX frames at write time.

**Files:**
- Modify: `requirements.lyra.txt`
- Modify: `pipeline/lyra/tts_generator.py` (new function + call after MP3 write at ~line 312)
- Test: `tests/pipeline/test_tts_ai_marking.py` (new)

**Deploy note:** this code runs in the **lyra** container — needs `docker compose up -d --build lyra` on the VPS after deploy.

- [ ] **Step 1: Add the dependency**

Append to `requirements.lyra.txt`:

```
# ID3 tagging of generated TTS audio (Art. 50(2) EU AI Act marking)
mutagen>=1.47.0
```

Install locally: `pip install "mutagen>=1.47.0"`

- [ ] **Step 2: Write the failing test**

Create `tests/pipeline/test_tts_ai_marking.py`:

```python
# SPDX-License-Identifier: AGPL-3.0-only
"""Art. 50(2) EU AI Act: machine-readable AI marking in generated TTS MP3s."""

from mutagen.id3 import ID3

from pipeline.lyra.tts_generator import tag_mp3_ai_generated


def test_tag_mp3_ai_generated(tmp_path):
    f = tmp_path / "x.mp3"
    # Minimal MPEG frame header + padding — enough for ID3 to attach a tag.
    f.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 128)

    tag_mp3_ai_generated(f)

    frames = {fr.desc: str(fr.text[0]) for fr in ID3(f).getall("TXXX")}
    assert frames["AI-Generated"] == "true"
    assert "MiniMax" in frames["AI-System"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/pipeline/test_tts_ai_marking.py -v`
Expected: FAIL with `ImportError: cannot import name 'tag_mp3_ai_generated'`.

- [ ] **Step 4: Implement the tagging function**

In `pipeline/lyra/tts_generator.py`, add (near the other module-level functions, before `generate_paper_audio`):

```python
def tag_mp3_ai_generated(path) -> None:
    """Embed a machine-readable AI-generation marker (Art. 50(2) EU AI Act)."""
    from mutagen.id3 import ID3, ID3NoHeaderError, TXXX

    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(TXXX(encoding=3, desc="AI-Generated", text="true"))
    tags.add(
        TXXX(
            encoding=3,
            desc="AI-System",
            text="MiniMax speech-2.8-hd — Ancient Nerds Theo TTS",
        )
    )
    tags.save(path)
```

In `generate_paper_audio`, directly after the MP3 file is written to `out_path` (~line 312), add:

```python
    tag_mp3_ai_generated(out_path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/pipeline/test_tts_ai_marking.py -v`
Expected: 1 passed.

- [ ] **Step 6: Lint and commit**

```bash
ruff format pipeline/lyra/tts_generator.py tests/pipeline/test_tts_ai_marking.py
ruff check pipeline/lyra/tts_generator.py tests/pipeline/test_tts_ai_marking.py
git add requirements.lyra.txt pipeline/lyra/tts_generator.py tests/pipeline/test_tts_ai_marking.py
git commit -m "feat(compliance): ID3 AI-generation marking in TTS MP3s (Art. 50(2))"
```

---

### Task 13: Update the compliance analysis document

**Files:**
- Modify: `docs/research/EU_AI_Act_Compliance_Analysis.md`

- [ ] **Step 1: Add a status addendum**

At the top of the file (after the existing header block, before "## Executive Summary"), insert:

```markdown
> **ADDENDUM 2026-07-31 (supersedes stale statements below):**
> - Commission guidelines on Art. 50 adopted 2026-07-20; Code of Practice on marking &
>   labelling final since 2026-06-10, assessed adequate 2026-07-08/09.
> - AI-Omnibus grace period: Art. 50(2) machine-readable marking applies from
>   **2026-12-02** for systems in service before 2026-08-02 (ours). Art. 50(1) and 50(4)
>   apply 2026-08-02 without grace.
> - Correction to §10: the platform DOES generate synthetic audio (MiniMax speech-2.8-hd
>   paper narration, ElevenLabs video voiceover) — Art. 50(2) marking applies to it.
> - The Art. 50(4) editorial-review exception is NOT available: Lyra news, weekly
>   journals, and batch Theo papers publish fully automatically (LLM-only gates).
>   Compliance route is labeling (Option A), implemented via
>   `docs/superpowers/plans/2026-07-31-eu-ai-act-compliance.md`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/research/EU_AI_Act_Compliance_Analysis.md
git commit -m "docs(compliance): July 2026 status addendum to EU AI Act analysis"
```

---

### Task 14: Phase B verification gate

- [ ] **Step 1: Full backend test suite**

Run: `python -m pytest tests/ -q`
Expected: no new failures vs. pre-plan baseline.

- [ ] **Step 2: Lint gate**

Run: `ruff format --check api/ pipeline/ && ruff check api/ pipeline/`
Expected: clean.

- [ ] **Step 3: STOP — ask the user for permission to push/deploy**

After deploy, remind the user: manual `docker compose up -d --build lyra` on the VPS (Task 12), and spot-check `curl https://ancientnerds.com/api/v1/research?limit=1` for `"ai_generated": true`.
