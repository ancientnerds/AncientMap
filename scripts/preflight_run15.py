"""Run 15 pre-flight measurements for the content-QA fix plan.

Measures each tunable threshold against Run 15's archived data BEFORE shipping
the change to Run 16. Each check has a pass/fail criterion documented in the
plan at C:\\Users\\marti\\.claude\\plans\\omg-we-need-to-lively-balloon.md.

Run:
    python scripts/preflight_run15.py
    python scripts/preflight_run15.py --live   # also runs PF-2 (verifier) + PF-5 (prompt) via LLM

Run 15 archive files expected at $TMP/run15*.json (already present from the
audit pass).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Make pipeline importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.lyra.image_gates import metadata_gate_passes
from pipeline.lyra.image_fetcher import ImageCandidate
from pipeline.lyra.theo_citations import (
    CitationRegistry,
    CitedSource,
    ClaimCitation,
    inject_citation_for_paragraph,
    score_tier_by_domain,
)


TMP = os.environ.get("TMP", os.environ.get("TEMP", "/tmp"))


def _load(name: str):
    with open(os.path.join(TMP, name), encoding="utf-8") as f:
        return json.load(f)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


# ---------------------------------------------------------------------------
# PF-1 — tier floor simulation
# ---------------------------------------------------------------------------

def pf1_tier_floor() -> CheckResult:
    """Simulate tier-floor on Run 15 refs by domain-scoring each URL.

    The archive doesn't include the LLM-assigned reliability_tier per source,
    but score_tier_by_domain (the deterministic domain heuristic) is what the
    LLM audit's tier assignments mostly track. Use it to predict acceptance
    counts under the new floor (drop tier-3 when tier1+tier2 >= 3).
    """
    refs = _load("run15_refs.json")
    tiers = []
    for num, src in refs.items():
        url = src.get("url", "")
        tier = score_tier_by_domain(url)
        domain = urlparse(url).netloc.lower().replace("www.", "")
        tiers.append((num, tier, domain))

    t1 = sum(1 for _, t, _ in tiers if t == 1)
    t2 = sum(1 for _, t, _ in tiers if t == 2)
    t3 = sum(1 for _, t, _ in tiers if t == 3)
    t0 = sum(1 for _, t, _ in tiers if t == 0)

    # Run 15 had ~5 angles (typical V2 decomposition). Per-angle source counts
    # aren't recoverable from the archive. Instead, simulate at the global
    # level: if we pretend Run 15 was one big angle, would the floor leave
    # >=5 accepted sources?
    tier12_count = t1 + t2
    if tier12_count >= 3:
        accepted = t1 + t2  # tier-3 dropped
    else:
        accepted = t1 + t2 + t3
    accepted += t0  # unscored (likely tier-1/2 from academic DBs without domain match)

    passed = accepted >= 5
    detail = (
        f"refs={len(refs)} tier1={t1} tier2={t2} tier3={t3} unscored={t0}\n"
        f"  Under floor (drop t3 when t1+t2>=3): accepted={accepted}\n"
        f"  Pass criterion: accepted >= 5"
    )
    return CheckResult("PF-1 tier floor", passed, detail)


# ---------------------------------------------------------------------------
# PF-3 — injector tightening on synthetic test cases
# ---------------------------------------------------------------------------

def pf3_injector() -> CheckResult:
    """Test injector at new threshold (ratio=0.6, words=7) against:
       - false-positive case from Run 15 audit (desert kites + Venus claim)
       - legitimate match case (apkallu + Mesopotamian Seven Sages claim)
    Both cases use synthetic but Run-15-realistic prose.
    """
    registry = CitationRegistry()
    # Add legitimate apkallu source + claim
    apkallu_sid = "apkallu_test"
    registry.sources[apkallu_sid] = CitedSource(
        id=apkallu_sid,
        url="https://example.edu/apkallu",
        title="The Seven Apkallu of Mesopotamia",
        snippet="The seven apkallu sages brought civilization before the flood.",
        reliability_tier=1,
    )
    registry.claims.append(
        ClaimCitation(
            claim_text=(
                "The seven apkallu of Mesopotamian tradition were sages depicted as "
                "fish-cloaked figures who brought civilization to humanity in Sumerian "
                "and Akkadian texts before the great flood."
            ),
            source_ids=[apkallu_sid],
        )
    )

    # Add Venus-astronomy source + claim (the Run 15 false-positive case)
    venus_sid = "venus_test"
    registry.sources[venus_sid] = CitedSource(
        id=venus_sid,
        url="https://example.edu/venus",
        title="Venus tablets of Ammisaduqa: Babylonian astronomical records",
        snippet="Babylonian Venus observations recorded in cuneiform.",
        reliability_tier=1,
    )
    registry.claims.append(
        ClaimCitation(
            claim_text=(
                "Babylonian Venus tablet observations recorded planetary risings and "
                "settings over decades of astronomical study by trained scribes."
            ),
            source_ids=[venus_sid],
        )
    )

    # Test 1: legitimate apkallu paragraph should match apkallu claim
    apkallu_para = (
        "Mesopotamian tradition records the seven apkallu, fish-cloaked sages who "
        "appeared before the flood and brought writing, agriculture, and civilization "
        "to humanity according to ancient Sumerian and Akkadian sources."
    )
    out1 = inject_citation_for_paragraph(apkallu_para, registry)
    legit_match = out1 is not None and "[" in (out1 or "")

    # Test 2: desert-kite false-positive paragraph must NOT match the Venus claim
    # (the Run 15 audit found citation [23][24] attached to a desert-kite paragraph
    # because of generic "ancient" / "study" / "civilization" overlap)
    desert_para = (
        "Recent archaeological surveys in Saudi Arabia have documented hundreds of "
        "desert kites — large stone wall structures used for hunting that span "
        "kilometers across the landscape and date back nine thousand years."
    )
    # Reset injector state for second test (no shared state but rebuild for clarity)
    registry2 = CitationRegistry()
    registry2.sources[venus_sid] = registry.sources[venus_sid]
    registry2.claims.append(registry.claims[1])  # only Venus claim
    out2 = inject_citation_for_paragraph(desert_para, registry2)
    false_positive_rejected = out2 is None

    passed = legit_match and false_positive_rejected
    detail = (
        f"  Legitimate apkallu match: {'PASS' if legit_match else 'FAIL'} "
        f"(out={out1[:60] if out1 else 'None'}...)\n"
        f"  False-positive rejection (desert-kite + Venus): {'PASS' if false_positive_rejected else 'FAIL'} "
        f"(out={out2[:60] if out2 else 'None'})\n"
        f"  Pass criterion: both cases correct"
    )
    return CheckResult("PF-3 injector tightening", passed, detail)


# ---------------------------------------------------------------------------
# PF-4 — image metadata gate against Run 15 candidates
# ---------------------------------------------------------------------------

def pf4_image_gate() -> CheckResult:
    """For each Run 15 image candidate, recompute the new metadata gate.

    The Run 15 content audit (run15-content-audit.md) documented specific
    image mismatches: Enuma Elish image used for Inanna-descent paragraph,
    Mitannian seals for Sumerian Inanna paragraph, Egyptian seal for
    Mesopotamian apkallu paragraph. Pass criterion: those *documented*
    mismatches must reject, AND there must be at least one image that still
    passes per paragraph that has any named-entity overlap (we don't gut
    illustration entirely).
    """
    images = _load("run15_images.json")
    passes = 0
    fails = []
    pass_titles = []
    by_para_pass: dict[int, int] = {}
    by_para_total: dict[int, int] = {}

    for img in images:
        keyword = img.get("keyword", "") or ""
        cand = ImageCandidate(
            url=img.get("source_url", ""),
            source=img.get("source_name", "") or "",
            title=img.get("title", "") or "",
            description=img.get("description", "") or "",
            artist=img.get("artist", "") or "",
            license=img.get("license", "") or "",
            license_url=img.get("license_url", "") or "",
        )
        ok = metadata_gate_passes(cand, keyword)
        pidx = img.get("paragraph_index", -1)
        by_para_total[pidx] = by_para_total.get(pidx, 0) + 1
        if ok:
            passes += 1
            by_para_pass[pidx] = by_para_pass.get(pidx, 0) + 1
            pass_titles.append(f"para#{pidx} keyword={keyword!r} title={cand.title!r}")
        else:
            fails.append(
                f"para#{pidx} keyword={keyword!r} title={cand.title!r}"
            )

    # Documented mismatches from the audit must reject. If they don't appear
    # in fails, the gate isn't strict enough.
    audit_mismatches_keywords = {
        "Descent of Inanna cuneiform tablet",  # got Enuma Elish, wrong myth
        "Sumerian Inanna goddess",              # got Mitannian seal, wrong culture
        "Uanna/Oannes",                          # got Egyptian seal, wrong civilization
    }
    rejected_keywords = {
        f.split("keyword=")[1].split(" title=")[0].strip("'") for f in fails
    }
    documented_rejected = audit_mismatches_keywords & rejected_keywords
    documented_passed = audit_mismatches_keywords - rejected_keywords

    # Don't gut illustration: at least 30% of paragraphs that had any candidate
    # must still have at least one passing candidate.
    paras_with_candidates = len(by_para_total)
    paras_with_pass = len(by_para_pass)
    illustration_coverage = paras_with_pass / max(1, paras_with_candidates)

    documented_check = len(documented_rejected) >= 2  # at least 2 of 3 known bad cases reject
    coverage_check = illustration_coverage >= 0.30
    passed = documented_check and coverage_check

    survival_pct = (passes / max(1, len(images))) * 100
    detail = (
        f"  candidates={len(images)} pass_new_gate={passes} ({survival_pct:.0f}%)\n"
        f"  Documented mismatches rejected: {len(documented_rejected)}/3 "
        f"({sorted(documented_rejected)})\n"
        f"  Documented mismatches still passing: {sorted(documented_passed) or 'none'}\n"
        f"  Paragraphs with at least one passing image: "
        f"{paras_with_pass}/{paras_with_candidates} ({illustration_coverage:.0%})\n"
        f"  Pass criterion: >=2/3 documented mismatches reject AND >=30% paragraph coverage"
    )
    return CheckResult("PF-4 image gate", passed, detail)


# ---------------------------------------------------------------------------
# PF-2 / PF-5 — live LLM checks (require API)
# ---------------------------------------------------------------------------

def pf2_verifier_live() -> CheckResult:
    """Test the strict-only verifier on synthetic-but-realistic cases.

    Run 15's archive doesn't preserve snippets (only title+url), so we can't
    replay against real Run 15 data — the verifier would see title-only and
    correctly reject everything (which is the worst-case behavior, not the
    typical case). In production, register_source captures real snippets at
    web-fetch time and the verifier sees 500-3000 char content.

    Instead, test 4 cases with realistic snippets:
      A. Match  — snippet directly supports the sentence  → expect supported=True
      B. Mismatch — snippet about a different topic        → expect supported=False
      C. Adjacent — snippet on the same field, no specific support → expect False
      D. Vague title only (~150 chars)                     → expect False (strict)

    Pass criterion: A=True, B=False, C=False, D=False.
    """
    import asyncio
    from pipeline.lyra.citation_verifier import _verify_one_citation
    from pipeline.lyra.config import _get_settings

    settings = _get_settings()

    cases = [
        {
            "label": "A. legitimate match",
            "sentence": "Babylonian astronomers tracked Venus risings for over six centuries.",
            "title": "The Venus Tablet of Ammisaduqa: Babylonian Astronomical Records",
            "snippet": (
                "The Venus Tablet of Ammisaduqa is a clay cuneiform tablet that records "
                "Babylonian astronomical observations of Venus over a 21-year period during "
                "the reign of King Ammisaduqa (c. 1646-1626 BCE). The tablet is part of a "
                "longer series called Enuma Anu Enlil and demonstrates that Babylonian "
                "astronomers systematically tracked planetary risings and settings for "
                "centuries, with later observational records extending the practice into "
                "the first millennium BCE."
            ),
            "url": "https://example.edu/venus-tablet",
            "expect": True,
        },
        {
            "label": "B. clear topic mismatch",
            "sentence": "Desert kites in Saudi Arabia are large stone hunting structures.",
            "title": "Mesopotamian gods and Inanna's descent to the underworld",
            "snippet": (
                "Inanna, the Sumerian goddess of love and war, is depicted in mythological "
                "texts descending through seven gates of the underworld. At each gate she "
                "removes one item of clothing or regalia until she stands naked before "
                "Ereshkigal, queen of the underworld. The myth dates to the third millennium "
                "BCE and exists in multiple Sumerian and Akkadian versions."
            ),
            "url": "https://example.edu/inanna",
            "expect": False,
        },
        {
            "label": "C. adjacent topic, no specific support",
            "sentence": "Gobekli Tepe was deliberately buried by its builders around 8000 BCE.",
            "title": "Pre-pottery Neolithic architecture in southeast Anatolia",
            "snippet": (
                "The pre-pottery Neolithic period in southeast Anatolia (c. 9600-7000 BCE) "
                "produced a distinctive style of stone architecture characterized by T-shaped "
                "pillars and circular enclosures. Sites in this tradition exhibit complex "
                "iconography and evidence of communal construction. The chronology is "
                "established through radiocarbon dating of carbon samples from occupation "
                "layers."
            ),
            "url": "https://example.edu/ppna",
            "expect": False,
        },
        {
            "label": "D. title-only thin source",
            "sentence": "Sumerian apkallu sages were depicted as fish-cloaked figures.",
            "title": "Encyclopedia of ancient Near Eastern mythology",
            "snippet": "Encyclopedia of ancient Near Eastern mythology",  # = title
            "url": "https://example.com/encyclopedia",
            "expect": False,
        },
    ]

    results = []

    async def main():
        for i, c in enumerate(cases, start=1):
            try:
                supported, reason = await _verify_one_citation(
                    sentence=c["sentence"],
                    cite_num=i,
                    source_title=c["title"],
                    source_snippet=c["snippet"],
                    source_url=c["url"],
                    settings=settings,
                )
                ok = supported == c["expect"]
                results.append((c["label"], supported, c["expect"], ok, reason[:60]))
            except Exception as e:
                results.append((c["label"], None, c["expect"], False, f"ERR: {e}"))

    asyncio.run(main())

    correct = sum(1 for _, _, _, ok, _ in results if ok)
    passed = correct == len(cases)
    detail = f"  correct={correct}/{len(cases)}\n"
    for label, sup, exp, ok, reason in results:
        mark = "PASS" if ok else "FAIL"
        sup_str = "True " if sup else ("False" if sup is False else "ERR  ")
        detail += f"    [{mark}] {label}: got={sup_str} expected={exp}  {reason}\n"
    return CheckResult("PF-2 verifier (live)", passed, detail.rstrip())


def pf5_prompt_parse_live() -> CheckResult:
    """Run the new theo_source_audit prompt through one synthetic source.
    Verifies the prompt change didn't break JSON parsing."""
    import asyncio
    from pipeline.lyra.config import _get_settings, call_api

    prompt_path = (
        Path(__file__).resolve().parent.parent
        / "pipeline" / "lyra" / "prompts" / "theo_source_audit.txt"
    )
    system = prompt_path.read_text(encoding="utf-8")
    user = json.dumps(
        {
            "research_question": "Did ancient Mesopotamians observe Venus systematically?",
            "sources": [
                {
                    "id": "test001",
                    "url": "https://www.nature.com/articles/example",
                    "title": "Babylonian astronomical diaries: A reanalysis",
                    "snippet": "Cuneiform tablets dated to 700 BCE record Venus risings...",
                }
            ],
        }
    )

    async def main():
        return await asyncio.to_thread(
            call_api,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=512,
            temperature=0.0,
            timeout=30.0,
        )

    settings = _get_settings()
    try:
        resp = asyncio.run(main())
        text = (resp.text or "").strip()
        # Strip code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        ok = "scored_sources" in parsed or "rejected_sources" in parsed
        detail = f"  parse=OK keys={list(parsed.keys())}"
        return CheckResult("PF-5 prompt parse (live)", ok, detail)
    except Exception as e:
        return CheckResult("PF-5 prompt parse (live)", False, f"  ERR: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also run PF-2 + PF-5 (LLM calls)")
    args = ap.parse_args()

    print("=" * 70)
    print("Run 15 Pre-flight Measurements")
    print("=" * 70)

    checks = [pf1_tier_floor(), pf3_injector(), pf4_image_gate()]
    if args.live:
        print("\n[live mode] running PF-2 (verifier) — this calls the LLM...")
        checks.append(pf2_verifier_live())
        print("[live mode] running PF-5 (prompt parse) — this calls the LLM...")
        checks.append(pf5_prompt_parse_live())

    all_pass = True
    for c in checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"\n[{mark}] {c.name}")
        print(c.detail)
        if not c.passed:
            all_pass = False

    print("\n" + "=" * 70)
    print(f"OVERALL: {'PASS' if all_pass else 'FAIL'}")
    if not args.live:
        print("Note: PF-2 (verifier) and PF-5 (prompt) require --live to run via LLM.")
    print("=" * 70)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
