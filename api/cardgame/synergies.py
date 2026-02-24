"""Deck synergy computation — bonuses from category, empire diversity, era, cross-combo, and trade routes."""

from collections import Counter
from itertools import combinations

from api.cardgame.constants import (
    ANCIENT_ANCHOR_BONUS,
    ANCIENT_ANCHOR_THRESHOLD,
    COMMANDER_BONUS,
    COMMANDER_MAX_CARDS,
    CROSS_COMBO_BONUS,
    CROSS_COMBO_PAIRS,
    CROSSROADS_THRESHOLDS,
    EMPIRE_DISPLAY_NAMES,
    EMPIRE_THEMATIC_STATS,
    GROUP_PRIMARY_STAT,
    PERIOD_BUCKETS,
    SYNERGY_CATEGORY_BONUS,
    SYNERGY_TEMPORAL_BONUS,
    SYNERGY_THRESHOLD,
    TRADE_NETWORK_BONUS,
    TRADE_ROUTE_BONUS,
    TRADE_ROUTE_MAX_ACTIVE,
    TRADE_ROUTES,
)
from api.cardgame.models import CardStats

STAT_NAMES = ["antiquity", "fortification", "cultural_influence", "mystery", "legacy"]


def _find_active_trade_routes(
    deck: list[CardStats],
) -> tuple[
    list[tuple[str, str, str, str, bool]],  # (name, empire_a, empire_b, goods, is_triangle)
    dict[str, list[CardStats]],              # empire_id → cards
]:
    """Find active trade routes for a deck, prioritizing triangle networks.

    Returns (active_routes, empire_to_cards).
    Each active route tuple includes a boolean for whether it's part of a triangle.
    """
    # Build empire → cards mapping
    empire_to_cards: dict[str, list[CardStats]] = {}
    for card in deck:
        for emp in getattr(card, "empires", None) or []:
            empire_to_cards.setdefault(emp, []).append(card)

    deck_empires = set(empire_to_cards.keys())

    # Find candidate routes where both empires are present
    candidates: list[tuple[str, str, str, str]] = []
    for name, emp_a, emp_b, goods in TRADE_ROUTES:
        if emp_a in deck_empires and emp_b in deck_empires:
            candidates.append((name, emp_a, emp_b, goods))

    if not candidates:
        return [], empire_to_cards

    # Build a set of connected empire pairs for triangle detection
    pair_set: set[frozenset[str]] = set()
    for _, emp_a, emp_b, _ in candidates:
        pair_set.add(frozenset((emp_a, emp_b)))

    # Detect triangles: 3 empires all pairwise connected
    triangle_pairs: set[frozenset[str]] = set()
    candidate_empires = {e for _, ea, eb, _ in candidates for e in (ea, eb)}
    for trio in combinations(candidate_empires, 3):
        a, b, c = trio
        ab = frozenset((a, b))
        bc = frozenset((b, c))
        ac = frozenset((a, c))
        if ab in pair_set and bc in pair_set and ac in pair_set:
            triangle_pairs |= {ab, bc, ac}

    # Prioritize: triangle routes first, then non-triangle
    triangle_routes: list[tuple[str, str, str, str, bool]] = []
    single_routes: list[tuple[str, str, str, str, bool]] = []
    for name, emp_a, emp_b, goods in candidates:
        pair = frozenset((emp_a, emp_b))
        if pair in triangle_pairs:
            triangle_routes.append((name, emp_a, emp_b, goods, True))
        else:
            single_routes.append((name, emp_a, emp_b, goods, False))

    active = (triangle_routes + single_routes)[:TRADE_ROUTE_MAX_ACTIVE]
    return active, empire_to_cards


def _get_period_bucket(period_start: int | None) -> str | None:
    """Map a period_start year to a named period bucket."""
    if period_start is None:
        return None
    for upper_bound, name in PERIOD_BUCKETS:
        if period_start < upper_bound:
            return name
    return "Medieval"


