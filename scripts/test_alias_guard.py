"""Test the alias mismatch guard tiers using trigram similarity.

Replicates PostgreSQL pg_trgm word_similarity() in pure Python to verify
the three-tier guard logic:
  - name_similarity >= 0.8 → auto-accept
  - name_similarity <  0.3 → auto-reject
  - 0.3 to 0.8            → needs Mercury LLM verification

Applies the same normalization as the DB (strip diacritics, lowercase)
to match real behavior.

Usage:
    python scripts/test_alias_guard.py
"""

from __future__ import annotations

import sys
import unicodedata


def _normalize(s: str) -> str:
    """Strip diacritics and lowercase, matching pipeline normalize_name."""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


def _trigrams(s: str) -> set[str]:
    """Generate trigrams matching pg_trgm behavior."""
    s = s.lower().strip()
    padded = f"  {s} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def word_similarity(query: str, target: str) -> float:
    """Python approximation of pg_trgm word_similarity(query, target)."""
    q_trgms = _trigrams(query)
    if not q_trgms:
        return 0.0

    t_trgms = _trigrams(target)
    if not t_trgms:
        return 0.0

    target_lower = target.lower().strip()
    best = 0.0

    for start in range(len(target_lower)):
        for end in range(start + 1, len(target_lower) + 1):
            s_trgms = _trigrams(target_lower[start:end])
            if not s_trgms:
                continue
            overlap = len(q_trgms & s_trgms)
            denom = max(len(q_trgms), len(s_trgms))
            sim = overlap / denom if denom > 0 else 0.0
            if sim > best:
                best = sim

    overlap = len(q_trgms & t_trgms)
    full_sim = overlap / max(len(q_trgms), len(t_trgms))
    best = max(best, full_sim)
    simple = len(q_trgms & t_trgms) / len(q_trgms) if q_trgms else 0.0
    best = max(best, simple)

    return best


# (search_query, site_name, is_same_site)
# We test whether the three-tier system handles each case safely:
#   - same_site=True  landing in "accept" or "llm" → SAFE
#   - same_site=True  landing in "reject"           → MISS (logged but not dangerous)
#   - same_site=False landing in "reject" or "llm"  → SAFE
#   - same_site=False landing in "accept"            → DANGEROUS (wrong link!)
TEST_CASES: list[tuple[str, str, bool]] = [
    # === SAME SITE (alternate names/spellings) ===
    ("gobekli tepe", "Göbekli Tepe", True),
    ("gobeklitepe", "Göbekli Tepe", True),
    ("machu picchu", "Machu Picchu", True),
    ("macchu picchu", "Machu Picchu", True),
    ("sacsayhuaman", "Sacsayhuamán", True),
    ("saksaywaman", "Sacsayhuamán", True),
    ("avebury henge", "Avebury", True),
    ("avebury stone circle", "Avebury", True),
    ("great pyramid of giza", "Great Pyramid of Giza", True),
    ("pyramid of khufu", "Great Pyramid of Giza", True),
    ("khufu pyramid", "Great Pyramid of Giza", True),
    ("teotihuacan", "Teotihuacán", True),
    ("chichen itza", "Chichén Itzá", True),
    ("angkor wat", "Angkor Wat", True),
    ("stonehenge", "Stonehenge", True),
    ("petra", "Petra", True),
    ("newgrange", "Newgrange", True),
    ("derinkuyu", "Derinkuyu Underground City", True),
    ("mohenjo daro", "Mohenjo-daro", True),
    ("catalhoyuk", "Çatalhöyük", True),
    ("tell el amarna", "Amarna", True),
    ("temple of hatshepsut", "Mortuary Temple of Hatshepsut", True),
    ("great zimbabwe", "Great Zimbabwe", True),
    ("leptis magna", "Leptis Magna", True),

    # === DIFFERENT SITE ===
    ("karahan tepe", "Göbekli Tepe", False),
    ("luxor temple", "Karnak", False),
    ("abu simbel", "Luxor Temple", False),
    ("knossos", "Phaistos", False),
    ("tikal", "Copán", False),
    ("carnac", "Stonehenge", False),
    ("baalbek", "Palmyra", False),
    ("pompeii", "Herculaneum", False),
    ("ephesus", "Pergamon", False),
    ("troy", "Mycenae", False),
    ("ur", "Uruk", False),
    ("persepolis", "Pasargadae", False),
    ("angkor thom", "Angkor Wat", False),
    ("ellora caves", "Ajanta Caves", False),
    ("borobudur", "Prambanan", False),
    ("mesa verde", "Chaco Canyon", False),
    ("cahokia", "Poverty Point", False),
    ("skara brae", "Ring of Brodgar", False),
    ("callanish", "Stonehenge", False),
    ("dolmen de menga", "Dolmen de Viera", False),
    ("sacsayhuaman", "Cusco", False),
    ("karnak", "Luxor Temple", False),
    ("valley of the kings", "Valley of the Queens", False),
    ("bru na boinne", "Newgrange", False),  # complex vs single site
]

