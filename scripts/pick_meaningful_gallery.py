"""Per-paragraph gallery picker.

For each paragraph in the paper, generate concrete image-search queries with
the LLM, fan out across Met + Commons, strict-VLM-gate each candidate, and
keep up to N meaningful images per paragraph.

Output:
  C:/tmp/meaningful/gallery.json  — machine-readable per-paragraph picks
  C:/tmp/meaningful/gallery.md    — human review doc with the picked images

Run:
    python scripts/pick_meaningful_gallery.py
    python scripts/pick_meaningful_gallery.py --limit 2  # first 2 paragraphs only
    python scripts/pick_meaningful_gallery.py --target 4 # want 4 images per paragraph
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys
from collections import OrderedDict

import httpx

for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Windows cp1252 console can't encode non-ASCII (ū, ē, ñ, etc). Swap stdout for
# a utf-8 writer so our debug prints don't crash the whole run mid-paragraph.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from pipeline.lyra.meaningful_images import (  # noqa: E402
    SourceMetadata,
    build_deterministic_caption,
    build_strict_vlm_prompt,
    download_bytes,
    fetch_met_metadata,
    fetch_wikimedia_metadata,
    source_page_url,
)

OUT_DIR = pathlib.Path(r"C:/tmp/meaningful")
UA = "AncientNerds-Gallery-Picker/1.0 (contact@ancientnerds.com)"

QUERY_PROMPT = """You are an image-search query generator for an illustrated
research paper. Given a paragraph from the paper, output 5-7 SHORT, CONCRETE
image-search queries that would find primary-source artifacts, sites, maps,
or historical figures that LITERALLY illustrate the paragraph's subject.

STRICT RULES:
- Each query: 2-5 words. Prefer the specific object/site/person name alone.
- Prefer named artifacts, archaeological sites, manuscripts, specific deities,
  specific rulers, specific places. Avoid generic topic words.
- If the paragraph mentions a specific culture (Sumerian, Vedic, Olmec), bias
  queries toward that culture's museum/archive holdings.
- Mix: 3-5 named-artifact queries + 1-2 broader-but-still-concrete queries
  for variety.
- Output ONLY JSON: {"queries": ["query one", "query two", ...]}. No prose.

Examples of good queries for an Anunnaki paragraph:
  ["Sumerian cuneiform tablet", "Enki god relief", "Anunnaki", "Marduk statue",
   "Gilgamesh tablet British Museum", "ziggurat Ur"]
