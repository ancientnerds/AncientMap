"""Batch test MiniMax web verification across all articles, multiple runs.

Usage:
    python scripts/test_web_verify_batch.py [--runs 5] [--api-url http://127.0.0.1:18000]

Runs web verification on every article, N times each, and reports:
- Success/failure per run
- Web refs collected (with URL validation)
- Inline [letter] markers placed
- Orphan [wN]/[RN] markers (should be 0)
- Broken URLs in web refs
- Sections that timed out or fell back
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def fetch_articles(api_url: str) -> list[dict]:
    """Fetch all articles with full content."""
    import httpx
    resp = httpx.get(f"{api_url}/api/v1/articles", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else data.get("items", data.get("articles", []))
    # List endpoint lacks content — fetch each article individually
    full_articles = []
    for item in items:
        detail = httpx.get(f"{api_url}/api/v1/articles/{item['id']}", timeout=10)
        detail.raise_for_status()
        full_articles.append(detail.json())
    return full_articles


def extract_body(content: str) -> str:
    parts = content.split("\n\n---\n\n")
    if len(parts) >= 3:
        return parts[1]
    elif len(parts) == 2:
        return parts[0]
    return content


def analyze_output(original_body: str, corrected_body: str, web_refs: list) -> dict:
    """Analyze a single verification run for issues."""
    issues = []

    # Count inline letter citations
    letter_cites = re.findall(r"\[[a-z]\]", corrected_body)

    # Check for orphan [wN] markers (should have been renumbered)
    orphan_w = re.findall(r"\[w\d+\]", corrected_body)
    if orphan_w:
        issues.append(f"Orphan [wN] markers: {orphan_w}")

    # Check for orphan [RN] markers (should have been stripped)
    orphan_r = re.findall(r"\[R\d+\]", corrected_body)
    if orphan_r:
        issues.append(f"Orphan [RN] markers: {len(orphan_r)} found")

    # Check for new numeric citations not in original
    orig_nums = set(re.findall(r"\[\d+\]", original_body))
    new_nums = set(re.findall(r"\[\d+\]", corrected_body)) - orig_nums
    if new_nums:
        issues.append(f"Injected numeric citations: {new_nums}")

    # Check web ref URLs
    broken_urls = []
    valid_urls = []
    for ref in web_refs:
        if not ref.url.startswith(("http://", "https://")):
            broken_urls.append(f"{ref.title}: {ref.url[:50]}")
        else:
            valid_urls.append(ref.url)

    if broken_urls:
        issues.append(f"Broken URLs: {broken_urls}")

    # Check if body changed at all
    changed = corrected_body != original_body

    # Check section count preserved
    orig_sections = len(re.findall(r"^## ", original_body, re.MULTILINE))
    new_sections = len(re.findall(r"^## ", corrected_body, re.MULTILINE))
    if orig_sections != new_sections:
        issues.append(f"Section count changed: {orig_sections} -> {new_sections}")

    # Check images preserved
    orig_images = len(re.findall(r"!\[", original_body))
    new_images = len(re.findall(r"!\[", corrected_body))
    if orig_images != new_images:
        issues.append(f"Image count changed: {orig_images} -> {new_images}")

    # Check YouTube citations preserved
    orig_yt_cites = set(re.findall(r"\[\d+\]", original_body))
    remaining_yt = set(re.findall(r"\[\d+\]", corrected_body))
    lost_cites = orig_yt_cites - remaining_yt
    if lost_cites:
        issues.append(f"Lost YouTube citations: {lost_cites}")

    return {
        "changed": changed,
        "letter_citations": len(letter_cites),
        "web_refs_total": len(web_refs),
        "web_refs_valid": len(valid_urls),
        "web_refs_broken": len(broken_urls),
        "orphan_w": len(orphan_w),
        "orphan_r": len(orphan_r),
        "injected_nums": len(new_nums),
        "sections_preserved": orig_sections == new_sections,
        "images_preserved": orig_images == new_images,
        "yt_citations_preserved": len(lost_cites) == 0,
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch test web verification")
    parser.add_argument("--runs", type=int, default=5, help="Runs per article")
    parser.add_argument("--api-url", default="http://127.0.0.1:18000")
    parser.add_argument("--article-id", type=int, help="Test single article only")
    args = parser.parse_args()

    minimax_key = os.environ.get("LYRA_MINIMAX_API_KEY", "")
    if not minimax_key:
        print("ERROR: Set LYRA_MINIMAX_API_KEY")
        sys.exit(1)

    os.environ.setdefault("LYRA_ANTHROPIC_API_KEY", "unused")
    os.environ["LYRA_ARTICLE_WEB_BACKEND"] = "minimax"

    import pipeline.lyra.config as cfg
    cfg._cached_settings = None
    cfg.LyraSettings._resolve_env_fallbacks()
    from pipeline.lyra.config import LyraSettings
    from pipeline.lyra.web_research import MiniMaxWebResearch

    # Fetch articles
    print(f"Fetching articles from {args.api_url}...")
    articles = fetch_articles(args.api_url)
    if args.article_id:
        articles = [a for a in articles if a["id"] == args.article_id]
    print(f"Found {len(articles)} articles\n")

    settings = LyraSettings()
    backend = MiniMaxWebResearch(settings)

    all_results = []
    output_dir = "scripts/batch_test_output"
    os.makedirs(output_dir, exist_ok=True)

    for article in articles:
        aid = article["id"]
        title = article["title"][:60].encode("ascii", "replace").decode()
        body = extract_body(article["content"])
        sections = re.split(r"(?=^## )", body, flags=re.MULTILINE)
        sections = [s.strip() for s in sections if s.strip()]

        print(f"{'='*70}")
        print(f"ARTICLE {aid}: {title}")
        print(f"  {len(body)} chars, {len(sections)} sections")
        print(f"{'='*70}")

        for run in range(1, args.runs + 1):
            print(f"\n  Run {run}/{args.runs}...", end=" ", flush=True)
            t0 = time.time()

            try:
                corrected, web_refs = backend.verify_article(body)
                elapsed = time.time() - t0

                # Apply same safety strip as production pipeline
                original_yt = set(re.findall(r"\[\d+\]", body))
                new_nums = set(re.findall(r"\[\d+\]", corrected)) - original_yt
                for m in new_nums:
                    corrected = corrected.replace(m, "")
                corrected = re.sub(r"\[R\d+\]", "", corrected)

                analysis = analyze_output(body, corrected, web_refs)

                status = "OK" if not analysis["issues"] else "ISSUES"
                print(
                    f"{status} in {elapsed:.0f}s — "
                    f"{analysis['letter_citations']} inline cites, "
                    f"{analysis['web_refs_valid']} valid refs, "
                    f"{analysis['web_refs_broken']} broken"
                    + (f" | {analysis['issues']}" if analysis["issues"] else "")
                )

                analysis["article_id"] = aid
                analysis["run"] = run
                analysis["elapsed"] = round(elapsed, 1)
                all_results.append(analysis)

                # Save first run's output
                if run == 1:
                    outfile = f"{output_dir}/article_{aid}_corrected.md"
                    with open(outfile, "w", encoding="utf-8") as f:
                        f.write(corrected)

            except Exception as e:
                elapsed = time.time() - t0
                print(f"FAIL in {elapsed:.0f}s — {e}")
                all_results.append({
                    "article_id": aid,
                    "run": run,
                    "elapsed": round(elapsed, 1),
                    "error": str(e),
                    "issues": [f"Exception: {e}"],
                })

            # Cooldown between runs to avoid overwhelming MiniMax API
            if run < args.runs:
                time.sleep(5)

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    total_runs = len(all_results)
    errors = sum(1 for r in all_results if "error" in r)
    issues_runs = sum(1 for r in all_results if r.get("issues"))
    clean_runs = total_runs - issues_runs

    print(f"Total runs: {total_runs}")
    print(f"Clean: {clean_runs}, Issues: {issues_runs - errors}, Errors: {errors}")
    print()

    # Aggregate issue types
    issue_counts: dict[str, int] = {}
    for r in all_results:
        for issue in r.get("issues", []):
            key = issue.split(":")[0] if ":" in issue else issue
            issue_counts[key] = issue_counts.get(key, 0) + 1

    if issue_counts:
        print("Issue frequency:")
        for issue, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
            print(f"  {count}x {issue}")
    print()

    # Per-article stats
    for article in articles:
        aid = article["id"]
        runs = [r for r in all_results if r.get("article_id") == aid]
        avg_refs = sum(r.get("web_refs_valid", 0) for r in runs) / max(len(runs), 1)
        avg_cites = sum(r.get("letter_citations", 0) for r in runs) / max(len(runs), 1)
        avg_time = sum(r.get("elapsed", 0) for r in runs) / max(len(runs), 1)
        print(
            f"  Article {aid}: {avg_refs:.1f} avg refs, "
            f"{avg_cites:.1f} avg inline cites, {avg_time:.0f}s avg"
        )

    # Save full report
    report_path = f"{output_dir}/batch_report.json"
    with open(report_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    main()
