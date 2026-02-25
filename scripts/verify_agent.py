#!/usr/bin/env python3
"""Phase 2 agent: verify + rewrite descriptions for a single batch.

Usage: python scripts/verify_agent.py <batch_index>

Reads:  output/verify_batch_XX.json
Writes: output/verify_result_XX.json

For each site:
- Factual check: compare description against wiki text
- Rewrite (flagged only): write new description avoiding banned phrases

Description rules:
- Max 200 characters
- Never mention the site's country name or demonym (reader sees country on the card)
- Open with a unique hook — a specific fact, number, date, or vivid detail
- Do NOT use any phrase from the banned_openers or overused_4grams lists
- No hedging ("believed to be", "thought to be", "possibly", "probably")
- No filler ("important site", "rich history", "remarkable example", "one of the most important")
- No discovery history ("discovered by", "excavated in", "unearthed")
- Two sentences max, dense with facts. Every word must earn its place.
- End with punctuation (period, question mark, or closing quote)
- Use an em dash (—) for asides, not parentheses
- Prefer concrete numbers, dates, and measurements over vague descriptions
"""

import json
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"


def check_facts(desc, wiki_text, name):
    """Compare description against wiki text for factual issues.

    Returns None if clean, or a dict with issue details.
    """
    issues = []

    # Extract years/dates from description
    desc_years = set(re.findall(r'\b(\d{3,4})\s*(?:BC|AD|bc|ad)\b', desc))
    desc_years.update(re.findall(r'\b(\d{3,4})\s*(?:BCE|CE|bce|ce)\b', desc))

    # Extract years from wiki
    wiki_years = set(re.findall(r'\b(\d{3,4})\s*(?:BC|AD|bc|ad|BCE|CE|bce|ce)\b', wiki_text))

    # Check if description claims specific years not in wiki
    for year in desc_years:
        if year not in wiki_text and int(year) > 100:
            # Only flag if the year isn't approximately mentioned
            year_int = int(year)
            # Check if a close year exists in wiki (within 100 years)
            close = any(
                abs(int(wy) - year_int) <= 100
                for wy in wiki_years
                if wy.isdigit()
            )
            if not close and str(year) not in wiki_text:
                issues.append(f"year {year} not found in wiki text")

    # Extract specific measurements from description
    measurements = re.findall(r'(\d+(?:\.\d+)?)\s*(?:m|metres?|meters?|km|hectares?|ha|feet|ft)\b', desc, re.IGNORECASE)
    for m in measurements:
        if m not in wiki_text:
            # Check if it's approximately there
            try:
                val = float(m)
                if val > 10:  # Only flag significant measurements
                    found_close = False
                    wiki_nums = re.findall(r'(\d+(?:\.\d+)?)', wiki_text)
                    for wn in wiki_nums:
                        try:
                            if abs(float(wn) - val) / max(val, 1) < 0.2:
                                found_close = True
                                break
                        except ValueError:
                            continue
                    if not found_close:
                        issues.append(f"measurement {m} not verified in wiki text")
            except ValueError:
                pass

    if issues:
        return {"issues": issues}
    return None


def rewrite_description(site, banned_openers, overused_4grams):
    """Generate a replacement description for a flagged site.

    This function creates the rewrite prompt but cannot call an LLM.
    It returns a structured prompt that will be used by the agent.
    """
    # This is a placeholder — the actual rewriting happens in the agent
    # The agent script outputs the data needed for rewriting
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/verify_agent.py <batch_index>")
        sys.exit(1)

    batch_idx = int(sys.argv[1])
    sys.stdout.reconfigure(encoding="utf-8")

    batch_path = OUTPUT / f"verify_batch_{batch_idx:02d}.json"
    with open(batch_path, encoding="utf-8") as f:
        batch = json.load(f)

    banned_openers = set(batch["banned_openers"])
    overused_4grams = set(batch["overused_4grams"])
    sites = batch["sites"]

    results = {
        "batch_index": batch_idx,
        "factual_issues": {},
        "needs_rewrite": {},
        "confirmed_clean": 0,
    }

    for site in sites:
        sid = site["site_id"]
        desc = site["current_description"]
        wiki = site["wiki_text"]
        name = site["name"]

        # Factual check for ALL sites
        fact_issue = check_facts(desc, wiki, name)
        if fact_issue:
            results["factual_issues"][sid] = {
                "name": name,
                "current_description": desc,
                "issues": fact_issue["issues"],
                "wiki_excerpt": wiki[:300],
            }

        # Mark flagged sites for rewrite
        if site["flagged"]:
            results["needs_rewrite"][sid] = {
                "name": name,
                "site_type": site["site_type"],
                "period_name": site["period_name"],
                "period_start": site["period_start"],
                "country": site["country"],
                "current_description": desc,
                "issues": site["issues"],
                "wiki_text": wiki,
            }
        elif not fact_issue:
            results["confirmed_clean"] += 1

    out_path = OUTPUT / f"verify_result_{batch_idx:02d}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Batch {batch_idx}: {len(sites)} sites")
    print(f"  Factual issues: {len(results['factual_issues'])}")
    print(f"  Needs rewrite:  {len(results['needs_rewrite'])}")
    print(f"  Confirmed clean: {results['confirmed_clean']}")
    print(f"  → {out_path}")


if __name__ == "__main__":
    main()
