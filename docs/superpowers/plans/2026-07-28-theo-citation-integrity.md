# Theo Citation Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee referential citation integrity of every published Theo paper by validating the rendered artifact (not the in-memory registry) and repairing defects deterministically — zero LLM calls, zero quota.

**Architecture:** Three pure functions in `pipeline/lyra/theo_citations.py` (`validate_paper_artifact`, `normalize_grouped_markers`, `repair_artifact`, composed by `validate_or_repair`) become the single integrity mechanism. The presentation handler re-renders the References list from the registry (fixing the verbatim-stale-block bug) and runs the artifact gate as the guaranteed last act. Both publish paths (manual route + worker auto-publish) recompute validation on the exact text being published. A CLI applies the same functions to stored papers (fixes the two pending papers + backfill sweep).

**Tech Stack:** Python 3.11, stdlib `re` only, pytest, SQLAlchemy (CLI), FastAPI (route). Spec: `docs/superpowers/specs/2026-07-28-theo-citation-integrity-design.md`.

**Conventions that bind every task:**
- NEVER duplicate a utility — extract and reuse (Task 1 creates the shared helpers).
- No fallback code, no silent except-pass. A paper that can't be repaired deterministically HOLDS.
- Run `ruff format pipeline/ api/ scripts/ tests/` and `ruff check` before every commit (CI enforces `ruff format --check`, ruff 0.15.11).
- Run tests with `python -m pytest <file> -v` from the repo root (`C:\PythonProjects\AncientMap`).
- Commit locally only. **NEVER push** — the user pushes explicitly.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `pipeline/lyra/theo_citations.py` | Modify | Add `split_artifact`, `_collect_non_numeric_markers` (extracted from `audit_citations`), `normalize_grouped_markers`, `validate_paper_artifact`, `repair_artifact`, `validate_or_repair`, `replace_references_section` |
| `tests/pipeline/test_theo_artifact_gate.py` | Create | All new tests (golden defect fixtures) |
| `pipeline/lyra/handlers/paper.py` | Modify (~261–273) | Step 7.4: normalize grouped markers before `finalize_references` |
| `pipeline/lyra/handlers/presentation.py` | Modify (~16–30, ~182–235) | Re-render refs from registry; final `validate_or_repair` gate; invariant comment |
| `api/routes/theo.py` | Modify (~1126–1250) | Publish gate recomputes on artifact; `?repair=1`; override no longer bypasses integrity |
| `api/services/theo_worker.py` | Modify (~444–536) | `_auto_publish` recomputes + auto-repairs; holds when dirty |
| `scripts/repair_theo_citations.py` | Create | Scan/repair stored papers (backfill + the two pending papers) |

---

### Task 1: Shared helpers — `split_artifact` + `_collect_non_numeric_markers`

The validator and repairer both need (a) a prose/heading/refs-body split and (b) the non-numeric-token scan that today lives inline in `audit_citations` (part 6). Extract, don't duplicate.

**Files:**
- Modify: `pipeline/lyra/theo_citations.py`
- Create: `tests/pipeline/test_theo_artifact_gate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/pipeline/test_theo_artifact_gate.py`:

```python
"""Artifact-level citation integrity: validate_paper_artifact + repair_artifact.

Golden fixtures mirror the real defect classes found 2026-07-28 in the
Kybalion and DMT papers (stray [N#] tokens, markers beyond the rendered
list, grouped [9, 7, 1] brackets, orphaned rendered refs, stale rendered
list vs registry).
"""

from pipeline.lyra.theo_citations import (
    _collect_non_numeric_markers,
    split_artifact,
)


def test_split_artifact_splits_on_first_heading():
    md = "# T\n\nProse [1].\n\n## References\n\n[1] A — https://a.example (accessed 2026-01-01)\n"
    prose, heading, body = split_artifact(md)
    assert "Prose [1]." in prose
    assert "References" not in prose
    assert heading.startswith("## References")
    assert "[1] A — https://a.example" in body


def test_split_artifact_no_heading_returns_all_prose():
    prose, heading, body = split_artifact("just prose, no refs")
    assert prose == "just prose, no refs"
    assert heading == ""
    assert body == ""


def test_split_artifact_handles_h3_and_sources():
    for h in ("### References", "## Sources"):
        prose, heading, body = split_artifact(f"P\n\n{h}\n\n[1] A — https://a.example\n")
        assert heading.startswith(h)


def test_collect_non_numeric_markers_finds_debug_and_grouped_tokens():
    prose = (
        "Claim [N1]. Another [N2]. Grouped [9, 7, 1]. Fine [3]. "
        "A [link](https://x.example) and a footnote [^1] are ignored."
    )
    tokens = _collect_non_numeric_markers(prose)
    assert "N1" in tokens
    assert "N2" in tokens
    assert "9, 7, 1" in tokens
    assert "3" not in tokens
    assert "link" not in tokens
    assert "^1" not in tokens
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_theo_artifact_gate.py -v`
Expected: FAIL — `ImportError: cannot import name 'split_artifact'`

- [ ] **Step 3: Implement the helpers**

In `pipeline/lyra/theo_citations.py`, directly below `_find_references_heading` (~line 1277), add:

```python
# ---------------------------------------------------------------------------
# Artifact splitting — shared by validate_paper_artifact / repair_artifact /
# replace_references_section / presentation's prose-vs-refs split
# ---------------------------------------------------------------------------

_REFS_HEADING_RE = re.compile(r"^#{2,3}\s+(?:References|Sources)\b.*$", re.MULTILINE)


def split_artifact(markdown: str) -> tuple[str, str, str]:
    """Split final paper markdown into (prose, heading_line, refs_body).

    Splits on the FIRST References/Sources heading (same anchor the frontend
    uses). heading_line includes the trailing newline when present. When no
    heading exists, everything is prose and heading/body are empty.
    """
    m = _REFS_HEADING_RE.search(markdown)
    if not m:
        return markdown, "", ""
    heading_end = markdown.find("\n", m.start())
    if heading_end == -1:
        return markdown[: m.start()], markdown[m.start() :], ""
    return (
        markdown[: m.start()],
        markdown[m.start() : heading_end + 1],
        markdown[heading_end + 1 :],
    )
```

