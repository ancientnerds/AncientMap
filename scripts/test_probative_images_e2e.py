"""End-to-end smoke test: run the full probative-images flow on a fixture paper.

Does NOT depend on a fresh pipeline run — uses the stored Shining Ones v2 JSON
and exercises select_opportunities -> fetch_candidates -> metadata gate -> VLM
gate -> insert on the existing paper text.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

# Load .env
for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Add repo root to sys.path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pipeline.lyra.config import _get_settings
from pipeline.lyra.illustration_specialist import select_opportunities
from pipeline.lyra.image_fetcher import (
    download_candidate,
    fetch_candidates,
)
from pipeline.lyra.image_gates import (
    build_vlm_prompt,
    metadata_gate_passes,
    parse_vlm_verdict,
    verdict_is_accept,
)
from pipeline.lyra.minimax_shared import create_minimax_client, minimax_vlm
from pipeline.lyra.theo_image_captions import (
    find_section_for_claim,
    image_markdown,
    insert_image_after_section,
)


async def main() -> None:
    fixture_path = pathlib.Path(r"C:\tmp\theo_new.json")
    if not fixture_path.exists():
        print(f"Fixture missing: {fixture_path}")
        sys.exit(1)

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    report = fixture["result"]["report"]

    claims = [
        {
            "claim": "The Nebra Sky Disc encodes Bronze Age astronomical knowledge",
            "confidence": "high",
        },
        {
            "claim": "Mesopotamian cuneiform sources document the Anunnaki as divine beings",
            "confidence": "high",
        },
        {
            "claim": "Göbekli Tepe builders carved monumental T-pillars before agriculture",
            "confidence": "high",
        },
        {
            "claim": "The Dendera Light interpretation rests on a specific crypt relief",
            "confidence": "medium",
        },
    ]

    settings = _get_settings()
    opps = await select_opportunities(claims, settings)
    print(f"\nOpportunities: {len(opps)}")
    for o in opps:
        print(f"  - claim {o['claim_index']}: {o['search_query']}")

    client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)
    out_dir = pathlib.Path(r"C:\tmp\probative_e2e")
    out_dir.mkdir(parents=True, exist_ok=True)

    paper_text = report
    embedded = 0
    for opp in opps[:6]:
        claim = claims[opp["claim_index"]]["claim"]
        section = find_section_for_claim(paper_text, claim)
        if not section:
            print(f"  skip (no section): {claim[:60]}")
            continue
        cands = await fetch_candidates(opp["search_query"])
        cands = [c for c in cands if metadata_gate_passes(c, opp["what_image_must_show"])]
        accepted = None
        for c in cands[:5]:
            probe = out_dir / f"_probe_{opp['claim_index']}.bin"
            if not await download_candidate(c, probe):
                continue
            raw = minimax_vlm(
                client,
                probe.read_bytes(),
                build_vlm_prompt(claim, opp["what_image_must_show"], opp["forbidden_elements"]),
            )
            v = parse_vlm_verdict(raw)
            probe.unlink(missing_ok=True)
            if verdict_is_accept(v):
                accepted = c
                print(f"  ✓ accepted {c.title[:50]} — {c.source}")
                break
        if not accepted:
            print(f"  ✗ no candidate survived: {claim[:60]}")
            continue
        final = out_dir / f"claim_{opp['claim_index']}.jpg"
        await download_candidate(accepted, final)
        md = image_markdown(accepted, f"/tmp/{final.name}", opp["rationale"])
        paper_text = insert_image_after_section(paper_text, section, md)
        embedded += 1

    client.close()
    out = out_dir / "report_with_images.md"
    out.write_text(paper_text, encoding="utf-8")
    print(f"\nEmbedded {embedded} images. Output written to {out}")


if __name__ == "__main__":
    asyncio.run(main())
