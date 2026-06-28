"""
Shining Ones Research Paper — Quality Assessment Framework

This is a SUPPLEMENTARY assessor. The pipeline's own JudgeHandler already computes
quality_score.passed (badge + mechanical metrics) and audit_result (citation integrity).
This script checks what the pipeline DOESN'T mechanically measure:

  1. Why Files narrative voice — investigative, documentary, no hedging
  2. AI slop detection — banned phrase patterns
  3. Image probative density — are images embedded per section, not just decorative

The pipeline's own gates (quality_score.passed, audit_result.passed) are authoritative.
This script supplements with editorial/quality-of-voice checks.

Usage:
    python scripts/assess_research_quality.py <request_id> [--api-base URL]
    python scripts/assess_research_quality.py --slug <slug>
    python scripts/assess_research_quality.py --report-json /path/to/paper.json
"""

import io
import sys
import re
import json
from dataclasses import dataclass, field
from typing import Optional

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AI_SLOP_PATTERNS = [
    (r"\bit should be noted\b", "it should be noted"),
    (r"\bit is worth considering\b", "it is worth considering"),
    (r"\bit is important to emphasize\b", "it is important to emphasize"),
    (r"\bthroughout (history|human history)\b", "throughout history"),
    (r"\bsince the dawn of time\b", "since the dawn of time"),
    (r"\bscholars have (long |often |traditionally )?debated\b", "scholars have debated"),
    (r"\bfurther research is needed\b", "further research is needed"),
    (r"\bthe answer remains elusive\b", "the answer remains elusive"),
    (r"\bonly time will tell\b", "only time will tell"),
    (r"\bthis challenges our fundamental understanding\b", "this challenges our fundamental"),
    (r"\bas we continue to explore this fascinating topic\b", "as we continue to explore"),
    (r"\bthe evidence suggests this could potentially indicate\b", "the evidence suggests...could potentially"),
    (r"\bthe investigation (has |will |does )?reveal\b", "the investigation reveals"),
    (r"\bthe evidence (has |will |does )?show\b", "the evidence shows"),
    (r"\bthe analysis (has |will |does )?reveal\b", "the analysis reveals"),
    (r"\bit is (also )?worth noting\b", "it is worth noting"),
    (r"\bdelve[sd]? into\b", "delve into"),
    (r"\bintricately\b", "intricately"),
    (r"\bserves as a (crucial |vital )?(piece|component|evidence)\b", "serves as a crucial piece"),
    (r"\bpivotal role\b", "pivotal role"),
    (r"\bmultifaceted\b", "multifaceted"),
    (r"\bunparalleled\b", "unparalleled"),
    (r"\bunderscores the (importance|significance)\b", "underscores the importance"),
    (r"\bcross-section of\b", "cross-section of"),
    (r"\bfusion of\b", "fusion of"),
    (r"\bsynergy\b", "synergy"),
    (r"\bspeaks to\b", "speaks to"),
    (r"\bholistic\b", "holistic"),
    (r"\blaunchpad\b", "launchpad"),
    (r"\bignite[d]?\b", "ignite"),
    (r"\bunlock(ing)?\b", "unlock"),
    (r"\bre\u5199\u4e0b\b", "Chinese character bleed"),
    (r"\b\u30b3\u30f3\u30c6\u30f3\u30c8\u30b9\u30bf\u30a4\u30eb\b", "Japanese content bleed"),
]

WHY_FILES_OPENERS_BAD = [
    "throughout history",
    "since the dawn of time",
    "scholars have debated",
    "since ancient times",
    "humans have always",
    "from the beginning",
]

WHY_FILES_POSITIVE = [
    "but here's where it gets interesting",
    "but here's the part that doesn't sit right",
    "the timeline fits",
    "if you're building a case",
    "the scans show",
    "the documents show",
    "something is going on",
    "that could be coincidence",
    "they have a point",
    "and they have a point",
    "i don't know",
    "we don't know",
    "nobody knows",
    "the evidence doesn't",
    "flat out",
    "that's not how",
]