def compute_synergies(
    deck: list[CardStats],
    commander_empire_id: str | None = None,
) -> dict[str, dict[str, int]]:
    """Compute synergy bonuses for each card in a deck.

    Returns: {site_id_str: {"antiquity": bonus, "fortification": bonus, ...}}
    """
    bonuses: dict[str, dict[str, int]] = {}
    for card in deck:
        bonuses[str(card.site_id)] = dict.fromkeys(STAT_NAMES, 0)

    # --- Category synergy: 3+ same group → +1 to group's primary stat ---
    group_counts = Counter(c.category_group for c in deck)
    for card in deck:
        if group_counts[card.category_group] >= SYNERGY_THRESHOLD:
            primary_stat = GROUP_PRIMARY_STAT.get(card.category_group, "mystery")
            bonuses[str(card.site_id)][primary_stat] += SYNERGY_CATEGORY_BONUS

    # --- Crossroads synergy: empire diversity → +N cultural_influence to ALL ---
    all_empires: set[str] = set()
    for card in deck:
        card_empires = getattr(card, "empires", None) or []
        all_empires.update(card_empires)

    crossroads_bonus = 0
    for threshold, bonus_val in CROSSROADS_THRESHOLDS:
        if len(all_empires) >= threshold:
            crossroads_bonus = bonus_val
            break

    if crossroads_bonus > 0:
        for card in deck:
            bonuses[str(card.site_id)]["cultural_influence"] += crossroads_bonus

    # --- Ancient Anchor synergy: 2+ pre-empire cards → +1 mystery to anchors ---
    anchor_cards = [c for c in deck if (getattr(c, "empire_count", 0) or 0) == 0]
    if len(anchor_cards) >= ANCIENT_ANCHOR_THRESHOLD:
        for card in anchor_cards:
            bonuses[str(card.site_id)]["mystery"] += ANCIENT_ANCHOR_BONUS

    # --- Commander synergy: homeland cards get +1 thematic stat (max 3) ---
    if commander_empire_id:
        thematic_stat = EMPIRE_THEMATIC_STATS.get(commander_empire_id)
        if thematic_stat:
            # Find cards whose empires list contains the commander's empire
            homeland_cards = [
                c for c in deck
                if commander_empire_id in (getattr(c, "empires", None) or [])
            ]
            # Pick top 3 by base thematic stat value (descending)
            homeland_cards.sort(
                key=lambda c: getattr(c, thematic_stat, 0),
                reverse=True,
            )
            for card in homeland_cards[:COMMANDER_MAX_CARDS]:
                bonuses[str(card.site_id)][thematic_stat] += COMMANDER_BONUS

    # --- Temporal synergy: 3+ cards in same period bucket → +1 legacy ---
    card_buckets: dict[str, str | None] = {}
    for card in deck:
        site = card.site  # eagerly loaded via relationship
        period_start = site.period_start if site else None
        card_buckets[str(card.site_id)] = _get_period_bucket(period_start)

    bucket_counts = Counter(b for b in card_buckets.values() if b is not None)
    for card in deck:
        bucket = card_buckets.get(str(card.site_id))
        if bucket and bucket_counts[bucket] >= SYNERGY_THRESHOLD:
            bonuses[str(card.site_id)]["legacy"] += SYNERGY_TEMPORAL_BONUS

    # --- Cross-combo: category pairs from same country → +2 mystery ---
    country_group_cards: dict[tuple[str, str], list[str]] = {}
    for card in deck:
        if card.civilization:
            key = (card.civilization, card.category_group)
            country_group_cards.setdefault(key, []).append(str(card.site_id))

    for group_a, group_b in CROSS_COMBO_PAIRS:
        for country in {k[0] for k in country_group_cards}:
            cards_a = country_group_cards.get((country, group_a), [])
            cards_b = country_group_cards.get((country, group_b), [])
            if cards_a and cards_b:
                for sid in cards_a + cards_b:
                    bonuses[sid]["mystery"] += CROSS_COMBO_BONUS

    # --- Trade Routes: empire pairs connected by historical trade → +1/+2 legacy ---
    active_routes, empire_to_cards = _find_active_trade_routes(deck)
    for _name, emp_a, emp_b, _goods, is_triangle in active_routes:
        bonus_val = TRADE_NETWORK_BONUS if is_triangle else TRADE_ROUTE_BONUS
        for emp in (emp_a, emp_b):
            cards_for_emp = empire_to_cards.get(emp, [])
            if cards_for_emp:
                # Pick the card with the lowest legacy (helps weaker cards)
                target = min(cards_for_emp, key=lambda c: c.legacy)
                bonuses[str(target.site_id)]["legacy"] += bonus_val

    return bonuses


