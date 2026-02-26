#!/usr/bin/env python3
"""Phase 3: Multilingual Wikipedia Article Selection.

For each site with sitelinks, selects the best Wikipedia article:
- Prefers English if article > 2000 bytes
- Falls back to priority languages (local language, de, fr, it, es, etc.)
- Fetches article extract from the best source

Usage:
    python scripts/enrich_wiki_select.py
"""

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

_HEADERS = {
    "User-Agent": "AncientNerdsMap/1.0 (https://ancientnerds.com; contact@ancientnerds.com)",
    "Accept": "application/json",
}

OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Minimum article size to be considered useful
MIN_ARTICLE_BYTES = 2000

# Country -> preferred local Wikipedia language
COUNTRY_LANG = {
    "Germany": "de", "Austria": "de", "Switzerland": "de",
    "France": "fr", "Belgium": "fr",
    "Italy": "it",
    "Spain": "es", "Mexico": "es", "Peru": "es", "Colombia": "es",
    "Portugal": "pt", "Brazil": "pt",
    "Greece": "el",
    "Turkey": "tr",
    "Egypt": "ar", "Iraq": "ar", "Syria": "ar", "Jordan": "ar",
    "Lebanon": "ar", "Libya": "ar", "Tunisia": "ar", "Algeria": "ar",
    "Morocco": "ar",
    "Iran": "fa",
    "Israel": "he",
    "Russia": "ru",
    "China": "zh",
    "Japan": "ja",
    "India": "hi",
    "Indonesia": "id",
    "Netherlands": "nl",
    "Poland": "pl",
    "Czech Republic": "cs", "Czechia": "cs",
    "Romania": "ro",
    "Hungary": "hu",
    "Sweden": "sv",
    "Norway": "no",
    "Denmark": "da",
    "Finland": "fi",
    "Croatia": "hr",
    "Serbia": "sr",
    "Bulgaria": "bg",
    "Albania": "sq",
    "Georgia": "ka",
    "Armenia": "hy",
}

# Priority fallback languages (after English and local)
FALLBACK_LANGS = ["de", "fr", "it", "es", "el", "tr", "ar", "ru", "pt", "nl", "pl"]


def _get_article_size(client: httpx.Client, lang: str, title: str) -> int:
    """Get article byte size via Wikipedia API prop=info."""
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    try:
        resp = client.get(api_url, params={
            "action": "query",
            "titles": title,
            "prop": "info",
            "format": "json",
        })
        if resp.status_code != 200:
            return 0
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            if "missing" not in page:
                return page.get("length", 0)
    except Exception:
        pass
    return 0


def _get_article_extract(client: httpx.Client, lang: str, title: str) -> dict | None:
    """Fetch article extract via REST API."""
    from urllib.parse import quote
    rest_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'), safe='')}"
    try:
        resp = client.get(rest_url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("type") == "disambiguation":
            return None
        extract = data.get("extract", "")
        if not extract:
            return None
        return {
            "lang": lang,
            "title": title,
            "extract": extract,
            "byte_size": len(extract.encode("utf-8")),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page",
                   f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"),
        }
    except Exception:
        return None


def select_best_article(
    client: httpx.Client,
    sitelinks: dict[str, str],
    country: str | None,
) -> dict | None:
    """Select the best Wikipedia article for a site."""
    if not sitelinks:
        return None

    # Build priority language list
    priority_langs = ["en"]
    if country:
        local_lang = COUNTRY_LANG.get(country)
        if local_lang and local_lang not in priority_langs:
            priority_langs.append(local_lang)
    for lang in FALLBACK_LANGS:
        if lang not in priority_langs:
            priority_langs.append(lang)

    # Check article sizes for available languages
    lang_sizes: list[tuple[str, str, int]] = []
    for lang in priority_langs:
        wiki_key = lang  # sitelinks already use short lang codes
        title = sitelinks.get(wiki_key)
        if not title:
            continue

        size = _get_article_size(client, lang, title)
        lang_sizes.append((lang, title, size))

        # If English is good enough, use it immediately
        if lang == "en" and size >= MIN_ARTICLE_BYTES:
            break

        time.sleep(0.2)

    if not lang_sizes:
        return None

    # Pick best: English if >= MIN_ARTICLE_BYTES, otherwise longest
    en_entry = next((e for e in lang_sizes if e[0] == "en"), None)
    if en_entry and en_entry[2] >= MIN_ARTICLE_BYTES:
        best_lang, best_title, _ = en_entry
    else:
        # Sort by size descending, pick the largest
        lang_sizes.sort(key=lambda x: x[2], reverse=True)
        best_lang, best_title, best_size = lang_sizes[0]
        if best_size < 500:  # Too small to be useful
            return None

    # Fetch extract
    return _get_article_extract(client, best_lang, best_title)


def main() -> None:
    claims_path = OUTPUT_DIR / "enrichment_claims.json"
    if not claims_path.exists():
        print(f"Error: {claims_path} not found. Run: python scripts/enrich_fetch_claims.py")
        sys.exit(1)

    with open(claims_path, encoding="utf-8") as f:
        claims_data = json.load(f)

    # Load card_sites.json for country info
    card_sites_path = OUTPUT_DIR / "card_sites.json"
    site_countries: dict[str, str | None] = {}
    if card_sites_path.exists():
        with open(card_sites_path, encoding="utf-8") as f:
            sites = json.load(f)
        for s in sites:
            site_countries[s["site_id"]] = s.get("country")

    site_claims = claims_data.get("claims", {})

    # Filter to sites with sitelinks
    sites_with_sitelinks = {
        sid: data for sid, data in site_claims.items()
        if data.get("sitelinks")
    }
    total = len(sites_with_sitelinks)
    print(f"[WIKI] Selecting best articles for {total} sites with sitelinks", flush=True)

    client = httpx.Client(headers=_HEADERS, timeout=30.0, follow_redirects=True)
    articles: dict[str, dict] = {}

    for i, (site_id, data) in enumerate(sites_with_sitelinks.items()):
        sitelinks = data.get("sitelinks", {})
        country = site_countries.get(site_id)

        result = select_best_article(client, sitelinks, country)
        if result:
            articles[site_id] = result

        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{total} sites ({len(articles)} articles selected)...", flush=True)

        time.sleep(0.3)

    client.close()

    # Stats
    lang_counts: dict[str, int] = {}
    for a in articles.values():
        lang = a["lang"]
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    output = {
        "articles": articles,
        "stats": {
            "total_with_sitelinks": total,
            "articles_selected": len(articles),
            "by_language": lang_counts,
        },
    }

    output_path = OUTPUT_DIR / "enrichment_wiki.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[WIKI] Results saved to {output_path}", flush=True)
    print(f"  Articles selected: {len(articles)} / {total}", flush=True)
    print(f"  By language:", flush=True)
    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
        print(f"    {lang}: {count}", flush=True)


if __name__ == "__main__":
    main()