HEDGING_PATTERNS = [
    r"\bmight be\b",
    r"\bmay be\b",
    r"\bcould be\b",
    r"\bsuggests that\b",
    r"\bappears to\b",
    r"\bseems to\b",
    r"\bpotentially\b",
    r"\bperhaps\b",
    r"\bit is possible that\b",
]

PASSIVE_VOICE = r"\b(was|were|is|are|been|being)\s+\w+ed\b"

HEADER = "\n" + "=" * 60
BANGS = "\n" + "=" * 60


# ---------------------------------------------------------------------------
# Gate 1: Pipeline's Own Quality Score (authoritative)
# ---------------------------------------------------------------------------

def assess_pipeline_quality(data: dict) -> dict:
    """Check the pipeline's own quality_score from JudgeHandler."""
    result = data.get("result", {})
    qs = result.get("quality_score") or {}
    audit = result.get("audit") or {}

    score = qs.get("score", 0)
    badge = qs.get("badge", "Unverified")
    passed = qs.get("passed", False)
    meta = qs.get("meta", {})
    metrics = qs.get("metrics", {})

    audit_passed = audit.get("passed", False)
    issues = audit.get("issues", [])

    # Judge's own pass gate requires: passed AND citation_coverage >= 9 AND
    # reference_integrity == 10 AND zero placeholder_markers AND zero language_bleed
    citation_cov = metrics.get("citation_coverage", 0)
    ref_integrity = metrics.get("reference_integrity", 0)
    uncited = meta.get("uncited_paragraphs", 0)
    placeholders = meta.get("placeholder_markers", 0)
    lang_bleed = meta.get("language_bleed", 0)
    word_count = meta.get("word_count", 0)
    total_sources = meta.get("total_sources", 0)
    angles = meta.get("angles", 0)
    angles_sat = meta.get("angles_saturated", 0)
    debate_rounds = meta.get("debate_rounds", 0)
    total_claims = meta.get("total_claims", 0)

    fixes = []
    if not passed:
        if citation_cov < 9:
            fixes.append(f"Citation coverage too low: {citation_cov}/15 ({uncited} uncited paragraphs)")
        if ref_integrity < 10:
            fixes.append(f"Reference integrity failed: {ref_integrity}/10")
        if placeholders > 0:
            fixes.append(f"Placeholder markers leaked into prose: {placeholders}")
        if lang_bleed > 0:
            fixes.append(f"Non-Latin script bleed: {lang_bleed}")

    gate_passed = passed

    return {
        "name": "Pipeline Quality Score",
        "description": "JudgeHandler quality_score.passed gate — authoritative pipeline check",
        "gate_passed": gate_passed,
        "score": score,
        "badge": badge,
        "details": {
            "score": score,
            "badge": badge,
            "citation_coverage": citation_cov,
            "reference_integrity": ref_integrity,
            "uncited_paragraphs": uncited,
            "placeholder_markers": placeholders,
            "language_bleed": lang_bleed,
            "word_count": word_count,
            "total_sources": total_sources,
            "total_claims": total_claims,
            "angles": angles,
            "angles_saturated": angles_sat,
            "debate_rounds": debate_rounds,
            "audit_passed": audit_passed,
            "audit_issues": issues[:10],
        },
        "fixes": fixes,
        "weight": 1.0,  # This is the authoritative gate — always weight 1.0
    }


# ---------------------------------------------------------------------------
# Gate 2: Citation Integrity (from audit_result — supplementary check)
# ---------------------------------------------------------------------------