Then extract the non-numeric scan. In `audit_citations`, replace the part-6 block (lines ~1227–1240, from `non_numeric_markers: list[str] = []` through `non_numeric_markers.append(token)` inclusive — keep the `if non_numeric_markers:` issue-append that follows) with:

```python
    non_numeric_markers = _collect_non_numeric_markers(prose_only)
```

and add the extracted helper just above `audit_citations`:

```python
def _collect_non_numeric_markers(prose: str) -> list[str]:
    """Bracketed tokens in prose that are not plain [N] citations.

    Catches pipeline debug IDs ([5620e1fb87f7]), [N1]-style writer artifacts,
    and grouped forms like [9, 7, 1] (grouped digits are NOT a valid marker —
    they are invisible to renumbering). Markdown links [x](y) are excluded via
    the negative lookahead; footnotes [^n] and [N - topic] placeholders (already
    counted separately) are skipped. Deduplicated, first-seen order.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\[([^\]\n]+)\](?!\()", prose):
        token = m.group(1).strip()
        if not token or token.isdigit():
            continue
        if token.startswith("^"):
            continue
        if _PLACEHOLDER_MARKER_RE.match(f"[{token}]"):
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out
```

- [ ] **Step 4: Run new tests + existing regression suite**

Run: `python -m pytest tests/pipeline/test_theo_artifact_gate.py tests/pipeline/test_theo_citations.py -v`
Expected: ALL PASS (the extraction must not change `audit_citations` behavior).

- [ ] **Step 5: Format, lint, commit**

```bash
ruff format pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
ruff check pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
git add pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
git commit -m "refactor(theo): extract split_artifact + non-numeric marker scan as shared helpers"
```

---

### Task 2: `normalize_grouped_markers`

**Files:**
- Modify: `pipeline/lyra/theo_citations.py`
- Test: `tests/pipeline/test_theo_artifact_gate.py`

- [ ] **Step 1: Write the failing tests** (append to `test_theo_artifact_gate.py`)

```python
from pipeline.lyra.theo_citations import normalize_grouped_markers


def test_normalize_grouped_markers_splits_groups():
    text, n = normalize_grouped_markers("Intro claim [9, 7, 1]. Next [2,3].")
    assert text == "Intro claim [9] [7] [1]. Next [2] [3]."
    assert n == 2


def test_normalize_grouped_markers_noop_without_groups():
    text, n = normalize_grouped_markers("Plain [1] and [2].")
    assert text == "Plain [1] and [2]."
    assert n == 0


def test_normalize_grouped_markers_leaves_refs_section_alone():
    md = "Prose [1, 2].\n\n## References\n\n[1] A, B — https://a.example\n"
    text, n = normalize_grouped_markers(md)
    assert n == 1
    assert "[1] [2]" in text
    assert "[1] A, B — https://a.example" in text  # refs untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_theo_artifact_gate.py -v -k grouped`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement** (in `theo_citations.py`, below `split_artifact`)

```python
_GROUPED_MARKER_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)+)\]")


def normalize_grouped_markers(text: str) -> tuple[str, int]:
    """Split grouped citation markers `[9, 7, 1]` into `[9] [7] [1]`.

    MUST run before finalize_references(): grouped digits are invisible to
    the `\\[(\\d+)\\]` renumbering regex, so an unsplit group keeps its OLD
    working numbers after renumbering — silent misattribution, worse than an
    orphan. Only prose is touched; the References section may legitimately
    contain commas inside titles. Returns (new_text, groups_split).
    """
    prose, heading, body = split_artifact(text)
    count = 0

    def _split(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return " ".join(f"[{n.strip()}]" for n in m.group(1).split(","))

    return _GROUPED_MARKER_RE.sub(_split, prose) + heading + body, count
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/pipeline/test_theo_artifact_gate.py -v`
Expected: PASS

- [ ] **Step 5: Format, lint, commit**

```bash
ruff format pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
ruff check pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
git add pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
git commit -m "feat(theo): normalize grouped [9, 7, 1] citation markers"
```

---

### Task 3: `validate_paper_artifact`

