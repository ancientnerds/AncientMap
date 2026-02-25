"""Daily quiz mode — knowledge questions generated from card data."""

import random
import uuid
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.cardgame.constants import (
    QUIZ_CREDITS_PER_CORRECT,
    QUIZ_DAILY_LIMIT,
    QUIZ_PERFECT_BONUS_TIER,
    QUIZ_QUESTIONS_PER_SESSION,
    QUIZ_XP_PER_CORRECT,
)
from api.cardgame.models import CardPlayerStats, CardStats, QuizSession
from pipeline.database import CreditGrant, DiscordUser, UnifiedSite


class QuizLimitReachedError(Exception):
    pass


class QuizAlreadySubmittedError(Exception):
    pass


# ---------------------------------------------------------------------------
# Question generators
# ---------------------------------------------------------------------------

def _generate_age_comparison(session: Session, rng: random.Random) -> dict | None:
    """Which is older: A or B?"""
    rows = (
        session.query(CardStats, UnifiedSite)
        .join(UnifiedSite, CardStats.site_id == UnifiedSite.id)
        .filter(UnifiedSite.period_start.isnot(None))
        .order_by(func.random())
        .limit(2)
        .all()
    )
    if len(rows) < 2:
        return None
    (c1, s1), (c2, s2) = rows
    if s1.period_start == s2.period_start:
        return None

    older = s1 if s1.period_start < s2.period_start else s2
    return {
        "type": "age_comparison",
        "question": f"Which is older: {s1.name} or {s2.name}?",
        "choices": [s1.name, s2.name],
        "correct": older.name,
        "explanation": f"{older.name} dates to {older.period_name}, making it the older site.",
    }


def _generate_country_question(session: Session, rng: random.Random) -> dict | None:
    """What country is X in?"""
    row = (
        session.query(CardStats, UnifiedSite)
        .join(UnifiedSite, CardStats.site_id == UnifiedSite.id)
        .filter(UnifiedSite.country.isnot(None))
        .order_by(func.random())
        .first()
    )
    if not row:
        return None
    card, site = row

    wrong = (
        session.query(UnifiedSite.country)
        .filter(UnifiedSite.country.isnot(None), UnifiedSite.country != site.country)
        .distinct()
        .order_by(func.random())
        .limit(3)
        .all()
    )
    if len(wrong) < 3:
        return None
    choices = [site.country] + [r[0] for r in wrong]
    rng.shuffle(choices)

    return {
        "type": "country",
        "question": f"What country is {site.name} in?",
        "choices": choices,
        "correct": site.country,
        "explanation": f"{site.name} is located in {site.country}.",
    }


def _generate_category_question(session: Session, rng: random.Random) -> dict | None:
    """What type of site is X?"""
    card = session.query(CardStats).order_by(func.random()).first()
    if not card or not card.site:
        return None
    site = card.site

    all_groups = [
        r[0] for r in
        session.query(CardStats.category_group)
        .filter(CardStats.category_group != card.category_group)
        .distinct()
        .all()
    ]
    if len(all_groups) < 3:
        return None
    wrong = rng.sample(all_groups, 3)
    choices = [card.category_group] + wrong
    rng.shuffle(choices)

    return {
        "type": "category",
        "question": f"What type of site is {site.name}?",
        "choices": choices,
        "correct": card.category_group,
        "explanation": f"{site.name} is classified as {card.category_group}.",
    }


def _generate_stat_question(session: Session, rng: random.Random) -> dict | None:
    """Which site has higher [stat]: A or B?"""
    stat = rng.choice(["mystery", "antiquity", "fortification", "cultural_influence", "legacy"])
    stat_display = stat.replace("_", " ").title()

    cards = session.query(CardStats).order_by(func.random()).limit(2).all()
    if len(cards) < 2:
        return None
    c1, c2 = cards
    s1, s2 = c1.site, c2.site
    if not s1 or not s2:
        return None

    v1, v2 = getattr(c1, stat), getattr(c2, stat)
    if v1 == v2:
        return None

    higher = s1 if v1 > v2 else s2
    higher_val = max(v1, v2)
    lower_val = min(v1, v2)

    return {
        "type": "stat_challenge",
        "question": f"Which site has higher {stat_display}: {s1.name} or {s2.name}?",
        "choices": [s1.name, s2.name],
        "correct": higher.name,
        "explanation": f"{higher.name} has {stat_display} {higher_val} vs {lower_val}.",
    }


