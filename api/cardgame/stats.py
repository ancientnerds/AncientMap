"""Stat computation engine — pure functions, no side effects.

Each function takes site data and returns an int (1-10).
"""

from api.cardgame.constants import (
    ANTIQUITY_BUCKETS,
    ANTIQUITY_DEFAULT,
    GROUP_FORTIFICATION,
    MYSTERY_BUCKETS,
    MYSTERY_DEFAULT,
    get_group,
    get_rarity_tier,
)


def compute_antiquity(period_start: int | None) -> int:
    """Older sites score higher. NULL defaults to 5."""
    if period_start is None:
        return ANTIQUITY_DEFAULT
    for threshold, value in ANTIQUITY_BUCKETS:
        if period_start < threshold:
            return value
    return 1  # post-1500 CE


def compute_fortification(site_type: str | None) -> int:
    """Based on category group — Fortifications=10, Cave=2, etc."""
    group = get_group(site_type)
    return GROUP_FORTIFICATION.get(group, 3)


def compute_cultural_influence(
    *,
    has_description: bool,
    has_thumbnail: bool,
    content_link_count: int,
    wiki_image_count: int,
    has_source_url: bool,
) -> int:
    """Composite score from how well-documented the site is.

    Raw score 0-13, normalized to 1-10.
    """
    raw = 0
    if has_description:
        raw += 2
    if has_thumbnail:
        raw += 2
    raw += min(content_link_count, 4)  # cap at 4
    raw += min(wiki_image_count, 3)  # cap at 3
    if has_source_url:
        raw += 2
    # Normalize 0-13 → 1-10
    return max(1, min(10, round(raw * 10 / 13)))


def compute_mystery(combo_count: int) -> int:
    """Rarer (site_type, period_name) combos score higher."""
    for threshold, value in MYSTERY_BUCKETS:
        if combo_count <= threshold:
            return value
    return MYSTERY_DEFAULT


def compute_legacy(
    *,
    period_start: int | None,
    period_end: int | None,
    is_unesco: bool,
    like_count: int,
    bookmark_count: int,
) -> int:
    """Composite: age span + UNESCO + community engagement.

    Raw score 0-10, clamped.
    """
    raw = 0.0

    # Age span contribution (0-3 points)
    if period_start is not None and period_end is not None:
        span = abs(period_end - period_start)
        if span >= 3000:
            raw += 3
        elif span >= 1000:
            raw += 2
        elif span >= 500:
            raw += 1

    # UNESCO bonus (0-4 points)
    if is_unesco:
        raw += 4

    # Community engagement (0-3 points)
    engagement = like_count + bookmark_count
    if engagement >= 10:
        raw += 3
    elif engagement >= 5:
        raw += 2
    elif engagement >= 1:
        raw += 1

    return max(1, min(10, round(raw)))


def compute_rarity_score(
    *,
    mystery: int,
    cultural_influence: int,
    is_unesco: bool,
    content_type_count: int,
    has_3d_model: bool,
) -> int:
    """Rarity score — determines the card's rarity tier.

    mystery * 3 + cultural_influence * 2 + UNESCO bonus + content variety + 3D bonus
    """
    score = mystery * 3 + cultural_influence * 2
    if is_unesco:
        score += 15
    score += min(content_type_count, 5) * 2
    if has_3d_model:
        score += 8
    return score


def compute_all_stats(
    *,
    period_start: int | None,
    period_end: int | None,
    site_type: str | None,
    has_description: bool,
    has_thumbnail: bool,
    content_link_count: int,
    wiki_image_count: int,
    has_source_url: bool,
    combo_count: int,
    is_unesco: bool,
    like_count: int,
    bookmark_count: int,
    content_type_count: int,
    has_3d_model: bool,
    country: str | None,
) -> dict:
    """Compute all stats for a site. Returns dict ready for CardStats insert."""
    antiquity = compute_antiquity(period_start)
    fortification = compute_fortification(site_type)
    cultural_influence = compute_cultural_influence(
        has_description=has_description,
        has_thumbnail=has_thumbnail,
        content_link_count=content_link_count,
        wiki_image_count=wiki_image_count,
        has_source_url=has_source_url,
    )
    mystery = compute_mystery(combo_count)
    legacy = compute_legacy(
        period_start=period_start,
        period_end=period_end,
        is_unesco=is_unesco,
        like_count=like_count,
        bookmark_count=bookmark_count,
    )
    total_power = antiquity + fortification + cultural_influence + mystery + legacy
    rarity_score = compute_rarity_score(
        mystery=mystery,
        cultural_influence=cultural_influence,
        is_unesco=is_unesco,
        content_type_count=content_type_count,
        has_3d_model=has_3d_model,
    )
    tier, tier_name = get_rarity_tier(rarity_score)
    group = get_group(site_type)

    return {
        "antiquity": antiquity,
        "fortification": fortification,
        "cultural_influence": cultural_influence,
        "mystery": mystery,
        "legacy": legacy,
        "total_power": total_power,
        "rarity_score": rarity_score,
        "rarity_tier": tier,
        "category_group": group,
        "civilization": country,
    }
