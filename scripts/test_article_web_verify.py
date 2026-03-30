"""Test MiniMax web verification on an existing article.

Usage:
    python scripts/test_article_web_verify.py [--article-id 13] [--section N]

Fetches article from the API, extracts body, runs MiniMax web verification
per-section, and prints the corrected output + web references.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fetch_article(article_id: int, api_url: str) -> dict:
    """Fetch article from the API."""
    import httpx

    resp = httpx.get(f"{api_url}/api/v1/articles/{article_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def extract_body(content: str) -> str:
    """Extract article body (between TLDR and Sources)."""
    # Remove TLDR (italic text at start)
    parts = content.split("\n\n---\n\n")
    if len(parts) >= 3:
        # parts[0] = TLDR, parts[1] = body, parts[2] = sources
        return parts[1]
    elif len(parts) == 2:
        # Might be body + sources
        return parts[0]
    return content


def main():
    parser = argparse.ArgumentParser(description="Test MiniMax web verification")
    parser.add_argument("--article-id", type=int, default=13)
    parser.add_argument("--api-url", default="http://127.0.0.1:18000")
    parser.add_argument("--section", type=int, help="Only verify section N (1-based)")
    parser.add_argument("--output", type=str, help="Write corrected article to file")
    args = parser.parse_args()

    # Configure MiniMax
    minimax_key = os.environ.get("LYRA_MINIMAX_API_KEY", "")
    if not minimax_key:
        print("ERROR: Set LYRA_MINIMAX_API_KEY environment variable")
        sys.exit(1)

    os.environ.setdefault("LYRA_ANTHROPIC_API_KEY", "unused")
    os.environ["LYRA_ARTICLE_WEB_BACKEND"] = "minimax"

    # Clear cached settings
    import pipeline.lyra.config as cfg
    cfg._cached_settings = None
    cfg.LyraSettings._resolve_env_fallbacks()

    from pipeline.lyra.config import LyraSettings
    from pipeline.lyra.web_research import MiniMaxWebResearch

    # Fetch article
    print(f"Fetching article {args.article_id} from {args.api_url}...")
    try:
        article = fetch_article(args.article_id, args.api_url)
    except Exception as e:
        print(f"ERROR fetching article: {e}")
        sys.exit(1)

    print(f"Title: {article['title']}")
    print(f"Published: {article['published_at']}")
    print()

    body = extract_body(article["content"])
    print(f"Article body: {len(body)} chars")

    # Split into sections
    sections = re.split(r"(?=^## )", body, flags=re.MULTILINE)
    sections = [s.strip() for s in sections if s.strip()]
    print(f"Sections: {len(sections)}")
    for i, s in enumerate(sections, 1):
        heading = s.split("\n", 1)[0][:70]
        print(f"  {i}. {heading}")
    print()

    # Initialize MiniMax backend
    settings = LyraSettings()
    backend = MiniMaxWebResearch(settings)

    t0 = time.time()

    if args.section:
        # Single section mode — verbose output
        if args.section < 1 or args.section > len(sections):
            print(f"ERROR: --section must be 1-{len(sections)}")
            sys.exit(1)
        idx = args.section - 1
        section = sections[idx]
        heading = section.split("\n", 1)[0][:60]
        print(f"{'='*60}")
        print(f"SECTION {idx + 1}: {heading}")
        print(f"{'='*60}")

        print("  Extracting verifiable claims...")
        claims = backend._extract_claims(section)
        for c in claims:
            print(f"    -> {c}")
        print(f"  Searching {len(claims)} queries...")
        search_results = []
        for query in claims:
            search_results.extend(backend._search(query))
            time.sleep(0.3)
        seen = set()
        unique = [r for r in search_results if r.url not in seen and not seen.add(r.url)]
        print(f"  Got {len(unique)} unique search results")
        print("  Verifying with M2.7...")
        v = backend._verify_section(section, unique)
        if v.web_citations:
            print(f"  Web references: {len(v.web_citations)}")
            for ref in v.web_citations:
                print(f"    - {ref.title}\n      {ref.url}")

        corrected_sections = list(sections)
        corrected_sections[idx] = v.corrected_text
        all_web_refs = v.web_citations
    else:
        # Full article mode — parallel workers
        print(f"Running {len(sections)} sections in PARALLEL...")
        corrected_body, all_web_refs = backend.verify_article(body)
        corrected_sections = re.split(r"(?=^## )", corrected_body, flags=re.MULTILINE)
        corrected_sections = [s.strip() for s in corrected_sections if s.strip()]

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"DONE in {elapsed:.1f}s — {len(all_web_refs)} web refs")
    print(f"{'='*60}")

    # Reassemble corrected article
    corrected_body = "\n\n".join(corrected_sections)

    if args.output:
        # Write full corrected article with web references
        output_parts = [corrected_body]
        if all_web_refs:
            refs_lines = []
            for i, ref in enumerate(all_web_refs):
                letter = chr(ord("a") + i) if i < 26 else f"a{i - 25}"
                date_str = f" ({ref.date})" if ref.date else ""
                refs_lines.append(f"{letter}. [{ref.title}]({ref.url}){date_str}")
            output_parts.append(
                "### Web References\n\n" + "\n".join(refs_lines)
            )
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n\n---\n\n".join(output_parts))
        print(f"\nCorrected article written to: {args.output}")
    else:
        # Print corrected body to stdout
        print("\n" + "=" * 60)
        print("CORRECTED ARTICLE BODY")
        print("=" * 60)
        print(corrected_body[:3000])
        if len(corrected_body) > 3000:
            print(f"\n... [{len(corrected_body) - 3000} more chars]")

        if all_web_refs:
            print("\n" + "=" * 60)
            print("WEB REFERENCES")
            print("=" * 60)
            for i, ref in enumerate(all_web_refs, 1):
                print(f"{i}. {ref.title}")
                print(f"   {ref.url}")


if __name__ == "__main__":
    main()