def _generate_period_question(session: Session, rng: random.Random) -> dict | None:
    """What period does X belong to?"""
    row = (
        session.query(CardStats, UnifiedSite)
        .join(UnifiedSite, CardStats.site_id == UnifiedSite.id)
        .filter(UnifiedSite.period_name.isnot(None))
        .order_by(func.random())
        .first()
    )
    if not row:
        return None
    card, site = row

    wrong = (
        session.query(UnifiedSite.period_name)
        .filter(
            UnifiedSite.period_name.isnot(None),
            UnifiedSite.period_name != site.period_name,
        )
        .distinct()
        .order_by(func.random())
        .limit(3)
        .all()
    )
    if len(wrong) < 3:
        return None
    choices = [site.period_name] + [r[0] for r in wrong]
    rng.shuffle(choices)

    return {
        "type": "period",
        "question": f"What period does {site.name} belong to?",
        "choices": choices,
        "correct": site.period_name,
        "explanation": f"{site.name} belongs to the {site.period_name} period.",
    }


_GENERATORS = [
    _generate_age_comparison,
    _generate_country_question,
    _generate_category_question,
    _generate_stat_question,
    _generate_period_question,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_quiz(session: Session, user_id) -> dict:
    """Generate a quiz session with 5 questions.

    Returns: {session_id, questions: [{index, type, question, choices}]}
    Raises QuizLimitReachedError if daily limit reached.
    """
    now = datetime.now(UTC)

    today_count = (
        session.query(QuizSession)
        .filter(
            QuizSession.user_id == user_id,
            func.date(QuizSession.created_at) == now.date(),
        )
        .count()
    )
    if today_count >= QUIZ_DAILY_LIMIT:
        raise QuizLimitReachedError(f"Daily quiz limit ({QUIZ_DAILY_LIMIT}) reached")

    rng = random.Random()  # noqa: S311 — game logic
    questions: list[dict] = []
    attempts = 0

    while len(questions) < QUIZ_QUESTIONS_PER_SESSION and attempts < 30:
        gen = rng.choice(_GENERATORS)
        q = gen(session, rng)
        if q:
            q["index"] = len(questions)
            questions.append(q)
        attempts += 1

    quiz = QuizSession(
        user_id=user_id,
        questions=[
            {k: v for k, v in q.items() if k not in ("correct", "explanation")}
            for q in questions
        ],
        answers_key=[q["correct"] for q in questions],
        explanations=[q.get("explanation", "") for q in questions],
    )
    session.add(quiz)
    session.flush()

    return {
        "session_id": str(quiz.id),
        "questions": [
            {
                "index": q["index"],
                "type": q["type"],
                "question": q["question"],
                "choices": q["choices"],
            }
            for q in questions
        ],
    }


def submit_quiz_answers(
    session: Session,
    user: DiscordUser,
    quiz_session_id: str,
    answers: list[str],
) -> dict:
    """Grade quiz answers and distribute rewards.

    Returns: {score, total, results, rewards}
    """
    quiz = session.get(QuizSession, uuid.UUID(quiz_session_id))
    if not quiz:
        raise ValueError("Quiz session not found")
    if str(quiz.user_id) != str(user.id):
        raise ValueError("This quiz belongs to another player")
    if quiz.score is not None:
        raise QuizAlreadySubmittedError("Quiz already submitted")

    # Lock user row to prevent concurrent credit manipulation
    user = session.query(DiscordUser).filter(DiscordUser.id == user.id).with_for_update().first()

    correct = 0
    results = []
    for i, answer in enumerate(answers[: len(quiz.answers_key)]):
        is_correct = answer == quiz.answers_key[i]
        if is_correct:
            correct += 1
        results.append({
            "index": i,
            "your_answer": answer,
            "correct_answer": quiz.answers_key[i],
            "is_correct": is_correct,
            "explanation": quiz.explanations[i] if i < len(quiz.explanations) else "",
        })

    total = len(quiz.answers_key)
    quiz.score = correct
    quiz.submitted_at = datetime.now(UTC)

    # Distribute rewards
    credits_earned = correct * QUIZ_CREDITS_PER_CORRECT
    xp_earned = correct * QUIZ_XP_PER_CORRECT

    if credits_earned > 0:
        user.credits += credits_earned
        session.add(CreditGrant(
            user_id=user.id,
            amount=credits_earned,
            reason="quiz_reward",
        ))

    ps = session.get(CardPlayerStats, user.id)
    if not ps:
        ps = CardPlayerStats(user_id=user.id)
        session.add(ps)
    ps.xp += xp_earned

    # Perfect score bonus: 1 Common card
    bonus_card = None
    if correct == total and total > 0:
        from api.cardgame.models import CardCollection
        from api.cardgame.packs import _card_to_dict, _pick_card

        owned = {
            r[0] for r in
            session.query(CardCollection.site_id)
            .filter(CardCollection.user_id == user.id)
            .all()
        }
        card = _pick_card(session, QUIZ_PERFECT_BONUS_TIER, owned)
        if card:
            session.add(CardCollection(
                user_id=user.id,
                site_id=card.site_id,
                acquired_via="quiz_perfect",
            ))
            ps.total_cards += 1
            bonus_card = _card_to_dict(session, card)

    return {
        "score": correct,
        "total": total,
        "results": results,
        "rewards": {
            "credits": credits_earned,
            "xp": xp_earned,
            "bonus_card": bonus_card,
        },
    }