**Files:**
- Modify: `pipeline/lyra/theo_citations.py`
- Test: `tests/pipeline/test_theo_artifact_gate.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from pipeline.lyra.theo_citations import validate_paper_artifact

CLEAN_PAPER = """# Clean Paper

## Findings

The site dates to 9600 BC based on radiocarbon samples [1]. Excavations
revealed T-shaped pillars with animal reliefs carved in relief [2].

## References

[1] Radiocarbon dating at Gobekli Tepe — https://a.example/dating (accessed 2026-07-01) [Academic]
[2] T-shaped pillars survey — https://a.example/pillars (accessed 2026-07-01)
"""

# Kybalion-class defects: [N#] writer artifacts + markers beyond the rendered
# list + a rendered ref never cited.
KYBALION_CLASS = """# Hermeticism Paper

## Findings

The Corpus Hermeticum dates to late antiquity [N1], and the famous axiom is
a nineteenth-century paraphrase [N2] first printed in 1908 [1].

The Kybalion presents seven principles attributed to Hermes Trismegistus [2].

*Kybalion first edition, 1908 [4] [5]*

Atkinson published under several pseudonyms during his career [6].

## References

[1] Corpus Hermeticum dating — https://a.example/corpus (accessed 2026-07-01) [Academic]
[2] The Kybalion 1908 — https://a.example/kybalion (accessed 2026-07-01)
[3] Hermetic tradition overview — https://a.example/tradition (accessed 2026-07-01)
"""


def test_validate_passes_clean_paper():
    report = validate_paper_artifact(CLEAN_PAPER)
    assert report["passed"] is True
    assert report["total_references"] == 2
    assert report["issues"] == []


def test_validate_flags_kybalion_class_defects():
    report = validate_paper_artifact(KYBALION_CLASS)
    assert report["passed"] is False
    assert "N1" in report["non_numeric_markers"]
    assert "N2" in report["non_numeric_markers"]
    assert report["invalid_markers"] == [4, 5, 6]
    assert report["orphaned_refs"] == [3]
    # total_references counts the RENDERED list — the 50-vs-45 bug class.
    assert report["total_references"] == 3


def test_validate_flags_grouped_markers_as_non_numeric():
    md = CLEAN_PAPER.replace("samples [1]", "samples [1, 2]")
    report = validate_paper_artifact(md)
    assert report["passed"] is False
    assert "1, 2" in report["non_numeric_markers"]


def test_validate_flags_missing_references_section():
    report = validate_paper_artifact("# T\n\nProse with [1].\n")
    assert report["passed"] is False
    assert report["references_sections"] == 0
    assert any("no References section" in i for i in report["issues"])


def test_validate_flags_duplicate_references_sections():
    md = CLEAN_PAPER + "\n## References\n\n[9] Ghost — https://g.example\n"
    report = validate_paper_artifact(md)
    assert report["passed"] is False
    assert report["references_sections"] == 2


def test_validate_flags_unparseable_ref_line():
    md = CLEAN_PAPER.replace(
        "[2] T-shaped pillars survey — https://a.example/pillars (accessed 2026-07-01)",
        "Smith, J. (1998). Pillars. Antiquity.",
    )
    report = validate_paper_artifact(md)
    assert report["passed"] is False
    assert len(report["unparseable_ref_lines"]) == 1


def test_validate_flags_duplicate_and_noncontiguous_numbers():
    md = """# T

## Findings

Alpha claim about dating with plenty of detail attached [1]. Beta claim about
architecture with plenty of detail attached [4].

## References

[1] A — https://a.example (accessed 2026-07-01)
[1] B — https://b.example (accessed 2026-07-01)
[4] D — https://d.example (accessed 2026-07-01)
"""
    report = validate_paper_artifact(md)
    assert report["passed"] is False
    assert report["duplicate_ref_nums"] == [1]
    assert report["non_contiguous"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_theo_artifact_gate.py -v -k validate`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement** (in `theo_citations.py`, below `normalize_grouped_markers`)

```python
def validate_paper_artifact(markdown: str) -> dict:
    """Artifact-only citation integrity check — validates what readers see.

    Unlike audit_citations() this takes NO registry: it parses the rendered
    ## References list out of the markdown and checks the prose against it.
    Registry and rendered artifact can drift (injection assigns numbers after
    the list was rendered; presentation re-appended the stale block verbatim
    while prune mutated the registry) — this function is immune to the drift
    because it never sees the registry. Run it on the exact text being
    persisted or published.

    Returns the audit_result dict shape (superset): every audit_citations key
    plus references_sections, unparseable_ref_lines, duplicate_ref_nums,
    non_contiguous. `passed` is True iff `issues` is empty.
    """
    issues: list[str] = []

    references_sections = len(_REFS_HEADING_RE.findall(markdown))
    if references_sections == 0:
        issues.append("no References section found")
    elif references_sections > 1:
        issues.append(f"{references_sections} References/Sources headings (expected 1)")

    prose_only, _heading, refs_body = split_artifact(markdown)

    # Every non-empty rendered line must parse as a reference entry.
    parsed = parse_references_section(refs_body)
    parsed_nums = [r["num"] for r in parsed]
    unparseable_ref_lines: list[str] = []
    for line in refs_body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not (_RICH_REF_LINE_RE.match(stripped) or _REF_LINE_RE.match(stripped)):
            unparseable_ref_lines.append(stripped[:120])
    if unparseable_ref_lines:
        issues.append(
            f"{len(unparseable_ref_lines)} unparseable line(s) in References: "
            + "; ".join(unparseable_ref_lines[:3])
        )

    duplicate_ref_nums = sorted({n for n in parsed_nums if parsed_nums.count(n) > 1})
    if duplicate_ref_nums:
        issues.append(f"duplicate reference number(s): {duplicate_ref_nums}")

    ref_nums = set(parsed_nums)
    non_contiguous = bool(ref_nums) and sorted(ref_nums) != list(range(1, max(ref_nums) + 1))
    if non_contiguous:
        issues.append(f"reference numbers not contiguous 1..{max(ref_nums)}")

    marker_values = [int(m) for m in re.findall(r"\[(\d+)\]", prose_only)]
    total_citations = len(marker_values)
    unique_cited = set(marker_values)

    invalid_markers = sorted(unique_cited - ref_nums)
    for n in invalid_markers:
        issues.append(f"[{n}] cited in text but not in the rendered References list")

    orphaned_refs = sorted(ref_nums - unique_cited)
    for n in orphaned_refs:
        issues.append(f"[{n}] in References list but never cited in text")

    # Prose-quality checks — same helpers audit_citations uses, so the dict
    # keeps its full shape for the judge/UI.
    paragraphs_with_section = _split_prose_into_paragraphs(prose_only)
    factual = [p for s, p in paragraphs_with_section if _is_factual_paragraph(p, s)]
    uncited_paragraphs = sum(1 for p in factual if not re.search(r"\[\d+\]", p))
    if uncited_paragraphs:
        issues.append(
            f"{uncited_paragraphs} paragraph(s) longer than 50 chars contain no citation marker"
        )

    placeholder_markers = detect_placeholder_markers(prose_only)
    if placeholder_markers:
        issues.append(f"{len(placeholder_markers)} unresolved [N - topic] placeholder(s) in prose")

    language_bleed = detect_language_bleed(prose_only)
    if language_bleed:
        issues.append(
            f"{len(language_bleed)} non-Latin script segment(s) in prose: "
            + ", ".join(language_bleed[:3])
        )

    non_numeric_markers = _collect_non_numeric_markers(prose_only)
    if non_numeric_markers:
        sample = ", ".join(f"[{t}]" for t in non_numeric_markers[:5])
        issues.append(f"{len(non_numeric_markers)} non-numeric bracketed marker(s) in prose: {sample}")

    return {
        "passed": not issues,
        "total_citations": total_citations,
        "total_references": len(parsed),
        "orphaned_refs": orphaned_refs,
        "invalid_markers": invalid_markers,
        "uncited_paragraphs": uncited_paragraphs,
        "placeholder_markers": placeholder_markers,
        "language_bleed": language_bleed,
        "non_numeric_markers": non_numeric_markers,
        "references_sections": references_sections,
        "unparseable_ref_lines": unparseable_ref_lines,
        "duplicate_ref_nums": duplicate_ref_nums,
        "non_contiguous": non_contiguous,
        "issues": issues,
    }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/pipeline/test_theo_artifact_gate.py -v`
