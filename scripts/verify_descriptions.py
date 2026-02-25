#!/usr/bin/env python3
"""Phase 1: Detect issues in card descriptions via mechanical checks.

Produces output/verification_flags.json with:
- banned_openers: first-5-word openers appearing 3+ times
- overused_4grams: 4-grams appearing 10+ times
- country_list / demonym_map: country names and their adjective forms
- flagged: per-site issues dict
- clean_count / flagged_count: summary stats
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"

# ── Country / demonym data ──────────────────────────────────────────────────

DEMONYM_MAP = {
    "Afghanistan": ["afghan"],
    "Albania": ["albanian"],
    "Algeria": ["algerian"],
    "Armenia": ["armenian"],
    "Australia": ["australian"],
    "Austria": ["austrian"],
    "Azerbaijan": ["azerbaijani", "azeri"],
    "Bahrain": ["bahraini"],
    "Belgium": ["belgian"],
    "Belize": ["belizean"],
    "Bolivia": ["bolivian"],
    "Bosnia and Herzegovina": ["bosnian", "herzegovinian"],
    "Brazil": ["brazilian"],
    "Bulgaria": ["bulgarian"],
    "Cambodia": ["cambodian", "khmer"],
    "Canada": ["canadian"],
    "Chile, Easter Island": ["chilean", "easter island"],
    "China": ["chinese"],
    "Costa Rica": ["costa rican"],
    "Croatia": ["croatian"],
    "Cyprus": ["cypriot", "cyprian"],
    "Denmark": ["danish", "dane"],
    "Ecuador": ["ecuadorian"],
    "Egypt": ["egyptian"],
    "England": ["english"],
    "Eritrea": ["eritrean"],
    "Ethiopia": ["ethiopian"],
    "Finland": ["finnish", "finn"],
    "France": ["french"],
    "Georgia (country)": ["georgian"],
    "Germany": ["german"],
    "Greece": ["greek"],
    "Greenland": ["greenlandic"],
    "Guatemala": ["guatemalan"],
    "Honduras": ["honduran"],
    "Hungary": ["hungarian", "magyar"],
    "India": ["indian"],
    "Indonesia": ["indonesian"],
    "Iran": ["iranian", "persian"],
    "Iraq": ["iraqi"],
    "Ireland": ["irish"],
    "Israel": ["israeli"],
    "Italy": ["italian"],
    "Japan": ["japanese"],
    "Jordan": ["jordanian"],
    "Kazakhstan": ["kazakh", "kazakhstani"],
    "Laos": ["lao", "laotian"],
    "Lebanon": ["lebanese"],
    "Libya": ["libyan"],
    "Malta": ["maltese"],
    "Mauritania": ["mauritanian"],
    "Mexico": ["mexican"],
    "Mongolia": ["mongolian", "mongol"],
    "Morocco": ["moroccan"],
    "Myanmar": ["burmese", "myanmar"],
    "Netherlands": ["dutch", "netherlander"],
    "North Korea": ["north korean"],
    "North Macedonia": ["macedonian"],
    "Northern Mariana Islands": ["chamorro"],
    "Norway": ["norwegian"],
    "Pakistan": ["pakistani"],
    "Panama": ["panamanian"],
    "Peru": ["peruvian"],
    "Poland": ["polish"],
    "Portugal": ["portuguese"],
    "Republic of The Gambia": ["gambian"],
    "Romania": ["romanian"],
    "Russia": ["russian"],
    "Saudi Arabia": ["saudi", "arabian"],
    "Scotland": ["scottish", "scots"],
    "Serbia": ["serbian"],
    "Slovakia": ["slovak", "slovakian"],
    "South Korea": ["south korean", "korean"],
    "Spain": ["spanish"],
    "Sri Lanka": ["sri lankan"],
    "Sudan": ["sudanese"],
    "Sweden": ["swedish"],
    "Switzerland": ["swiss"],
    "Syria": ["syrian"],
    "Taiwan": ["taiwanese"],
    "Thailand": ["thai"],
    "Tunisia": ["tunisian"],
    "Turkey": ["turkish"],
    "USA": ["american"],
    "Ukraine": ["ukrainian"],
    "United Arab Emirates": ["emirati"],
    "Wales": ["welsh"],
    "Yemen": ["yemeni"],
    # Also add "British" as a cross-country demonym for UK nations
}

# Additional broad demonyms that apply to multiple countries
BROAD_DEMONYMS = {
    "british": ["England", "Scotland", "Wales"],
    "scandinavian": ["Denmark", "Norway", "Sweden", "Finland"],
    "iberian": ["Spain", "Portugal"],
    "balkan": ["Albania", "Bosnia and Herzegovina", "Bulgaria", "Croatia",
               "North Macedonia", "Romania", "Serbia"],
}

# ── Hedging / filler / discovery patterns ───────────────────────────────────

HEDGING_PATTERNS = [
    r"\bit is believed\b",
    r"\bit is thought\b",
    r"\bthought to be\b",
    r"\bbelieved to be\b",
    r"\bscholars suggest\b",
    r"\bit is said\b",
    r"\bpossibly\b",
    r"\bprobably\b",
    r"\bmay have been\b",
    r"\bmight have been\b",
    r"\bgenerally considered\b",
    r"\bwidely believed\b",
    r"\bsome scholars\b",
    r"\bsome historians\b",
    r"\baccording to legend\b",
    r"\baccording to tradition\b",
]

FILLER_PATTERNS = [
    r"\bimportant site\b",
    r"\brich history\b",
    r"\bremarkable example\b",
    r"\bancient ruins\b",
    r"\bone of the most important\b",
    r"\bsignificant archaeological\b",
    r"\bfascinating\b",
    r"\bimpressive\b",
    r"\bnotable for\b",
    r"\bserves as a testament\b",
    r"\btestament to\b",
    r"\boffers a glimpse\b",
    r"\bprovides valuable insight\b",
    r"\ba window into\b",
    r"\ba glimpse into\b",
]

DISCOVERY_PATTERNS = [
    r"\bdiscovered (?:by|in)\b",
    r"\bexcavated (?:by|in)\b",
    r"\bunearthed\b",
    r"\brediscovered\b",
    r"\bfirst explored\b",
    r"\bfirst investigated\b",
]

# Compile all regex once
HEDGING_RE = [re.compile(p, re.IGNORECASE) for p in HEDGING_PATTERNS]
FILLER_RE = [re.compile(p, re.IGNORECASE) for p in FILLER_PATTERNS]
DISCOVERY_RE = [re.compile(p, re.IGNORECASE) for p in DISCOVERY_PATTERNS]


def load_data():
    with open(OUTPUT / "card_descriptions.json", encoding="utf-8") as f:
        raw = json.load(f)
    descs = raw["descriptions"]

    with open(OUTPUT / "card_sites.json", encoding="utf-8") as f:
        sites_list = json.load(f)
    sites = {s["site_id"]: s for s in sites_list}

    return descs, sites


def build_opener_counts(descs):
    """Count first-5-word openers across all descriptions."""
    counter = Counter()
    for desc in descs.values():
        words = desc.lower().split()[:5]
        opener = " ".join(words)
        counter[opener] += 1
    return counter


def is_date_4gram(gram):
    """Return True if this 4-gram is just a date reference (not a style issue)."""
    # Patterns like "from the 1st century", "in the 2nd century",
    # "the 1st century ad", "the 4th millennium bc", "century bc to the", etc.
    date_patterns = [
        r"^(?:from|in|of|during) the \d+(?:st|nd|rd|th) (?:century|millennium)$",
        r"^the \d+(?:st|nd|rd|th) (?:century|millennium) (?:bc|ad|bc\.|ad\.)$",
        r"^(?:century|millennium) (?:bc|ad) (?:to|through|until|and) the$",
        r"^a \d+(?:st|nd|rd|th)-century ad (?:roman|greek|byzantine)$",
        r"^the \d+(?:st|nd|rd|th) century (?:bc|ad|bc\.|ad\.)$",
        r"^from the \d+(?:st|nd|rd|th) (?:to|millennium)$",
        r"^the \d+(?:st|nd|rd|th) (?:century|millennium) bc$",
        r"^(?:from|in) the (?:bronze|iron) age$",
        r"^from the (?:bronze|iron|stone) age$",
    ]
    for pat in date_patterns:
        if re.match(pat, gram):
            return True
    return False


def build_fourgram_counts(descs):
    """Count all 4-grams across all descriptions, excluding date references."""
    counter = Counter()
    for desc in descs.values():
        words = desc.lower().split()
        for i in range(len(words) - 3):
            gram = " ".join(words[i : i + 4])
            if not is_date_4gram(gram):
                counter[gram] += 1
    return counter


def check_country_mention(desc_lower, site_country):
    """Check if description mentions the site's country name or demonym."""
    issues = []

    # Normalize country name for matching
    country_clean = site_country.lower()
    # Handle special cases like "Georgia (country)", "Chile, Easter Island"
    country_variants = [country_clean]
    if "(" in country_clean:
        country_variants.append(country_clean.split("(")[0].strip())
    if "," in country_clean:
        parts = [p.strip() for p in country_clean.split(",")]
        country_variants.extend(parts)

    # Check country name
    for variant in country_variants:
        if len(variant) < 4:
            # Skip very short names that are substrings of other words
            # (e.g., "Iran" in "terrain" — but Iran is 4 chars, so check carefully)
            continue
        # Use word boundary matching for longer names
        if re.search(r'\b' + re.escape(variant) + r'\b', desc_lower):
            issues.append(f"country_mention:{site_country}")
            break

    # Check demonyms
    demonyms = DEMONYM_MAP.get(site_country, [])
    for dem in demonyms:
        if re.search(r'\b' + re.escape(dem) + r'\b', desc_lower):
            issues.append(f"demonym_mention:{dem}")
            break

    # Check broad demonyms
    for broad_dem, countries in BROAD_DEMONYMS.items():
        if site_country in countries:
            if re.search(r'\b' + re.escape(broad_dem) + r'\b', desc_lower):
                issues.append(f"demonym_mention:{broad_dem}")

    return issues