def assess_citation_integrity(data: dict) -> dict:
    """Supplementary citation check — validates [N] markers resolve to references."""
    result = data.get("result", {})
    report = result.get("report", "")
    audit = result.get("audit", {})

    passed = audit.get("passed", True)
    total_citations = audit.get("total_citations", 0)
    orphaned_refs = audit.get("orphaned_refs", [])
    invalid_markers = audit.get("invalid_markers", [])
    uncited_paragraphs = audit.get("uncited_paragraphs", 0)

    # Parse reference section
    ref_match = re.search(r"^##\s+References\s*$", report, re.MULTILINE)
    ref_entries = []
    if ref_match:
        ref_text = report[ref_match.end():]
        next_h2 = re.search(r"^##\s+", ref_text)
        if next_h2:
            ref_text = ref_text[:next_h2.start()]
        ref_entries = re.findall(r"^\[(\d+)\]", ref_text, re.MULTILINE)

    fixes = []
    if orphaned_refs:
        fixes.append(f"Orphaned references (cited but no [N]): {orphaned_refs[:5]}")
    if invalid_markers:
        fixes.append(f"Invalid [N] markers (no matching ref): {invalid_markers[:5]}")
    if uncited_paragraphs > 5:
        fixes.append(f"Uncited paragraphs: {uncited_paragraphs} (many paragraphs missing citation)")

    gate_passed = passed and not orphaned_refs and not invalid_markers and uncited_paragraphs <= 3

    return {
        "name": "Citation Integrity",
        "description": "All [N] markers resolve, all references cited, no orphans",
        "gate_passed": gate_passed,
        "score": 1.0 if gate_passed else 0.3,
        "details": {
            "total_citations": total_citations,
            "orphaned_refs": orphaned_refs,
            "invalid_markers": invalid_markers,
            "uncited_paragraphs": uncited_paragraphs,
            "reference_entries": len(ref_entries),
        },
        "fixes": fixes,
        "weight": 0.3,
    }


# ---------------------------------------------------------------------------
# Gate 3: Source Tier Mix
# ---------------------------------------------------------------------------

def assess_source_tiers(data: dict) -> dict:
    """Check for meaningful source diversity — Academic + Reputable + primary."""
    result = data.get("result", {})
    report = result.get("report", "")

    ref_match = re.search(r"^##\s+References\s*$", report, re.MULTILINE)
    if not ref_match:
        return _fail_gate("Source Tier Mix", "No References section found")

    ref_text = report[ref_match.end():]
    next_h2 = re.search(r"^##\s+", ref_text)
    if next_h2:
        ref_text = ref_text[:next_h2.start()]

    academic_kw = ["journal", "arxiv", "semantic scholar", "crossref", "openalex", "jstor",
                   "researchgate", "doi.org", ".edu/", "proceedings", "conference"]
    reputable_kw = ["wikipedia", "encyclopedia", "britannica", "smithsonian", "national geographic",
                     "europeana", "getty", "library of congress", "british museum", "louvre"]
    primary_kw = ["metmuseum", "wikimedia", "commons", "loc.gov", "digging", "excavation",
                  "field report", "museum of"]

    academic_count = reputable_count = primary_count = total = 0
    for line in ref_text.split("\n"):
        if not re.match(r"^\[\d+\]", line.strip()):
            continue
        total += 1
        lower = line.lower()
        if any(kw in lower for kw in academic_kw):
            academic_count += 1
        elif any(kw in lower for kw in reputable_kw):
            reputable_count += 1
        elif any(kw in lower for kw in primary_kw):
            primary_count += 1

    fixes = []
    if academic_count < 2:
        fixes.append(f"No academic tier sources: need journals/arxiv/doi (found {academic_count})")
    if total < 10:
        fixes.append(f"Very few references: {total} (need 10+ for credible coverage)")
    if academic_count == 0 and total > 0:
        fixes.append("No academic sources — only web scrapes and encyclopedic sources")

    score = 1.0
    if academic_count == 0: score *= 0.2
    elif academic_count < 2: score *= 0.6
    elif total < 10: score *= 0.7

    gate_passed = score >= 0.7 and academic_count >= 2

    return {
        "name": "Source Tier Mix",
        "description": "Academic + Reputable + Primary sources, not just Wikipedia",
        "gate_passed": gate_passed,
        "score": score,
        "details": {
            "academic": academic_count,
            "reputable": reputable_count,
            "primary": primary_count,
            "total": total,
        },
        "fixes": fixes,
        "weight": 0.2,
    }