Expected: PASS

- [ ] **Step 5: Format, lint, commit**

```bash
ruff format pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
ruff check pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
git add pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
git commit -m "feat(theo): validate_paper_artifact — artifact-only citation integrity check"
```

---

### Task 4: `repair_artifact` + `validate_or_repair` + `replace_references_section`

**Files:**
- Modify: `pipeline/lyra/theo_citations.py`
- Test: `tests/pipeline/test_theo_artifact_gate.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from pipeline.lyra.theo_citations import (
    repair_artifact,
    replace_references_section,
    validate_or_repair,
)

# DMT-class defects: grouped marker + orphan high marker + rendered refs
# never cited (repair must drop them and renumber prose + list atomically).
DMT_CLASS = """# DMT Paper

## Findings

Strassman ran DEA-approved injections at UNM between 1990 and 1995 with
sixty volunteers enrolled [2, 1]. Later EEG work replicated the surge under
psilocybin in controlled settings [3]. A speculative claim cites nothing
real [6].

## References

[1] Strassman UNM study — https://a.example/strassman (accessed 2026-07-01) [Academic]
[2] DMT and the pineal — https://a.example/pineal (accessed 2026-07-01)
[3] EEG replication — https://a.example/eeg (accessed 2026-07-01) [Academic]
[4] Never cited A — https://a.example/na (accessed 2026-07-01)
[5] Never cited B — https://a.example/nb (accessed 2026-07-01)
"""


def test_repair_fixes_dmt_class_defects():
    repaired, report = repair_artifact(DMT_CLASS)
    assert report["passed"] is True
    # Grouped marker split, order preserved: [2, 1] -> [2] [1] -> renumbered [1] [2]
    assert "enrolled [1] [2]." in repaired
    # [3] keeps citing the EEG line, renumbered to [3] (first-use order 2,1,3)
    assert "settings [3]." in repaired
    # Orphan [6] stripped; never-cited refs [4] [5] dropped; list is 1..3
    assert "[6]" not in repaired
    assert "Never cited" not in repaired
    assert report["total_references"] == 3
    # Titles preserved verbatim on renumbered lines
    assert "[1] DMT and the pineal — https://a.example/pineal" in repaired
    assert "[2] Strassman UNM study — https://a.example/strassman" in repaired


def test_repair_strips_tokens_but_holds_kybalion_class():
    # [N1]/[N2] and [4][5][6] are stripped, ref [3] dropped — but stripping
    # [6] leaves the Atkinson paragraph uncited, so the repair must NOT
    # reach passed: the paper HOLDS for manual review instead of publishing
    # with an uncited factual claim.
    repaired, report = repair_artifact(KYBALION_CLASS)
    assert "[N1]" not in repaired
    assert "[N2]" not in repaired
    prose_part = repaired.split("## References")[0]
    assert "[4]" not in prose_part
    assert "[6]" not in prose_part
    assert report["passed"] is False
    assert report["uncited_paragraphs"] >= 1


def test_repair_is_idempotent():
    once, _ = repair_artifact(DMT_CLASS)
    twice, report = repair_artifact(once)
    assert twice == once
    assert report["passed"] is True


def test_repair_bails_on_unparseable_ref_line():
    md = DMT_CLASS.replace(
        "[4] Never cited A — https://a.example/na (accessed 2026-07-01)",
        "Some stray sentence in the references block.",
    )
    repaired, report = repair_artifact(md)
    assert report["passed"] is False
    # Original refs body untouched — no guessing against a broken list.
    assert "Some stray sentence" in repaired


def test_repair_holds_when_strip_creates_uncited_paragraph():
    md = """# T

## Findings

This entire factual paragraph about ancient metallurgy rests on one marker
that resolves to nothing at all [9].

## References

[1] Real ref — https://a.example/r (accessed 2026-07-01)
"""
    _repaired, report = repair_artifact(md)
    # [9] is stripped, [1] becomes orphaned -> dropped, paragraph now uncited.
    assert report["passed"] is False
    assert report["uncited_paragraphs"] >= 1


def test_validate_or_repair_returns_original_when_clean():
    text, report = validate_or_repair(CLEAN_PAPER)
    assert text == CLEAN_PAPER
    assert report["passed"] is True


def test_validate_or_repair_repairs_dirty_text():
    text, report = validate_or_repair(DMT_CLASS)
    assert report["passed"] is True
    assert "enrolled [1] [2]." in text


def test_replace_references_section_replaces_stale_block():
    stale = CLEAN_PAPER
    new_md = replace_references_section(stale, "[1] Only ref — https://o.example (accessed 2026-07-02)")
    assert "Only ref" in new_md
    assert "Radiocarbon dating" not in new_md
    assert new_md.count("## References") == 1


def test_replace_references_section_appends_when_missing():
    new_md = replace_references_section("# T\n\nProse [1].\n", "[1] R — https://r.example")
    assert "## References" in new_md
    assert "[1] R — https://r.example" in new_md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_theo_artifact_gate.py -v -k "repair or replace"`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement** (in `theo_citations.py`, below `validate_paper_artifact`)