def describe_synergies(
    deck: list[CardStats],
    commander_empire_id: str | None = None,
) -> list[str]:
    """Return human-readable list of active synergies for a deck."""
    descriptions = []

    # Category synergy
    group_counts = Counter(c.category_group for c in deck)
    for group, count in group_counts.items():
        if count >= SYNERGY_THRESHOLD:
            stat = GROUP_PRIMARY_STAT.get(group, "mystery")
            descriptions.append(
                f"Category: {count}x {group} → +{SYNERGY_CATEGORY_BONUS} "
                f"{stat.replace('_', ' ').title()}"
            )

    # Crossroads synergy
    all_empires: set[str] = set()
    for card in deck:
        card_empires = getattr(card, "empires", None) or []
        all_empires.update(card_empires)

    for threshold, bonus_val in CROSSROADS_THRESHOLDS:
        if len(all_empires) >= threshold:
            descriptions.append(
                f"Crossroads: {len(all_empires)} empires → "
                f"+{bonus_val} Cultural Influence to all"
            )
            break

    # Ancient Anchor
    anchor_cards = [c for c in deck if (getattr(c, "empire_count", 0) or 0) == 0]
    if len(anchor_cards) >= ANCIENT_ANCHOR_THRESHOLD:
        descriptions.append(
            f"Ancient Anchor: {len(anchor_cards)} pre-empire sites → "
            f"+{ANCIENT_ANCHOR_BONUS} Mystery to anchors"
        )

    # Commander
    if commander_empire_id:
        thematic_stat = EMPIRE_THEMATIC_STATS.get(commander_empire_id)
        if thematic_stat:
            homeland_count = sum(
                1 for c in deck
                if commander_empire_id in (getattr(c, "empires", None) or [])
            )
            boosted = min(homeland_count, COMMANDER_MAX_CARDS)
            if boosted > 0:
                empire_name = EMPIRE_DISPLAY_NAMES.get(
                    commander_empire_id, commander_empire_id,
                )
                descriptions.append(
                    f"Commander ({empire_name}): {boosted} homeland sites → "
                    f"+{COMMANDER_BONUS} {thematic_stat.replace('_', ' ').title()}"
                )

    # Temporal synergy
    card_buckets: dict[str, str | None] = {}
    for card in deck:
        site = card.site
        period_start = site.period_start if site else None
        card_buckets[str(card.site_id)] = _get_period_bucket(period_start)
    bucket_counts = Counter(b for b in card_buckets.values() if b is not None)
    for bucket, count in bucket_counts.items():
        if count >= SYNERGY_THRESHOLD:
            descriptions.append(
                f"Temporal: {count}x {bucket} → +{SYNERGY_TEMPORAL_BONUS} Legacy"
            )

    # Cross-combo
    country_group_cards: dict[tuple[str, str], list[str]] = {}
    for card in deck:
        if card.civilization:
            key = (card.civilization, card.category_group)
            country_group_cards.setdefault(key, []).append(str(card.site_id))
    for group_a, group_b in CROSS_COMBO_PAIRS:
        for country in {k[0] for k in country_group_cards}:
            if country_group_cards.get((country, group_a)) and country_group_cards.get((country, group_b)):
                descriptions.append(
                    f"Cross-combo: {group_a} + {group_b} ({country}) → "
                    f"+{CROSS_COMBO_BONUS} Mystery"
                )

    # Trade Routes
    active_routes, _empire_to_cards = _find_active_trade_routes(deck)
    for name, emp_a, emp_b, goods, is_triangle in active_routes:
        display_a = EMPIRE_DISPLAY_NAMES.get(emp_a, emp_a)
        display_b = EMPIRE_DISPLAY_NAMES.get(emp_b, emp_b)
        bonus_val = TRADE_NETWORK_BONUS if is_triangle else TRADE_ROUTE_BONUS
        tag = " [Trade Network]" if is_triangle else ""
        descriptions.append(
            f"Trade Route: {name} ({display_a} \u2194 {display_b}) \u2192 "
            f"+{bonus_val} Legacy{tag} \u2014 {goods}"
        )

    return descriptions
