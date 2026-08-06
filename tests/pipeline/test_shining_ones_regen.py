"""End-to-end verification that regenerating Shining Ones satisfies the 14
criteria that the full-fix sprint was designed to enforce.

This test makes real LLM calls and hits the registered source adapters.
It is slow (~10-30 minutes) and not appropriate for per-commit CI.
Gated on THEO_REGEN_TEST=1 env var so it only runs when explicitly
requested (nightly CI job or manual invocation).

Criteria (numbered to match the spec):
  1. No "David Kisheton" / "Kisheton" string.
  2. No "Grayson and Mellon" / "Fingerprints of the Fraud".
  3. No non-numeric bracketed tokens except markdown links and footnotes.
  4. "Shining Ones" defined in first 500 words.
  5. Watchers/Book of Enoch addressed (>=3 paragraphs).
  6. Giza pyramids addressed (>=3 paragraphs).
  7. Quantum-manipulation sub-question addressed (>=3 paragraphs).
  8. <=5% uncited factual paragraphs.
  9. No multi-URL reference entries.
  10. Every paragraph has distinct image subjects.
  11. (Manual browser check: carousel renders.)
  12. No severe cross-section contradictions.
  13. (Manual: card description matches conclusion.)
  14. Pipeline passes all judge+audit gates without override.
"""

import os
import re

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("THEO_REGEN_TEST") != "1",
    reason="Set THEO_REGEN_TEST=1 to run the live Shining Ones regen",
)

SHINING_ONES_QUESTION = (
    "I was always pondering about the Legends of the so called Shining Ones. "
    "What if these were beings from other planets coming to earth, interacting "
    "with early humans, giving them knowledge which results in stories about "
    "ancient egypt gods or Hermes Trismegistus or others like Quetzalcoatle that "
    "came from the skies? What if these beings are so enhanced that we cannot "
    "comprehend it. Could they have skills like manipulating matter via quantum "
    "mechanics to form ancient unexplainable structures like megalithic walls "
    "and polygonal masonry? Please investigate and try to connect the dots on "
    "what you can find! Make sure look left and right and not be contained to "
    "my specific question to connect the dots!"
)


@pytest.mark.asyncio
async def test_shining_ones_regen_satisfies_criteria():
    """Run the full Theo pipeline end-to-end and assert the automatable subset
    of the 14 verification criteria. Criteria 11 and 13 require manual
    browser / human review and are not asserted here.
    """
    # Local import so module imports don't require a full pipeline env when
    # the test is skipped.
    from pipeline.lyra.orchestrator import run_research

    result = await run_research(SHINING_ONES_QUESTION)
    body = result["result"]["report"]
    meta = result["result"]["quality_score"]["meta"]
    audit = result["result"]["audit"]

    # 1. No Kisheton fabrication.
    assert "Kisheton" not in body, "Fabricated name 'Kisheton' present"
    # 2. No Grayson & Mellon fabrication.
    assert "Grayson and Mellon" not in body
    assert "Fingerprints of the Fraud" not in body
    # 3. No non-numeric bracketed tokens (excluding markdown link syntax `[x](y)`
    #    and footnote `[^n]`).
    non_numeric = re.findall(r"\[([^\]\n]+)\](?!\()", body)
    offenders = [
        t for t in non_numeric if not (t.isdigit() or t.startswith("^") or t.startswith("N -"))
    ]
    assert not offenders, f"Non-numeric bracketed tokens leaked: {offenders!r}"
    # 4. "Shining Ones" defined in first 500 words of body.
    first_500 = " ".join(body.split()[:500]).lower()
    assert "shining ones" in first_500, "Title concept 'Shining Ones' not defined early"
    # 5-7. Canonical + user-subquestion coverage via paragraph counts.
    paragraphs = [p for p in body.split("\n\n") if len(p.strip()) > 80]
    watchers = sum(1 for p in paragraphs if "watcher" in p.lower() or "book of enoch" in p.lower())
    assert watchers >= 3, f"Watchers/Enoch under-covered ({watchers} paragraphs)"
    giza = sum(1 for p in paragraphs if "giza" in p.lower() or "great pyramid" in p.lower())
    assert giza >= 3, f"Giza under-covered ({giza} paragraphs)"
    quantum = sum(1 for p in paragraphs if "quantum" in p.lower())
    assert quantum >= 3, (
        f"User's quantum-manipulation sub-question under-addressed ({quantum} paragraphs)"
    )
    # 8. <=5% uncited factual paragraphs.
    total_factual = len(paragraphs)
    uncited_ratio = audit.get("uncited_paragraphs", 0) / max(total_factual, 1)
    assert uncited_ratio <= 0.05, f"Too many uncited paragraphs: {uncited_ratio:.0%}"
    # 9. No multi-URL reference entries.
    refs_text = body.split("\n## References", 1)[-1]
    for line in refs_text.splitlines():
        if line.strip().startswith("["):
            http_count = line.count("http://") + line.count("https://")
            assert http_count <= 1, f"Multi-URL reference entry: {line!r}"
    # 10. Distinct image subjects per paragraph — best-effort: no duplicate
    # image filename stems next to each other.
    img_lines = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", body)
    for i in range(1, len(img_lines)):
        # If two adjacent images share the same first-30-char stem, fail.
        stem_a = img_lines[i - 1].rsplit("/", 1)[-1][:30]
        stem_b = img_lines[i].rsplit("/", 1)[-1][:30]
        assert stem_a != stem_b, f"Adjacent duplicate image stems: {stem_a!r}"
    # 12. No severe cross-section contradictions.
    assert meta.get("coherence_contradictions", 0) == 0, (
        f"Coherence pass flagged contradictions: {meta.get('coherence_contradictions')}"
    )
    assert not meta.get("coherence_undefined_title_terms"), (
        f"Undefined title terms: {meta.get('coherence_undefined_title_terms')!r}"
    )
    # 14. Pipeline gate passes without override.
    assert result["result"]["quality_score"]["passed"] is True
    assert audit["passed"] is True