# ---------------------------------------------------------------------------
# Gate 4: Why Files Voice
# ---------------------------------------------------------------------------

def assess_why_files_voice(data: dict) -> dict:
    """Check for Why Files documentary narrative voice — not academic essay."""
    result = data.get("result", {})
    report = result.get("report", "")

    paragraphs = [p.strip() for p in report.split("\n\n")
                  if p.strip() and len(p) > 80 and not p.startswith("#")]

    why_elements = sum(1 for p in paragraphs if any(e in p.lower() for e in WHY_FILES_POSITIVE))
    hedging_count = sum(1 for p in paragraphs
                        if any(re.search(h, p, re.I) for h in HEDGING_PATTERNS))

    # Bad opener check
    first_para = paragraphs[0] if paragraphs else ""
    first_lower = first_para.lower()[:200]
    bad_opener = any(b in first_lower for b in WHY_FILES_OPENERS_BAD)

    passive_count = len(re.findall(PASSIVE_VOICE, report))
    passive_ratio = passive_count / max(len(paragraphs), 1)

    why_ratio = why_elements / max(len(paragraphs), 1)
    hedging_ratio = hedging_count / max(len(paragraphs), 1)

    fixes = []
    if why_ratio < 0.05:
        fixes.append(f"Almost no Why Files voice: {why_ratio:.0%} of paragraphs (need 5%+)")
    if hedging_ratio > 0.35:
        fixes.append(f"Too much hedging: {hedging_ratio:.0%} of paragraphs (need <25%)")
    if passive_ratio > 0.2:
        fixes.append(f"High passive voice: {passive_ratio:.0%} (need <15%)")
    if bad_opener:
        fixes.append("Hook opens with generic opener instead of specific date/person/place")

    score = 1.0
    if why_ratio < 0.03: score *= 0.2
    elif why_ratio < 0.05: score *= 0.5
    if hedging_ratio > 0.4: score *= 0.5
    elif hedging_ratio > 0.35: score *= 0.7
    if passive_ratio > 0.2: score *= 0.7
    if bad_opener: score *= 0.7

    gate_passed = score >= 0.65

    return {
        "name": "Why Files Voice",
        "description": "Investigative documentary narrative — specific, direct, no hedging",
        "gate_passed": gate_passed,
        "score": score,
        "details": {
            "total_paragraphs": len(paragraphs),
            "why_files_paragraphs": why_elements,
            "why_files_ratio": round(why_ratio, 3),
            "hedging_paragraphs": hedging_count,
            "hedging_ratio": round(hedging_ratio, 3),
            "passive_ratio": round(passive_ratio, 3),
            "bad_opener": bad_opener,
        },
        "fixes": fixes,
        "weight": 0.15,
    }


# ---------------------------------------------------------------------------
# Gate 5: AI Slop Detection
# ---------------------------------------------------------------------------