"""


# ---------------------------------------------------------------------------
# Query generation via MiniMax.
# ---------------------------------------------------------------------------


def _parse_queries(raw: str) -> list[str]:
    if not raw:
        return []
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(cleaned)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    qs = data.get("queries") or []
    seen: set[str] = set()
    out: list[str] = []
    for q in qs:
        if not isinstance(q, str):
            continue
        q = q.strip()
        if not q or len(q) > 80:
            continue
        lo = q.lower()
        if lo in seen:
            continue
        seen.add(lo)
        out.append(q)
        if len(out) >= 7:
            break
    return out


def generate_queries(paragraph: str, section: str, settings) -> list[str]:
    """Synchronous wrapper — MiniMax SDK is sync-friendly and this is small."""
    from pipeline.lyra.minimax_shared import minimax_chat_anthropic

    user = f"## Section\n{section}\n\n## Paragraph\n{paragraph}\n"
    try:
        raw = minimax_chat_anthropic(QUERY_PROMPT, user, 512, settings, temperature=0.2)
    except Exception as e:
        print(f"    ! query LLM failed: {e!r}")
        return []
    return _parse_queries(raw)


# ---------------------------------------------------------------------------
# Search sources.
# ---------------------------------------------------------------------------


async def met_search(client: httpx.AsyncClient, query: str, limit: int = 6) -> list[int]:
    try:
        r = await client.get(
            "https://collectionapi.metmuseum.org/public/collection/v1/search",
            params={"q": query, "hasImages": "true", "isPublicDomain": "true"},
            timeout=20.0,
            headers={"User-Agent": UA},
        )
        r.raise_for_status()
        ids = r.json().get("objectIDs") or []
    except Exception as e:
        print(f"    ! met search {query!r} failed: {e!r}")
        return []
    return list(ids)[:limit]


async def met_meta(client: httpx.AsyncClient, object_id: int) -> SourceMetadata:
    url = f"https://www.metmuseum.org/art/collection/search/{object_id}"
    return await fetch_met_metadata(client, url)


async def commons_search(client: httpx.AsyncClient, query: str, limit: int = 6) -> list[str]:
    try:
        r = await client.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": "6",
                "srlimit": str(limit),
                "format": "json",
            },
            timeout=20.0,
            headers={"User-Agent": UA},
        )
        r.raise_for_status()
        hits = r.json().get("query", {}).get("search", []) or []
    except Exception as e:
        print(f"    ! commons search {query!r} failed: {e!r}")
        return []
    return [h["title"] for h in hits if h.get("title", "").startswith("File:")][:limit]


async def commons_meta(client: httpx.AsyncClient, file_title: str) -> SourceMetadata:
    url = f"https://commons.wikimedia.org/wiki/{file_title.replace(' ', '_')}"
    return await fetch_wikimedia_metadata(client, url)


# ---------------------------------------------------------------------------
# Per-paragraph picker.
# ---------------------------------------------------------------------------


async def pick_for_paragraph(
    http: httpx.AsyncClient,
    vlm_client,
    settings,
    section: str,
    paragraph: str,
    entities: list[str],
    target: int,
    max_gates: int,
) -> dict:
    """Pick up to `target` meaningful images for one paragraph."""
    from pipeline.lyra.image_gates import parse_vlm_verdict
    from pipeline.lyra.minimax_shared import minimax_vlm

    queries = generate_queries(paragraph, section, settings)
    # Seed in the VLM-extracted entities as fallback queries if LLM was stingy.
    for e in entities:
        if e and e not in queries and len(queries) < 7:
            queries.append(re.sub(r"\s*\([^)]+\)", "", e).strip())
    print(f"  queries ({len(queries)}): {queries}")

    candidates: list[tuple[str, SourceMetadata, str]] = []  # (kind, meta, query)
    seen_urls: set[str] = set()
    for q in queries:
        ids = await met_search(http, q, limit=4)
        for oid in ids:
            meta = await met_meta(http, oid)
            if not meta.ok or not meta.primary_image_url:
                continue
            if meta.primary_image_url in seen_urls:
                continue
            seen_urls.add(meta.primary_image_url)
            candidates.append(("met", meta, q))
        titles = await commons_search(http, q, limit=4)
        for ft in titles:
            meta = await commons_meta(http, ft)
            if not meta.ok or not meta.primary_image_url:
                continue
            if meta.primary_image_url in seen_urls:
                continue
            seen_urls.add(meta.primary_image_url)
            candidates.append(("commons", meta, q))
        if len(candidates) >= max_gates:
            break

    print(f"  {len(candidates)} candidates; gating up to {max_gates}")
    picks: list[dict] = []
    for src_kind, meta, query in candidates[:max_gates]:
        if len(picks) >= target:
            break
        img_bytes = await download_bytes(http, meta.primary_image_url)
        if not img_bytes:
            continue
        verdict = None
        for attempt in range(2):
            try:
                raw = minimax_vlm(
                    vlm_client,
                    img_bytes,
                    build_strict_vlm_prompt(paragraph, "gallery candidate"),
                )
                verdict = parse_vlm_verdict(raw)
                if verdict:
                    break
            except Exception as e:
                print(f"    ! vlm attempt {attempt + 1} failed: {e!r}")
                verdict = None
            await asyncio.sleep(1.0)

        label = (verdict or {}).get("verdict")
        title = (meta.title or "")[:60]
        marker = "PICK" if label == "meaningful" else "skip"
        print(f"    {marker:4} {src_kind:<7} {label or 'error':<11} q={query[:22]:<22} {title}")
        if label != "meaningful":
            continue

        caption = build_deterministic_caption(meta)
        source_page = source_page_url(meta)
        picks.append(
            {
                "kind": src_kind,
                "query": query,
                "source_url": source_page,
                "image_url": meta.primary_image_url,
                "caption": caption,
                "alt": meta.title[:140],
                "vlm_reason": (verdict or {}).get("reason", ""),
            }
        )

    return {
        "section": section,
        "paragraph": paragraph,
        "queries": queries,
        "candidate_count": len(candidates),
        "picks": picks,
    }


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="first N paragraphs only")
    ap.add_argument("--target", type=int, default=4, help="target images per paragraph")
    ap.add_argument("--max-gates", type=int, default=16, help="max VLM calls per paragraph")
    ap.add_argument("--resume", action="store_true", help="skip paragraphs already in gallery.json")
    args = ap.parse_args()

    assessment = json.loads(
        (OUT_DIR / "assessment.json").read_text(encoding="utf-8")
    )

    # Group by (section, paragraph_before) preserving document order.
    groups: OrderedDict[tuple[str, str], dict] = OrderedDict()
    for r in assessment:
        key = (r["section"], r["paragraph_before"])
        if key not in groups:
            groups[key] = {"section": r["section"], "paragraph": r["paragraph_before"], "entities": []}
        ent = (r.get("vlm_verdict") or {}).get("primary_entity_in_claim")
        if ent and ent not in groups[key]["entities"]:
            groups[key]["entities"].append(ent)

    paragraphs = list(groups.values())
    if args.limit:
        paragraphs = paragraphs[: args.limit]

    # Resume support — skip paragraphs already in gallery.json with picks>=1.
    existing: list[dict] = []
    existing_keys: set[tuple[str, str]] = set()
    gallery_path = OUT_DIR / "gallery.json"
    if args.resume and gallery_path.exists():
        try:
            existing = json.loads(gallery_path.read_text(encoding="utf-8"))
            existing_keys = {(r["section"], r["paragraph"]) for r in existing}
            print(f"Resuming — {len(existing)} paragraphs already processed")
        except Exception as e:
            print(f"! could not read existing gallery.json: {e!r}")
            existing, existing_keys = [], set()

    print(f"Paragraphs to process: {len(paragraphs)}")
    print(f"Target images per paragraph: {args.target}")
    print(f"Max VLM gates per paragraph: {args.max_gates}\n")

    from pipeline.lyra.config import _get_settings
    from pipeline.lyra.minimax_shared import create_minimax_client

    settings = _get_settings()
    vlm_client = create_minimax_client(settings.minimax_base_url, settings.minimax_api_key)

    results: list[dict] = list(existing)
    async with httpx.AsyncClient() as http:
        for i, p in enumerate(paragraphs, 1):
            if (p["section"], p["paragraph"]) in existing_keys:
                print(f"\n--- [{i}/{len(paragraphs)}] (skipped, already done)")
                continue
            print(f"\n--- [{i}/{len(paragraphs)}] § {p['section'][:55]}")
            print(f"  PARA: {p['paragraph'][:160]}...")
            try:
                r = await pick_for_paragraph(
                    http, vlm_client, settings,
                    p["section"], p["paragraph"], p["entities"],
                    target=args.target, max_gates=args.max_gates,
                )
            except Exception as e:
                print(f"  !! fatal: {e!r}")
                r = {
                    "section": p["section"], "paragraph": p["paragraph"],
                    "queries": [], "candidate_count": 0, "picks": [],
                    "error": repr(e),
                }
            results.append(r)
            # Incremental write — don't lose progress if we crash.
            (OUT_DIR / "gallery.json").write_text(
                json.dumps(results, indent=2), encoding="utf-8"
            )

    vlm_client.close()

    # Render gallery.md
    md: list[str] = ["# Shining Ones — meaningful-image galleries\n"]
    total_picks = sum(len(r.get("picks", [])) for r in results)
    pcount = sum(1 for r in results if len(r.get("picks", [])) >= args.target)
    wcount = sum(1 for r in results if 0 < len(r.get("picks", [])) < args.target)
    zcount = sum(1 for r in results if len(r.get("picks", [])) == 0)
    md.append(
        f"**Paragraphs:** {len(results)}  "
        f"**full ({args.target}+ picks):** {pcount}  "
        f"**partial:** {wcount}  "
        f"**empty:** {zcount}  "
        f"**total picks:** {total_picks}\n"
    )
    for i, r in enumerate(results, 1):
        md.append(f"---\n\n## [{i}] §{r['section']}")
        md.append(f"**Paragraph:**\n\n> {r['paragraph'][:800]}\n")
        md.append(f"**Queries used:** {', '.join(f'`{q}`' for q in r.get('queries') or [])}")
        md.append(
            f"**Candidates gated:** {r.get('candidate_count', 0)}  "
            f"**Picks:** {len(r.get('picks', []))}\n"
        )
        for j, pick in enumerate(r.get("picks") or [], 1):
            md.append(f"### pick {j} — {pick['kind']}")
            md.append(f"![{pick['alt']}]({pick['image_url']})\n")
            md.append(f"- source: <{pick['source_url']}>")
            md.append(f"- caption: {pick['caption']}")
            md.append(f"- VLM: {pick['vlm_reason']}")
            md.append(f"- query: `{pick['query']}`\n")
        if r.get("error"):
            md.append(f"- error: {r['error']}")
        md.append("")
    (OUT_DIR / "gallery.md").write_text("\n".join(md), encoding="utf-8")

    print("\n=== Summary ===")
    print(f"  paragraphs     {len(results)}")
    print(f"  full galleries {pcount}")
    print(f"  partial        {wcount}")
    print(f"  empty          {zcount}")
    print(f"  total picks    {total_picks}")
    print(f"\n-> {OUT_DIR / 'gallery.json'}")
    print(f"-> {OUT_DIR / 'gallery.md'}")


if __name__ == "__main__":
    asyncio.run(main())