REJECT_THRESHOLD = 0.3
ACCEPT_THRESHOLD = 0.8


def get_tier(sim: float, search_name: str) -> str:
    is_short = len(_normalize(search_name)) < 4
    if not is_short and sim < REJECT_THRESHOLD:
        return "reject"
    elif is_short or sim < ACCEPT_THRESHOLD:
        return "llm"
    return "accept"


def main() -> None:
    dangerous = 0  # False match auto-accepted
    missed = 0     # True match auto-rejected
    safe = 0

    all_results = []

    for search_query, site_name, is_same_site in TEST_CASES:
        # Normalize both sides like the DB does
        q_norm = _normalize(search_query)
        s_norm = _normalize(site_name)
        sim = round(word_similarity(q_norm, s_norm), 3)
        tier = get_tier(sim, search_query)

        is_dangerous = not is_same_site and tier == "accept"
        is_missed = is_same_site and tier == "reject"

        if is_dangerous:
            dangerous += 1
            label = "DANGEROUS"
        elif is_missed:
            missed += 1
            label = "MISSED"
        else:
            safe += 1
            label = "safe"

        all_results.append((search_query, site_name, is_same_site, sim, tier, label))

    # Print all results grouped by tier
    for tier_name in ["accept", "llm", "reject"]:
        tier_results = [r for r in all_results if r[4] == tier_name]
        if not tier_results:
            continue
        print(f"\n--- Tier: {tier_name.upper()} ---")
        for q, s, same, sim, _, label in tier_results:
            tag = "SAME" if same else "DIFF"
            flag = f"  *** {label} ***" if label != "safe" else ""
            print(f"  sim={sim:.3f}  [{tag}]  '{q}' vs '{s}'{flag}")

    total = len(TEST_CASES)
    print(f"\n{'=' * 65}")
    print(f"Total: {total} cases")
    print(f"Thresholds: reject < {REJECT_THRESHOLD} | LLM {REJECT_THRESHOLD}-{ACCEPT_THRESHOLD} | accept >= {ACCEPT_THRESHOLD}")
    print(f"  Safe:      {safe}")
    print(f"  Dangerous: {dangerous}  (DIFFERENT site auto-accepted — would create wrong link!)")
    print(f"  Missed:    {missed}  (SAME site auto-rejected — falls through to deep research)")

    llm_count = sum(1 for r in all_results if r[4] == "llm")
    print(f"\nMercury LLM calls needed: {llm_count} (out of {total} total)")

    if dangerous:
        print(f"\n*** CRITICAL: {dangerous} dangerous cases! Threshold is not safe. ***")
        sys.exit(1)
    elif missed:
        print(f"\nNote: {missed} true matches auto-rejected (will be found via deep research, not lost).")
        sys.exit(0)
    else:
        print(f"\nAll cases handled safely.")
        sys.exit(0)


if __name__ == "__main__":
    main()