def check_hedging(desc):
    hits = []
    for rx in HEDGING_RE:
        m = rx.search(desc)
        if m:
            hits.append(f"hedging:{m.group().lower()}")
    return hits


def check_filler(desc):
    hits = []
    for rx in FILLER_RE:
        m = rx.search(desc)
        if m:
            hits.append(f"filler:{m.group().lower()}")
    return hits


def check_discovery(desc):
    hits = []
    for rx in DISCOVERY_RE:
        m = rx.search(desc)
        if m:
            hits.append(f"discovery:{m.group().lower()}")
    return hits


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("Loading data...")
    descs, sites = load_data()
    print(f"  {len(descs)} descriptions, {len(sites)} sites")

    # Build global stats
    print("Analyzing openers...")
    opener_counts = build_opener_counts(descs)
    banned_openers = {
        opener: count
        for opener, count in opener_counts.items()
        if count >= 3
    }
    print(f"  {len(banned_openers)} banned openers (3+ occurrences)")

    print("Analyzing 4-grams...")
    fourgram_counts = build_fourgram_counts(descs)
    overused_4grams = {
        gram: count
        for gram, count in fourgram_counts.items()
        if count >= 10
    }
    print(f"  {len(overused_4grams)} overused 4-grams (10+ occurrences)")

    # Build opener map: desc -> its opener
    desc_openers = {}
    for sid, desc in descs.items():
        words = desc.lower().split()[:5]
        desc_openers[sid] = " ".join(words)

    # Per-description checks
    print("Running per-description checks...")
    flagged = {}
    clean_count = 0

    for sid, desc in descs.items():
        issues = []
        desc_lower = desc.lower()
        site = sites.get(sid)

        # 1. Repeated opener (first 5 words match 3+ others)
        opener = desc_openers[sid]
        if opener in banned_openers:
            issues.append(f"repeated_opener:{opener}")

        # 2. Overused 4-grams
        words = desc_lower.split()
        seen_grams = set()
        for i in range(len(words) - 3):
            gram = " ".join(words[i : i + 4])
            if gram in overused_4grams and gram not in seen_grams:
                issues.append(f"overused_phrase:{gram}")
                seen_grams.add(gram)

        # 3. Country mention
        if site:
            country_issues = check_country_mention(desc_lower, site["country"])
            issues.extend(country_issues)

        # 4. Hedging
        issues.extend(check_hedging(desc))

        # 5. Filler
        issues.extend(check_filler(desc))

        # 6. Discovery history
        issues.extend(check_discovery(desc))

        # 7. Length > 200 chars
        if len(desc) > 200:
            issues.append(f"too_long:{len(desc)}")

        if issues:
            flagged[sid] = {
                "issues": issues,
                "current_description": desc,
                "site_name": site["name"] if site else "?",
                "country": site["country"] if site else "?",
            }
        else:
            clean_count += 1

    flagged_count = len(flagged)
    print(f"  Clean: {clean_count}, Flagged: {flagged_count}")

    # Build output
    result = {
        "banned_openers": dict(
            sorted(banned_openers.items(), key=lambda x: -x[1])
        ),
        "overused_4grams": dict(
            sorted(overused_4grams.items(), key=lambda x: -x[1])
        ),
        "country_list": sorted(set(s["country"] for s in sites.values())),
        "demonym_map": {k: v for k, v in sorted(DEMONYM_MAP.items())},
        "flagged": flagged,
        "clean_count": clean_count,
        "flagged_count": flagged_count,
    }

    out_path = OUTPUT / "verification_flags.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nWrote {out_path}")
    print(f"  {clean_count} clean + {flagged_count} flagged = {clean_count + flagged_count} total")

    # Print issue breakdown
    issue_types = Counter()
    for entry in flagged.values():
        for iss in entry["issues"]:
            issue_type = iss.split(":")[0]
            issue_types[issue_type] += 1

    print("\nIssue breakdown (descriptions affected):")
    for itype, count in issue_types.most_common():
        print(f"  {count:5d} {itype}")


if __name__ == "__main__":
    main()