```python
def replace_references_section(text: str, refs_md: str) -> str:
    """Replace (or append) the rendered References block with refs_md.

    Presentation renders the canonical list from the registry AFTER all
    injection/prune passes; this swaps out whatever stale block the text
    carries. Empty refs_md just drops the block.
    """
    prose, _heading, _body = split_artifact(text)
    if not refs_md:
        return prose.rstrip() + "\n"
    return prose.rstrip() + f"\n\n## References\n\n{refs_md}\n"


def _tidy_marker_whitespace(prose: str) -> str:
    """Collapse doubled spaces / space-before-punctuation left by marker strips."""
    prose = re.sub(r" {2,}", " ", prose)
    return re.sub(r" +([.,;:?!])", r"\1", prose)


def repair_artifact(markdown: str) -> tuple[str, dict]:
    """Deterministic citation repair. Never adds or remaps a citation.

    Order matters:
      1. split grouped markers so every digit is visible,
      2. strip non-numeric bracket tokens ([N1], [N - topic], [...], hex ids),
      3. strip numeric prose markers with no rendered list entry,
      4. drop rendered entries never cited in prose,
      5. renumber prose + list atomically to 1..M in first-citation order.

    Bails (steps 3-5 skipped) when the rendered list itself is broken — no
    refs section, a non-empty line that isn't `[N] ...`, or duplicate numbers.
    Repairing against a broken list would be guessing, and guessing is the
    failure mode this module exists to prevent. The caller must HOLD such
    papers, not publish them.

    Returns (repaired_markdown, validate_paper_artifact(repaired_markdown)).
    """
    text, _groups = normalize_grouped_markers(markdown)
    prose, heading, refs_body = split_artifact(text)

    # Step 2 — strip non-numeric bracket tokens from prose.
    def _drop_non_numeric(m: re.Match[str]) -> str:
        token = m.group(1).strip()
        if token.isdigit() or token.startswith("^"):
            return m.group(0)
        return ""

    prose = re.sub(r"\[([^\]\n]+)\](?!\()", _drop_non_numeric, prose)
    prose = _tidy_marker_whitespace(prose)

    # Parse the rendered list; bail on anything broken.
    line_by_num: dict[int, str] = {}
    broken = not heading
    for line in refs_body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^\[(\d+)\]\s+(.+)$", stripped)
        if m is None or int(m.group(1)) in line_by_num:
            broken = True
            break
        line_by_num[int(m.group(1))] = m.group(2)

    if broken:
        repaired = prose + heading + refs_body
        return repaired, validate_paper_artifact(repaired)

    # Step 3 — strip numeric markers with no rendered entry.
    ref_nums = set(line_by_num)

    def _drop_invalid(m: re.Match[str]) -> str:
        return m.group(0) if int(m.group(1)) in ref_nums else ""

    prose = re.sub(r"\[(\d+)\](?!\()", _drop_invalid, prose)
    prose = _tidy_marker_whitespace(prose)

    # Steps 4+5 — first-citation order, renumber prose and rebuild the list.
    order: list[int] = []
    seen: set[int] = set()
    for m in re.finditer(r"\[(\d+)\](?!\()", prose):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            order.append(n)
    old_to_new = {old: new for new, old in enumerate(order, start=1)}

    prose = re.sub(
        r"\[(\d+)\](?!\()", lambda m: f"\x00{old_to_new[int(m.group(1))]}\x00", prose
    )
    prose = re.sub(r"\x00(\d+)\x00", r"[\1]", prose)

    new_lines = [f"[{old_to_new[old]}] {line_by_num[old]}" for old in order]
    repaired = replace_references_section(prose, "\n".join(new_lines))
    return repaired, validate_paper_artifact(repaired)


def validate_or_repair(markdown: str) -> tuple[str, dict]:
    """Validate; on failure attempt the deterministic repair once.

    Returns (text, report). The text is only replaced when the repair reaches
    a passing state — a still-failing repair returns the ORIGINAL text with
    the original failing report, so callers hold the unmodified paper.
    """
    report = validate_paper_artifact(markdown)
    if report["passed"]:
        return markdown, report
    repaired, repaired_report = repair_artifact(markdown)
    if repaired_report["passed"]:
        return repaired, repaired_report
    return markdown, report
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/pipeline/test_theo_artifact_gate.py -v`
Expected: PASS

- [ ] **Step 5: Format, lint, commit**

```bash
ruff format pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
ruff check pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
git add pipeline/lyra/theo_citations.py tests/pipeline/test_theo_artifact_gate.py
git commit -m "feat(theo): deterministic repair_artifact + validate_or_repair gate"
```

---

### Task 5: Pipeline integration — paper.py Step 7.4 + presentation re-render & final gate

**Files:**
- Modify: `pipeline/lyra/handlers/paper.py` (~lines 261–273)
- Modify: `pipeline/lyra/handlers/presentation.py` (~lines 16–30 and 182–235)

- [ ] **Step 1: paper.py — normalize before finalize**

In the import block at line 261–267, add `normalize_grouped_markers`:

```python
        from pipeline.lyra.theo_citations import (
            audit_citations,
            finalize_references,
            normalize_grouped_markers,
            strip_existing_references_section,
            strip_orphan_citation_markers,
            strip_uncited_factual_paragraphs,
        )
```