def assess_ai_slop(data: dict) -> dict:
    """Detect banned AI slop phrases."""
    result = data.get("result", {})
    report = result.get("report", "")

    slop_hits = []
    for pattern, label in AI_SLOP_PATTERNS:
        for m in re.finditer(pattern, report, re.IGNORECASE):
            ctx = report[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
            slop_hits.append((label, ctx[:100]))

    # Language bleed check (non-Latin scripts in Latin text)
    non_latin = re.findall(r"[\u0400-\u04FF\u30FF\u4E00-\u9FFF\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]", report)

    fixes = []
    if slop_hits:
        fixes.append(f"AI slop phrases: {len(slop_hits)} hits")
        seen = set()
        for label, _ in slop_hits[:5]:
            if label not in seen:
                fixes.append(f"  Banned: {label}")
                seen.add(label)

    if non_latin:
        fixes.append(f"Non-Latin script bleed: {len(non_latin)} chars")
        fixes.append(f"  Sample: {''.join(non_latin[:20])}")

    score = max(0, 1.0 - len(slop_hits) * 0.04 - len(non_latin) * 0.02)
    gate_passed = score >= 0.75 and not non_latin

    return {
        "name": "AI Slop Detection",
        "description": "No banned AI slop phrases, no non-Latin script bleed",
        "gate_passed": gate_passed,
        "score": score,
        "details": {
            "slop_hits": len(slop_hits),
            "language_bleed_chars": len(non_latin),
            "sample_slop": [f"{l}: {c[:80]}" for l, c in slop_hits[:3]],
        },
        "fixes": fixes,
        "weight": 0.15,
    }


# ---------------------------------------------------------------------------
# Gate 6: Image Probative Density (supplementary)
# ---------------------------------------------------------------------------

def assess_image_density(data: dict, probative_images: list = None) -> dict:
    """Check for meaningful image density — probative images per section, not decorative."""
    result = data.get("result", {})
    report = result.get("report", "")

    # Count markdown images in body (not references)
    refs_idx = report.find("## References")
    body = report[:refs_idx] if refs_idx > 0 else report
    images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", body)
    image_count = len(images)

    # Sections with images
    h2_sections = re.findall(r"^##\s+(.+)$", report, re.MULTILINE)
    target_sections = [h for h in h2_sections
                       if h.lower() not in ("references", "sources")]
    sections_with_images = 0
    for h2 in target_sections:
        h2_idx = report.find(f"## {h2}")
        next_h2_idx = report.find("\n## ", h2_idx + 1)
        section_text = report[h2_idx:next_h2_idx if next_h2_idx > 0 else len(report)]
        if re.search(r"!\[[^\]]+\]\([^\)]+\)", section_text):
            sections_with_images += 1

    # Gallery markers from new pipeline
    gallery_count = len(re.findall(r"gallery:", body))

    # From probative_images metadata if available
    embedded_count = len(probative_images) if probative_images else 0
    sources = set()
    for img in (probative_images or []):
        if img.get("source_name"):
            sources.add(img["source_name"])

    fixes = []
    if image_count == 0:
        fixes.append("No images in body — probative image pipeline may have failed")
    elif image_count < 5:
        fixes.append(f"Low image density: {image_count} images (target 10+ for high-density video)")
    if gallery_count == 0 and image_count > 0:
        fixes.append("No gallery: markers — frontend carousel grouping not active")
    if sections_with_images < len(target_sections) * 0.3:
        fixes.append(f"Few sections have images: {sections_with_images}/{len(target_sections)}")

    score = 1.0
    if image_count == 0: score *= 0.0
    elif image_count < 5: score *= 0.4
    elif image_count < 10: score *= 0.7
    if gallery_count == 0 and image_count > 0: score *= 0.8

    gate_passed = score >= 0.65 and image_count >= 5

    return {
        "name": "Image Probative Density",
        "description": "Multiple probative images per section — gallery carousel for video",
        "gate_passed": gate_passed,
        "score": score,
        "details": {
            "total_images": image_count,
            "gallery_markers": gallery_count,
            "sections_with_images": sections_with_images,
            "total_sections": len(target_sections),
            "embedded_count": embedded_count,
            "unique_sources": len(sources),
        },
        "fixes": fixes,
        "weight": 0.15,
    }


# ---------------------------------------------------------------------------
# Master assessor
# ---------------------------------------------------------------------------

def assess_paper(data: dict, probative_images: list = None) -> dict:
    """Run all gates. Gate 1 (pipeline quality) is authoritative; others are supplementary."""

    g1 = assess_pipeline_quality(data)
    g2 = assess_citation_integrity(data)
    g3 = assess_source_tiers(data)
    g4 = assess_why_files_voice(data)
    g5 = assess_ai_slop(data)
    g6 = assess_image_density(data, probative_images)

    gates = [g1, g2, g3, g4, g5, g6]

    # Pipeline's own passed gate is authoritative
    pipeline_passed = g1["gate_passed"]
    # Supplementary gates are guidance
    supplementary_passed = all(g["gate_passed"] for g in gates[1:])

    all_fixes = []
    for g in gates:
        all_fixes.extend(g["fixes"])

    return {
        "pipeline_passed": pipeline_passed,
        "supplementary_passed": supplementary_passed,
        "overall_passed": pipeline_passed and supplementary_passed,
        "quality_score": g1["score"],
        "badge": g1["badge"],
        "gates": gates,
        "all_fixes": all_fixes,
    }


def print_scorecard(result: dict):
    print(HEADER)
    print("  SHINING ONES RESEARCH — QUALITY SCORECARD")
    print(HEADER)

    pipe_status = "PASS" if result["pipeline_passed"] else "FAIL"
    print(f"\n  Pipeline Judge:  {pipe_status}  |  Badge: {result['badge']}  |  Score: {result['quality_score']}")
    print(f"  Supplementary:  {'PASS' if result['supplementary_passed'] else 'FAIL'}")

    print(f"\n  Gates:")
    for g in result["gates"]:
        status = "PASS" if g["gate_passed"] else "FAIL"
        bar = "█" * int(g["score"] * 10) + "░" * (10 - int(g["score"] * 10))
        print(f"\n  [{status}] {g['name']} ({g['score']:.0%}) {bar}")
        d = g["details"]
        for k, v in d.items():
            print(f"         {k}: {v}")
        if g["fixes"]:
            print(f"         ISSUES:")
            for f in g["fixes"]:
                print(f"           ✗ {f}")

    if result["all_fixes"]:
        print(BANGS)
        print(f"  ALL ISSUES ({len(result['all_fixes'])}):")
        for i, f in enumerate(result["all_fixes"], 1):
            print(f"  {i}. {f}")
        print(BANGS)

    return result["overall_passed"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import httpx
    import os

    parser = argparse.ArgumentParser(
        description="Supplementary quality assessment for research papers"
    )
    parser.add_argument("request_id", nargs="?", help="API request ID")
    parser.add_argument("--slug", help="Paper slug (from public URL)")
    parser.add_argument("--report-json", help="Path to paper JSON file")
    parser.add_argument(
        "--api-base",
        default=os.getenv("TEST_API_BASE", "https://ancientnerds.com/api/"),
    )
    parser.add_argument(
        "--auth-token",
        default=os.getenv(
            "AUTH_TOKEN",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0NDIwMDAxMTI3NTYwNjQyNjAiLCJ1c2VyX2lkIjoiMjZlMDYzMWItNjY0Yy00NTg4LTk0M2EtMDk1NjE2YWFjODhiIiwiZXhwIjoxNzc2ODA1NjgyLCJpYXQiOjE3NzYyMDA4ODJ9.DxQqBrI0rAJE1wD0WgkIuyb6Ipgc8UlrsjhLJoA_Zso",
        ),
    )
    args = parser.parse_args()

    # Load paper data
    if args.report_json:
        with open(args.report_json, encoding="utf-8") as f:
            data = json.load(f)

    elif args.request_id:
        resp = httpx.get(
            f"{args.api_base}theo/research/{args.request_id}",
            headers={"Authorization": f"Bearer {args.auth_token}"},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"ERROR {resp.status_code}: {resp.text}")
            sys.exit(1)
        data = resp.json()

    else:
        parser.print_help()
        sys.exit(1)

    # Check status
    status = data.get("status", "unknown")
    if status != "completed":
        print(f"Paper status: {status} — cannot assess until completed")
        print(f"  sites_found: {data.get('sites_found')}")
        print(f"  error_message: {data.get('error_message')}")
        sys.exit(0)

    result = data.get("result", {})
    if not result or not result.get("report"):
        print("No paper content yet")
        sys.exit(0)

    probative_images = data.get("probative_images", [])

    scorecard = assess_paper(data, probative_images)
    print_scorecard(scorecard)

    print(f"\n  Pipeline PASSED: {scorecard['pipeline_passed']}")
    print(f"  Supplementary: {'ALL PASS' if scorecard['supplementary_passed'] else 'SOME FAIL'}")
    print(f"  FINAL: {'PASS' if scorecard['overall_passed'] else 'NEEDS WORK'}")

    sys.exit(0 if scorecard["overall_passed"] else 1)
