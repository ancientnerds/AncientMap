"""End-to-end smoke for the new Image Research stage.

Exercises the full flow against a synthetic angles list:
  1. generate_queries_for_angle() per angle (MiniMax M2.7 specialist)
  2. fetch_candidates() fan-out across connectors for each query
  3. pool population (deduped, capped)
  4. illustration-specialist opportunities against synthetic claims
  5. pool-based + fallback candidate gathering
  6. metadata gate + VLM gate + download + insert
  7. diversity scoring on the final embedded set

Runs against live APIs (MiniMax, connectors). Prints a structured report.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
from dataclasses import asdict

for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pipeline.lyra.angle_image_queries import generate_queries_for_angle  # noqa: E402
from pipeline.lyra.config import _get_settings  # noqa: E402
from pipeline.lyra.illustration_specialist import select_opportunities  # noqa: E402
from pipeline.lyra.image_diversity import compute_diversity  # noqa: E402
from pipeline.lyra.image_fetcher import (  # noqa: E402
    ImageCandidate,
    download_candidate,
    fetch_candidates,
)
from pipeline.lyra.image_gates import (  # noqa: E402
    build_vlm_prompt,
    metadata_gate_passes,
    parse_vlm_verdict,
    verdict_is_accept,
)
from pipeline.lyra.minimax_shared import create_minimax_client, minimax_vlm  # noqa: E402
from pipeline.lyra.theo_image_captions import (  # noqa: E402
    find_section_for_claim,
    image_markdown,
    insert_image_after_section,
)

# Synthetic angles mirroring what the Shining Ones v2 paper would produce
SYNTHETIC_ANGLES = [
    {
        "id": "angle_1",
        "topic": "Sky Beings in Ancient Texts",
        "description": "Primary-source evidence from Egyptian and Mesopotamian scripture — Pyramid Texts, Book of the Dead, Enuma Elish.",
    },
    {
        "id": "angle_2",
        "topic": "Megalithic Construction Precision",
        "description": "Göbekli Tepe T-pillars, Puma Punku H-blocks, and the engineering questions around pre-industrial stonework.",
    },
    {
        "id": "angle_3",
        "topic": "Bronze Age Astronomical Knowledge",
        "description": "The Nebra Sky Disc, Dresden Codex Venus tables, and documented ancient astronomical sophistication.",
    },
]

SYNTHETIC_CLAIMS = [
    {
        "claim": "The Pyramid Texts at Saqqara describe divine beings as luminous entities",
        "confidence": "high",
        "source_ids": [],  # no real registry in this smoke test
    },
    {
        "claim": "Göbekli Tepe builders carved T-shaped pillars with animal reliefs before agriculture",
        "confidence": "high",
        "source_ids": [],
    },
    {
        "claim": "The Nebra Sky Disc encodes Bronze Age astronomical knowledge",
        "confidence": "high",
        "source_ids": [],
    },
]


async def main() -> None:
    settings = _get_settings()
    out_dir = pathlib.Path(r"C:\tmp\image_research_e2e")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== STAGE 1: per-angle query generation ===\n")
    queries_per_angle: dict[str, list[str]] = {}
    for angle in SYNTHETIC_ANGLES:
        q = await generate_queries_for_angle(angle["topic"], angle["description"], settings)
        queries_per_angle[angle["id"]] = q
        print(f"  [{angle['id']}] '{angle['topic']}'")
        for query in q:
            print(f"      • {query}")

    print("\n=== STAGE 2: candidate fetch per angle ===\n")
    pool: dict[str, list[dict]] = {}
    for angle_id, queries in queries_per_angle.items():
        if not queries:
            pool[angle_id] = []
            print(f"  [{angle_id}] NO QUERIES — pool empty")
            continue
        results = await asyncio.gather(
            *[fetch_candidates(q, limit_per_source=5) for q in queries],
            return_exceptions=True,
        )
        seen: set[str] = set()
        cands: list[dict] = []
        for batch in results:
            if isinstance(batch, Exception):
                continue
            for c in batch or []:
                if c.url in seen:
                    continue
                seen.add(c.url)
                cands.append(asdict(c))
                if len(cands) >= 30:
                    break
            if len(cands) >= 30:
                break
        pool[angle_id] = cands
        sources_seen = {c.get("source") for c in cands}
        print(f"  [{angle_id}] {len(cands)} candidates from sources: {sorted(sources_seen)}")

    print("\n=== STAGE 3: illustration specialist ===\n")
    opps = await select_opportunities(SYNTHETIC_CLAIMS, settings)
    print(f"  Opportunities: {len(opps)}")
    for o in opps:
        print(
            f"    claim {o['claim_index']}: query='{o['search_query']}'  must_show='{o['what_image_must_show'][:60]}...'"
        )

    print("\n=== STAGE 4: pool-based selection + gates ===\n")
    client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)

    # Fake paper with claims literally in their would-be sections
    paper_text = (
        "# Synthetic Smoke Test Paper\n\n"
        "## Sky Beings\n\n"
        f"{SYNTHETIC_CLAIMS[0]['claim']}.\n\n"
        "## Stonework\n\n"
        f"{SYNTHETIC_CLAIMS[1]['claim']}.\n\n"
        "## Astronomy\n\n"
        f"{SYNTHETIC_CLAIMS[2]['claim']}."
    )

    embedded: list[dict] = []
    for opp in opps[:3]:
        if opp["claim_index"] >= len(SYNTHETIC_CLAIMS):
            continue
        claim = SYNTHETIC_CLAIMS[opp["claim_index"]]["claim"]
        section = find_section_for_claim(paper_text, claim)
        if not section:
            print(f"  skip (no section): {claim[:60]}")
            continue

        # Pull from the pool across all angles (since source_ids are empty in this smoke)
        cands: list[ImageCandidate] = []
        seen_urls: set[str] = set()
        for angle_id in pool:
            for d in pool.get(angle_id, []):
                if d.get("url") in seen_urls:
                    continue
                seen_urls.add(d.get("url") or "")
                cands.append(ImageCandidate.from_dict(d))

        cands = [c for c in cands if metadata_gate_passes(c, opp["what_image_must_show"])]
        print(f"  [{claim[:50]}] {len(cands)} candidates after metadata gate")

        accepted = None
        for c in cands[:5]:
            probe = out_dir / f"_probe_{opp['claim_index']}.bin"
            if not await download_candidate(c, probe):
                continue
            raw = minimax_vlm(
                client,
                probe.read_bytes(),
                build_vlm_prompt(
                    claim, opp["what_image_must_show"], opp.get("forbidden_elements", [])
                ),
            )
            v = parse_vlm_verdict(raw)
            probe.unlink(missing_ok=True)
            if verdict_is_accept(v):
                accepted = c
                print(f"    ✓ accepted: {c.title[:60]} ({c.source})")
                break

        if not accepted:
            print("    ✗ no candidate survived VLM")
            continue

        final = out_dir / f"claim_{opp['claim_index']}.jpg"
        await download_candidate(accepted, final)
        md = image_markdown(
            accepted, f"/data/research-images/_smoke/{final.name}", opp["rationale"]
        )
        paper_text = insert_image_after_section(paper_text, section, md)
        embedded.append(
            {
                "claim_index": opp["claim_index"],
                "claim_text": claim,
                "source": accepted.source,
                "license": accepted.license,
                "title": accepted.title,
                "rationale": opp["rationale"],
            }
        )

    client.close()

    print("\n=== STAGE 5: diversity scoring ===\n")
    diversity = compute_diversity(embedded)
    print(f"  total_embedded: {diversity['total_embedded']}")
    print(f"  source_count: {diversity['source_count']}")
    print(f"  license_count: {diversity['license_count']}")
    print(f"  source_diversity: {diversity['source_diversity']}")
    print(f"  license_diversity: {diversity['license_diversity']}")
    print(f"  sources: {diversity['sources']}")

    out = out_dir / "report_with_images.md"
    out.write_text(paper_text, encoding="utf-8")

    summary = {
        "pool_sizes": {a: len(pool.get(a, [])) for a in pool},
        "opportunities": len(opps),
        "embedded": len(embedded),
        "diversity": diversity,
        "output_markdown": str(out),
    }
    json_out = out_dir / "summary.json"
    json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSummary written to {json_out}")
    print(f"Paper written to {out}")


if __name__ == "__main__":
    asyncio.run(main())