Directly before the `finalize_references` call (line ~269), insert:

```python
        # ---------------------------------------------------------------
        # Step 7.4: Split grouped markers `[9, 7, 1]` -> `[9] [7] [1]`.
        # Grouped digits are invisible to the renumbering regex below — an
        # unsplit group would keep its OLD working numbers after
        # finalize_references and point at the wrong sources.
        # ---------------------------------------------------------------
        self.state.paper_text, _groups_split = normalize_grouped_markers(self.state.paper_text)
        if _groups_split:
            self.state.log("paper", f"Split {_groups_split} grouped citation marker(s)")
```

- [ ] **Step 2: presentation.py — delegate the split helper**

Replace `_split_paper_for_presentation` (lines 16–30) with a delegation to the shared splitter (its old regex missed `### References` / `## Sources`):

```python
from pipeline.lyra.theo_citations import split_artifact


def _split_paper_for_presentation(paper_text: str) -> tuple[str, str]:
    """Split into (prose, refs_block) on the first References/Sources heading.

    Delegates to theo_citations.split_artifact so every consumer agrees on
    the same anchor (the old local regex missed ### References / ## Sources).
    """
    prose, heading, body = split_artifact(paper_text)
    if not heading:
        return paper_text, ""
    return prose, heading + body
```

(Keep the module's existing `import re` only if still used elsewhere in the file; remove it if this was the last user — check with `ruff check`.)

- [ ] **Step 3: presentation.py — re-render refs + final artifact gate**

In the import block at lines 182–188, add the new names:

```python
        from pipeline.lyra.theo_citations import (
            prune_orphaned_references,
            prune_unrenderable_references,
            replace_references_section,
            strip_debug_tokens,
            strip_uncited_factual_paragraphs,
            validate_or_repair,
        )
```

(`audit_citations` is no longer imported here — the artifact gate replaces it.)

Replace lines 216–235 (`unrenderable = ...` through the second `self.state.log(...)` inclusive) with:

```python
            unrenderable = prune_unrenderable_references(self.state.registry)
            self.state.post_presentation_unrenderable_pruned = unrenderable

            # Re-render the References list from the (now-pruned) registry and
            # replace the stale block re-appended verbatim above. Without this,
            # injection/prune mutate the registry AFTER the list was rendered
            # and the published artifact drifts from the audit (Kybalion:
            # prose cited [46]-[50], rendered list stopped at [45]).
            refs_md = self.state.registry.format_references_list()
            self.state.paper_text = replace_references_section(self.state.paper_text, refs_md)

            # Final artifact gate — validates ONLY the rendered markdown, then
            # applies the deterministic repair when needed. INVARIANT: no LLM
            # pass may touch paper_text after this point; any new stage that
            # mutates prose must run before this block.
            self.state.paper_text, report = validate_or_repair(self.state.paper_text)
            self.state.audit_result = report
            self.state.log(
                "presentation",
                f"Post-presentation strip: seen={post_strip_metrics.get('uncited_seen', 0)}, "
                f"injected={post_strip_metrics.get('injected', 0)}, "
                f"dropped={post_strip_metrics.get('dropped', 0)}, "
                f"restored_sections={post_strip_metrics.get('restored_sections', 0)}, "
                f"pruned_orphans={pruned}, "
                f"pruned_unrenderable={unrenderable}",
            )
            self.state.log(
                "presentation",
                f"Artifact gate: passed={report.get('passed')}, "
                f"refs={report.get('total_references')}, "
                f"non_numeric={len(report.get('non_numeric_markers') or [])}, "
                f"invalid={len(report.get('invalid_markers') or [])}, "
                f"orphaned={len(report.get('orphaned_refs') or [])}, "
                f"uncited={report.get('uncited_paragraphs', 0)}",
            )
```

Note: `paper.py` Step 9 still appends the refs list for the pre-presentation state — presentation's `replace_references_section` swaps it for the final render. The mid-pipeline `audit_citations` call in paper.py Step 8 stays: it audits the registry state before coherence/presentation and is overwritten by the artifact gate at the end.

- [ ] **Step 4: Run the full pipeline test suite (regressions)**

Run: `python -m pytest tests/pipeline/ -v --timeout=120`
Expected: PASS (in particular `test_strip_injection_integration.py`, `test_verifier_references_intact.py`, `test_strip_debug_tokens.py`, `test_paper_repair_pass.py`).

- [ ] **Step 5: Format, lint, commit**

```bash
ruff format pipeline/lyra/handlers/paper.py pipeline/lyra/handlers/presentation.py
ruff check pipeline/lyra/handlers/paper.py pipeline/lyra/handlers/presentation.py
git add pipeline/lyra/handlers/paper.py pipeline/lyra/handlers/presentation.py
git commit -m "fix(theo): re-render refs after registry mutation; artifact gate as final pipeline act"
```

---

### Task 6: Publish route — recompute on artifact, `?repair=1`, override no longer bypasses integrity

**Files:**
- Modify: `api/routes/theo.py` (~lines 1126–1250)

- [ ] **Step 1: Add the `repair` query param**

In the `publish_research` signature (lines 1127–1133), after the `override` param add:

```python
    repair: int = Query(default=0, ge=0, le=1),
```

- [ ] **Step 2: Restrict the stored-audit gate to the judge score**

Replace the gate block (lines 1184–1219, from `# Quality gate — require judge.passed AND audit.passed...` through the `logger.warning(...)` call inclusive) with:

```python
        # Quality gate — the judge score is override-able; citation integrity
        # is NOT (it is recomputed on the artifact below, after assembly —
        # the stored audit can be stale and is informational only).
        quality_score = result.get("quality_score") or {}
        quality_passed = bool(quality_score.get("passed"))
        if not quality_passed:
            override_reason = (x_theo_override_reason or "").strip()
            if not (override and override_reason):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "quality_gate_failed",
                        "quality_passed": quality_passed,
                        "failing_metrics": ["quality_score.passed"],
                        "hint": (
                            "Pass ?override=1 with a non-empty X-Theo-Override-Reason "
                            "header to publish anyway."
                        ),
                    },
                )
            logger.warning(
                "Theo publish override: request_id=%s user=%s quality_passed=%s reason=%r",
                request_id,
                user.username,
                quality_passed,
                override_reason,
            )
```

- [ ] **Step 3: Add the artifact gate after assembly**

Directly after the legacy-workflow `assembled = {...}` block (line ~1249), insert:

```python
        # Citation-integrity gate — recomputed on the EXACT text being
        # published. Block-level rejections can orphan refs, and the stored
        # audit may predate later mutations. `?repair=1` applies the
        # deterministic repair (never fabricates or remaps a citation).
        from pipeline.lyra.theo_citations import repair_artifact, validate_paper_artifact

        publish_text = assembled["published_report"]
        artifact_report = validate_paper_artifact(publish_text)
        if not artifact_report["passed"] and repair:
            repaired_text, repaired_report = repair_artifact(publish_text)
            if repaired_report["passed"]:
                assembled["published_report"] = repaired_text
                artifact_report = repaired_report
        if not artifact_report["passed"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "citation_integrity_failed",
                    "issues": (artifact_report.get("issues") or [])[:10],
                    "hint": (
                        "Pass ?repair=1 to apply the deterministic citation repair, "
                        "or run scripts/repair_theo_citations.py. Override cannot "
                        "bypass this gate."
                    ),
                },
            )
        result["audit"] = artifact_report
```

`dry_run=1` still returns before persisting, so `?repair=1&dry_run=1` previews the repaired text without writing.

- [ ] **Step 4: Verify + lint**

Run: `python -m pytest tests/api/ -v --timeout=120` (regression — no existing test covers this route's gate; expect PASS)
Run: `ruff format api/routes/theo.py && ruff check api/routes/theo.py`

- [ ] **Step 5: Commit**

```bash
git add api/routes/theo.py
git commit -m "feat(theo): publish gate recomputes citation integrity on the artifact; ?repair=1"
```

---

### Task 7: Worker auto-publish — recompute + auto-repair, hold when dirty

**Files:**
- Modify: `api/services/theo_worker.py` (~lines 469–501, 515)

- [ ] **Step 1: Replace the stored-audit check in `_auto_publish`**

Replace lines 469–472 (`result = json.loads(...)` through `if not (quality.get("passed") and audit.get("passed")):`) with:

```python
            result = json.loads(row.result_json) if row.result_json else {}
            quality = result.get("quality_score") or {}

            # Citation integrity is recomputed on the artifact — the stored
            # audit can be stale. The deterministic repair never fabricates
            # or remaps a citation, so auto-publish may apply it directly.
            from pipeline.lyra.theo_citations import validate_or_repair

            report_text = result.get("report") or ""
            repaired_text, artifact_report = validate_or_repair(report_text)
            if repaired_text != report_text:
                logger.info("[THEO] Auto-repaired citations for %s before publish", request_id)
                result["report"] = repaired_text
            result["audit"] = artifact_report

            if not (quality.get("passed") and artifact_report["passed"]):
```

- [ ] **Step 2: Fix the hold-path log + webhook fields**

Inside the hold branch (old lines 473–501), replace every `audit.get("passed")` with `artifact_report["passed"]` and `audit.get("issues")` with `artifact_report.get("issues")`. The two spots:

```python
                logger.warning(
                    "[THEO] Auto-publish gate failed for %s (quality=%s audit=%s) — held.",
                    request_id,
                    quality.get("passed"),
                    artifact_report["passed"],
                )
```

and in the webhook embed description:

```python
                                        f"quality_passed={quality.get('passed')} "
                                        f"audit_passed={artifact_report['passed']}\n"
                                        f"issues: {(artifact_report.get('issues') or [])[:3]}"
```

Line 515 (`result["published_report"] = result.get("report") or ""`) needs no change — the repaired text flows through `result["report"]`.

- [ ] **Step 3: Verify + lint**

Run: `python -m pytest tests/api/test_theo_worker_pacing.py tests/api/test_theo_worker_quota.py tests/api/test_theo_worker_stall_guard.py -v` (regressions)
Run: `ruff format api/services/theo_worker.py && ruff check api/services/theo_worker.py`

- [ ] **Step 4: Commit**

```bash
git add api/services/theo_worker.py
git commit -m "feat(theo): auto-publish recomputes citation integrity, auto-repairs, holds when dirty"
```

---

### Task 8: Repair CLI + backfill — `scripts/repair_theo_citations.py`

**Files:**
- Create: `scripts/repair_theo_citations.py`

- [ ] **Step 1: Write the script**

```python
"""Scan / repair citation integrity of stored Theo research papers.

Runs validate_paper_artifact over every completed research_requests row and
optionally applies the deterministic repair_artifact (never fabricates or
remaps a citation — unrepairable papers are reported and left untouched).

Usage (inside the api container, or locally with DATABASE_URL on the tunnel):

  docker exec ancient_nerds_api python scripts/repair_theo_citations.py
  docker exec ancient_nerds_api python scripts/repair_theo_citations.py --apply <id> [<id> ...]
  docker exec ancient_nerds_api python scripts/repair_theo_citations.py --apply --all-dirty

Local (Bitvise tunnel, psql port 15432):
  DATABASE_URL=postgresql://ancient_map:<pw>@localhost:15432/ancient_map \\
    python scripts/repair_theo_citations.py

For published papers whose published_report changed, re-run Qdrant indexing
on the VPS afterwards (pipeline.lyra.theo_research_index) — this script only
prints a reminder, it does not reach Qdrant.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from pipeline.database import get_session  # noqa: E402
from pipeline.lyra.theo_citations import repair_artifact, validate_paper_artifact  # noqa: E402


def _fetch_rows(session):
    return session.execute(
        text("""
            SELECT id::text, slug, is_public, result_json
            FROM research_requests
            WHERE status = 'completed' AND result_json IS NOT NULL
            ORDER BY created_at
        """)
    ).fetchall()


def _repair_field(result: dict, field: str) -> tuple[bool, dict]:
    """Repair one markdown field in result_json. Returns (changed, report)."""
    original = result.get(field) or ""
    if not original:
        return False, {"passed": False, "issues": [f"{field} empty"]}
    repaired, report = repair_artifact(original)
    if report["passed"] and repaired != original:
        result[field] = repaired
        return True, report
    return False, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", nargs="*", metavar="ID", default=None,
                    help="Repair the given request ids (with --all-dirty: every failing row)")
    ap.add_argument("--all-dirty", action="store_true",
                    help="With --apply: repair every row that fails validation")
    args = ap.parse_args()

    apply_ids = set(args.apply or [])
    dirty = held = clean = 0

    with get_session() as session:
        for row in _fetch_rows(session):
            result = json.loads(row.result_json)
            report_md = result.get("report") or ""
            verdict = validate_paper_artifact(report_md)
            if verdict["passed"]:
                clean += 1
                continue

            dirty += 1
            label = row.slug or row.id
            print(f"\nDIRTY  {row.id}  ({label})  public={row.is_public}")
            for issue in verdict["issues"][:8]:
                print(f"       - {issue}")

            should_apply = args.apply is not None and (
                args.all_dirty or row.id in apply_ids
            )
            if not should_apply:
                continue

            changed, rep = _repair_field(result, "report")
            pub_changed = False
            if result.get("published_report"):
                pub_changed, _pub_rep = _repair_field(result, "published_report")
            if not rep["passed"]:
                held += 1
                print(f"HOLD   {row.id} — repair could not reach clean:")
                for issue in rep["issues"][:5]:
                    print(f"       - {issue}")
                continue

            result["audit"] = rep
            session.execute(
                text("UPDATE research_requests SET result_json = :r WHERE id = :id"),
                {"id": row.id, "r": json.dumps(result)},
            )
            session.commit()
            print(f"FIXED  {row.id}  (report={'yes' if changed else 'already-clean'}, "
                  f"published_report={'yes' if pub_changed else 'n/a'})")
            if row.is_public and pub_changed:
                print(f"       NOTE: re-index {row.id} in Qdrant on the VPS")

    print(f"\nScanned: clean={clean} dirty={dirty} held={held}")
    return 1 if (dirty and args.apply is None) else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-test locally without a DB (import + argparse only)**

Run: `python scripts/repair_theo_citations.py --help`
Expected: usage text prints, exit 0. (A live-DB scan happens in Task 9's verification.)

- [ ] **Step 3: Format, lint, commit**

```bash
ruff format scripts/repair_theo_citations.py
ruff check scripts/repair_theo_citations.py
git add scripts/repair_theo_citations.py
git commit -m "feat(theo): repair_theo_citations CLI — scan/repair stored papers"
```

---

### Task 9: Full verification + handover notes

- [ ] **Step 1: Full local test run**

Run: `python -m pytest tests/ -v --timeout=180`
Expected: PASS (memory: 6 pre-existing failures were fixed 2026-07-26; anything newly red must be fixed before proceeding).

- [ ] **Step 2: Full lint pass exactly as CI runs it**

Run: `ruff check api/ pipeline/ && ruff format --check api/ pipeline/`
Expected: clean. Fix and re-run if not.

- [ ] **Step 3: Final commit if anything changed**

```bash
git add -A
git commit -m "chore(theo): citation-integrity gate — lint/test fixups"
```

(Skip if the tree is clean.)

- [ ] **Step 4: Report the deploy + rollout checklist to the user (do NOT execute it unprompted)**

Present this checklist and stop:

1. **Push** — user pushes (never push unprompted). Deploy rebuilds `api` (route + worker changes live). Pipeline changes need the manual lyra rebuild: `ssh ancientnerds "cd /var/www/ancientnerds && docker compose up -d --build lyra"`.
2. **Backfill scan (read-only):** `ssh ancientnerds "docker exec ancient_nerds_api python scripts/repair_theo_citations.py"` — shows every stored dirty paper, applies nothing.
3. **Fix the two pending papers:** `... repair_theo_citations.py --apply <kybalion-id> <dmt-id>` — then review + publish them normally (publish now revalidates server-side; `?override=1` can no longer skip citation integrity).
4. **Optional full backfill:** `--apply --all-dirty` after reviewing the scan output.

---

## Self-Review Notes

- **Spec coverage:** validator (Task 3), normalizer pre-finalize (Tasks 2+5), repair (Task 4), presentation re-render + final gate + invariant (Task 5), publish-route recompute + `?repair=1` + override restriction (Task 6), auto-publish recompute/hold (Task 7), CLI/backfill (Task 8), golden-fixture + idempotence tests (Tasks 1–4), failure path = hold (Tasks 4, 7, 8). Non-goals untouched.
- **Type consistency:** `split_artifact -> (prose, heading, body)` used identically in Tasks 1, 2, 4, 5; `validate_or_repair -> (text, report)` in Tasks 4, 5, 7; `repair_artifact -> (text, report)` in Tasks 4, 6, 8. Report dict keys match `audit_citations` superset defined in Task 3.
- **Known behavior change (intentional, per spec):** papers whose only defect leaves a paragraph uncited after stripping will HOLD rather than publish — honest per the failure path. The stored audit becomes informational; the artifact gate is authoritative at publish time.
