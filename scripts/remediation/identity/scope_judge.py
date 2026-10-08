"""D20: the scope window - which sites past the E3 cutoff stay, which are dated wrongly, which go.

Owner decision D20 (2026-10-08): "check and retire autonomously: a wrong period is corrected
(sourced), a truly out-of-window site is retired (journalled)". The discovery (`scope_window.py`,
130 sites: the 127 outside the window, the pending ones and Hadrian's Wall Path) says *where each
stored date came from*: 78 were written by the MiniMax-answered field waves WD3/WD4 (`recheck_d10`),
so the question never trusts the stored date.

**The question** (stage `scope-window-web`, role `web_verifier`, Sonnet; prompt `scope-window-v1`):

* `PERIOD_WRONG`   - a source dates the site's start at or before the region's cutoff (give that
                     year with a quote; the stored one is wrong, or empty, or already right). The
                     entry is kept (`in_scope`) and the corrected start goes to the fields lane as
                     a hand-off (`PERIOD_WRONG.jsonl`), which writes it with its own quote gates;
* `OUT_OF_WINDOW`  - sources show the site began after the cutoff and nothing of it is older (give
                     the sourced year and a quote): retired;
* `MUSEUM_KEEP`    - a museum that exhibits ancient material (scope rule d; quote): `in_scope`;
* `NOT_A_SITE`     - not an archaeological site at all (natural formation, modern, object, legend
                     or hoax; quotes from at least two different websites, the Wikimedia projects
                     counting as one, as `scope_review` demands): retired.

**The re-check** (stage `scope-window-recheck`, role `adversarial`, Opus) asks every `OUT_OF_WINDOW`
and `NOT_A_SITE`, because a retirement is a 410 for that URL (and the `in_scope` -> `retired` and
`pending` -> `retired` transitions are the dangerous ones).

**The write** is `scope-window-<wave>` (`mechanical/identity_lanes.py`): `scope_status` and
`scope_reason` of one site in one transaction, the premise the entry the decision judged. A date
retirement's reason is `E3: period_start N is past the cutoff; <quote>`, a not-a-site retirement's
`scope_review`'s `E3: not an archaeological site (<kind>): <reason>`.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(_HERE.parents[1])):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from mechanical import plan as MP  # noqa: E402
from mechanical.identity_lanes import IN_SCOPE, scope_window_lane  # noqa: E402
from mechanical.lane import (  # noqa: E402
    NOT_A_SITE_PREFIX,
    SCOPE_REVIEW_PREMISE_SQL,
    Lane,
    sql_literal,
)
from mechanical.scope_review import KINDS, MIN_SITES, website  # noqa: E402

from identity import answers as A  # noqa: E402
from identity import common, export, waves  # noqa: E402
from identity.prompts import (  # noqa: E402
    cache_entries,
    cache_section,
    earlier_section,
    wiki_cache_dir,
)
from identity.rounds import (  # noqa: E402
    DECIDED,
    HELD,
    AnswerError,
    Env,
    Outcome,
    Question,
    StageSpec,
)
from pipeline.normalizers.dates import E3_CUTOFFS, e3_region  # noqa: E402
from pipeline.utils.public_sites import RETIRED  # noqa: E402

LANE = "scope-window"
WEB, RECHECK = "scope-window-web", "scope-window-recheck"
PROMPT_ID = "scope-window-v1"
PERIOD_WRONG, OUT_OF_WINDOW, MUSEUM_KEEP, NOT_A_SITE = (
    "PERIOD_WRONG",
    "OUT_OF_WINDOW",
    "MUSEUM_KEEP",
    "NOT_A_SITE",
)
VERDICTS = (PERIOD_WRONG, OUT_OF_WINDOW, MUSEUM_KEEP, NOT_A_SITE)
#: The verdicts a retirement rests on: the adversarial re-check asks them.
RETIRING = (OUT_OF_WINDOW, NOT_A_SITE)
CONFIRM, REJECT = "CONFIRM", "REJECT"
ANSWER_KEYS = frozenset(
    {"site_id", "verdict", "why", "period_start", "found_start", "kind", "quotes"}
)
RECHECK_KEYS = frozenset({"site_id", "verdict", "why", "quotes"})
YEAR_LOW, YEAR_HIGH = -200_000, 2100
SOURCE_FILE = "SCOPE_WINDOW.jsonl"
PERIOD_WRONG_FILE = "PERIOD_WRONG.jsonl"
DIR = "scope-window"


# ------------------------------------------------------------------------------------ the contexts
def cutoff_of(record: Mapping[str, Any]) -> tuple[str, int]:
    """The region of a record and its cutoff year (`dates.e3_region`, `dates.E3_CUTOFFS`)."""
    region = e3_region(record)
    if region is None:
        raise common.IdentityError(f"{record['id']} has no longitude: the window cannot be told")
    return region, E3_CUTOFFS[region]


def site_context(
    record: Mapping[str, Any],
    ext: Mapping[str, Sequence[str]],
    cache: Sequence[Mapping[str, str]],
    exported_at: str,
) -> dict[str, Any]:
    """Everything the question is a function of, JSON-able and stored with the round."""
    region, cutoff = cutoff_of(record)
    return {
        "site_id": record["id"],
        "exported_at": exported_at,
        "name": record["name"],
        "country": record["country"],
        "site_type": record["site_type"],
        "lat": record["lat"],
        "lon": record["lon"],
        "groups": list(record["groups"]),
        "museum_question": bool(record["museum_question"]),
        "scope_status": record["scope_status"],
        "scope_reason": record["scope_reason"],
        "period_start": record["period_start"],
        "period_end": record["period_end"],
        "period_name": record["period_name"],
        "date_used": record["date_used"],
        "region": region,
        "cutoff": cutoff,
        "origin": record["origin"],
        "recheck_d10": bool(record["recheck_d10"]),
        "period_writes": record["period_writes"],
        "description": record["description"],
        "source_url": record["source_url"],
        "images": record["images"],
        "qids": list(ext.get("wikidata_qid", [])),
        "enwiki": list(ext.get("enwiki_title", [])),
        "cache": list(cache),
    }


def questions(run: Path, *, root: Path | None = None) -> list[Question]:
    """One question per site of `SCOPE_WINDOW.jsonl`, from the discovery's files."""
    exported = export.load_export(run / common.EXPORT_FILE)
    ext: dict[str, dict[str, list[str]]] = {}
    for e in exported.ext_ids:
        ext.setdefault(e["site_id"], {}).setdefault(e["kind"], []).append(e["value"])
    cache = cache_entries(wiki_cache_dir(root))
    return [
        Question(
            r["id"],
            site_context(r, ext.get(r["id"], {}), cache.get(r["id"], []), exported.exported_at),
        )
        for r in common.read_jsonl(run / SOURCE_FILE)
    ]


# -------------------------------------------------------------------------------------- the prompt
WEB_TEMPLATE = """You are a period and field researcher of the scope review (owner decision D20, \
prompt {prompt_id}) of the Ancient Nerds final repair. One entry of a map of ancient sites lies past \
the date window the map covers, or has no scope decision yet. Decide what is true of it, from sources. \
Research on the open web; read the pages you cite.

THE ENTRY, as the database holds it (read {exported_at})
  id:           {site_id}
  name:         {name}
  country:      {country}
  point:        {lat}, {lon}
  type:         {site_type}
  period:       {period}
  source_url:   {source_url}
  Wikidata:     {qids}
  Wikipedia:    {titles}
  scope status: {status}
  description (first {chars} characters):
{description}

WHY IT IS ASKED
{why}
WHERE THE STORED DATE CAME FROM (do NOT trust it: research the date yourself)
{writes}{cache}{earlier}
THE WINDOW (owner decisions E3 and O7)
The map covers the {region} through {cutoff} AD ({cutoff_note}). The date the window tests is the \
entry's period_end when it is set, else its period_start: here {date_used}. A museum stays when it \
exhibits ancient material; its own date is its founding year.

THE QUESTION. Decide ONE verdict:
  PERIOD_WRONG   a source dates the start of the site at or before {cutoff} AD, so the stored date \
is wrong (or empty, or - for an entry that is only asked because it is pending - already right). Give \
that year as "period_start" (an integer; BC is negative) and quote the source. The entry stays on \
the map; the year goes to the field lane that writes dates with its own gates.
  OUT_OF_WINDOW  sources show that the site began after {cutoff} AD and that nothing of it is older. \
Give the year you found as "found_start" (an integer past {cutoff}) and quote the source that dates \
it. The entry is retired - it becomes a 410 - so be sure.
  MUSEUM_KEEP    {museum_note}
  NOT_A_SITE     the entry is no archaeological site at all: "kind" is natural_formation (a natural \
landform without human-made remains), modern (made after antiquity, without ancient remains), \
object (a movable object or a collection, not a place) or legend_or_hoax (a place that exists only \
in legend or an unsupported claim). Give quotes from at least {min_sites} different websites (the \
Wikipedias, Wikidata and Commons count as one website, and so do copies of Wikipedia). The entry is \
retired.

THE RULES
1. A quote is verbatim text (whitespace may differ) of a page you cite by its URL. The machine \
fetches every cited URL and does not count a verdict whose quote it cannot find there. Never cite \
ancientnerds.com. Prefer plain HTML pages; a 403 or 429 from a server is no finding.
2. Whether the date is inside the window is the question; whether the entry is interesting is not.
3. A date is a year of a source about THIS site at THIS point, not about a namesake or the modern \
town around it.

ANSWER with only this JSON object:
{{
 "site_id": "{site_id}",
 "verdict": "PERIOD_WRONG | OUT_OF_WINDOW | MUSEUM_KEEP | NOT_A_SITE",
 "why": "one or two sentences",
 "period_start": null,
 "found_start": null,
 "kind": null,
 "quotes": [{{"url": "https://...", "quote": "..."}}]
}}
"period_start" is set for PERIOD_WRONG, "found_start" for OUT_OF_WINDOW, "kind" for NOT_A_SITE; the \
others are null.
"""

RECHECK_TEMPLATE = """You are the adversarial reviewer of the scope review (owner decision D20) of \
the Ancient Nerds final repair. A researcher proposed to RETIRE one entry of a map of ancient sites; a \
retired entry becomes a 410 for its URL and is gone from the map, so try to REFUTE the proposal \
before you confirm it. Research on the open web with your own searches; do not trust the proposal's \
quotes, read the pages.

THE ENTRY (read {exported_at})
  id: {site_id}   name: {name}   country: {country}   point: {lat}, {lon}
  type: {site_type}   period: {period}   scope status now: {status}
  source_url: {source_url}
  Wikidata: {qids}   Wikipedia: {titles}
  description: {description}
{cache}
THE WINDOW: the {region} through {cutoff} AD; the stored date tested is {date_used} (do not trust \
it: {origin_note}).

THE PROPOSAL (verdict {verdict})
  why: {why}
{proposal}
{earlier}
THE QUESTION
{question}
Answer CONFIRM only when you found, on pages you read yourself, that the proposal is right. Answer \
REJECT when anything is wrong or unproven (say what). Every CONFIRM carries at least one quote: \
verbatim text of a page you cite by its URL; the machine fetches it and does not count a \
confirmation whose quote it cannot find. Never cite ancientnerds.com.

ANSWER with only this JSON object:
{{"site_id": "{site_id}", "verdict": "CONFIRM | REJECT", "why": "one or two sentences", \
"quotes": [{{"url": "https://...", "quote": "..."}}]}}
"""

QUESTIONS = {
    OUT_OF_WINDOW: (
        "Is it true that the site began after the cutoff and that no source dates any part of it at "
        "or before the cutoff (an earlier phase, a foundation, a reuse of older remains)? A site "
        "founded in the window and used into later centuries stays."
    ),
    NOT_A_SITE: (
        "Is it true that this entry is no archaeological site - nothing ancient is there to see or "
        "to find, nor a place known from ancient sources? A museum of ancient material, a heritage "
        "area with ancient remains and a site known only from texts are sites."
    ),
}


def _period(ctx: Mapping[str, Any]) -> str:
    start, end, name = ctx["period_start"], ctx["period_end"], ctx["period_name"]
    when = "no start" if start is None else f"{start}" + (f" to {end}" if end else "")
    return when + (f" ({name})" if name else "")


def _date_text(ctx: Mapping[str, Any]) -> str:
    return "none (the entry has no date)" if ctx["date_used"] is None else str(ctx["date_used"])


def _writes(ctx: Mapping[str, Any]) -> str:
    lines = [f"  origin of period_start: {ctx['origin']}"]
    if ctx["recheck_d10"]:
        lines.append(
            "  (written by a field wave whose MiniMax-answered share was withdrawn by owner "
            "decision D10: the date may be a rule's or a model's guess)"
        )
    for column in ("period_start", "period_end", "period_name"):
        w = ctx["period_writes"].get(column)
        if w is None:
            continue
        lines.append(
            f"  {column}: {w['old']!r} -> {w['new']!r} by {w['family']} ({w['confidence']}"
            + (f", models {w['models']}" if w["models"] else "")
            + ")"
            + (", reverted" if w["reverted"] else "")
        )
    return "\n".join(lines)


def _why(ctx: Mapping[str, Any]) -> str:
    texts = {
        "outside_window": f"  - its date {ctx['date_used']} lies past the cutoff {ctx['cutoff']} AD",
        "pending": "  - an earlier scope review left it pending: "
        f"{ctx['scope_reason'] or 'no reason recorded'}",
        "hadrians_wall_path": "  - a footpath opened in 2003 with no scope decision",
        "calibration": "  - a calibration case: decide as for any entry of the window",
    }
    lines = [texts[g] for g in ctx["groups"]]
    if ctx["museum_question"]:
        lines.append("  - it is a Museum: the museum rule (exhibits ancient material) applies")
    return "\n".join(lines)


def render_web(ctx: Mapping[str, Any], earlier: str | None = None) -> str:
    """The exact web question for one entry. Pure: the stored context and, for a re-ask, why the
    earlier answer was held."""
    description = str(ctx["description"] or "(none)")
    cutoff = ctx["cutoff"]
    return WEB_TEMPLATE.format(
        prompt_id=PROMPT_ID,
        exported_at=ctx["exported_at"],
        site_id=ctx["site_id"],
        name=ctx["name"],
        country=ctx["country"],
        lat=ctx["lat"],
        lon=ctx["lon"],
        site_type=ctx["site_type"],
        period=_period(ctx),
        source_url=ctx["source_url"],
        qids=", ".join(f"{q} (https://www.wikidata.org/wiki/{q})" for q in ctx["qids"]) or "none",
        titles=", ".join(ctx["enwiki"]) or "none",
        status=ctx["scope_status"] or "none yet",
        chars=len(description),
        description="    " + description.replace("\n", "\n    "),
        why=_why(ctx),
        writes=_writes(ctx),
        cache=cache_section(ctx),
        earlier=earlier_section(earlier),
        region=ctx["region"],
        cutoff=cutoff,
        cutoff_note=(
            "Americas and Oceania: 1500 AD" if cutoff == 1500 else "the rest of the world: 500 AD"
        ),
        date_used=_date_text(ctx),
        museum_note=(
            "the entry is a Museum that exhibits ancient material (scope rule d): quote a page that "
            "says what it exhibits. It stays (in_scope)."
            if ctx["museum_question"]
            else "not for this entry (it is no Museum): never answer it."
        ),
        min_sites=MIN_SITES,
    )


# ------------------------------------------------------------------------------------ the answer
@dataclass(frozen=True)
class Answer:
    site_id: str
    verdict: str
    why: str
    period_start: int | None
    found_start: int | None
    kind: str | None
    quotes: tuple[dict[str, str], ...]


def _year(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not YEAR_LOW <= value <= YEAR_HIGH:
        raise AnswerError(f"{what} is not a year (an integer from {YEAR_LOW} to {YEAR_HIGH})")
    return value


def parse_web(text: str, ctx: Mapping[str, Any]) -> Answer:
    """The web answer in its exact shape; every rule it can break on its own. Nothing is fetched."""
    data = A.load_object(text, ANSWER_KEYS)
    if data["site_id"] != ctx["site_id"]:
        raise AnswerError(f"site_id {data['site_id']!r} is not this question's {ctx['site_id']}")
    verdict = data["verdict"]
    if verdict not in VERDICTS:
        raise AnswerError(f"verdict {verdict!r} is not one of {', '.join(VERDICTS)}")
    why = A.text_of(data["why"], "why", max_chars=600)
    quotes = A.quotes_of(data["quotes"], "quotes", minimum=1)
    start, found, kind = data["period_start"], data["found_start"], data["kind"]
    expected = {
        PERIOD_WRONG: "period_start",
        OUT_OF_WINDOW: "found_start",
        NOT_A_SITE: "kind",
        MUSEUM_KEEP: None,
    }[verdict]
    for name, value in (("period_start", start), ("found_start", found), ("kind", kind)):
        if (value is not None) != (name == expected):
            raise AnswerError(
                f"{name} must be "
                + ("set" if name == expected else "null")
                + f" for {verdict}"
                + (f" (only {expected} is set)" if expected else " (all three are null)")
            )
    if verdict == PERIOD_WRONG:
        year = _year(start, "period_start")
        if year > ctx["cutoff"]:
            raise AnswerError(
                f"period_start {year} is past the cutoff {ctx['cutoff']}: a start inside the "
                "window is what PERIOD_WRONG gives (a later one is OUT_OF_WINDOW)"
            )
        start = year
    elif verdict == OUT_OF_WINDOW:
        year = _year(found, "found_start")
        if year <= ctx["cutoff"]:
            raise AnswerError(
                f"found_start {year} is not past the cutoff {ctx['cutoff']}: that site is in the "
                "window (PERIOD_WRONG)"
            )
        found = year
    elif verdict == MUSEUM_KEEP:
        if not ctx["museum_question"]:
            raise AnswerError("MUSEUM_KEEP is for an entry of type Museum")
    else:
        if kind not in KINDS:
            raise AnswerError(f"kind {kind!r} is not one of {list(KINDS)}")
        if len({website(q["url"]) for q in quotes}) < MIN_SITES:
            raise AnswerError(
                f"NOT_A_SITE needs quotes from at least {MIN_SITES} websites "
                "(the Wikimedia projects count as one)"
            )
    return Answer(ctx["site_id"], verdict, why, start, found, kind, quotes)


def cited(answer: Answer, ctx: Mapping[str, Any]) -> set[str]:
    return A.urls_of(answer.quotes)


def decide_web(answer: Answer, ctx: Mapping[str, Any], env: Env) -> Outcome:
    """Every quote found; a NOT_A_SITE still stands on two websites once every quote counts."""
    data: dict[str, Any] = {
        "verdict": answer.verdict,
        "why": answer.why,
        "period_start": answer.period_start,
        "found_start": answer.found_start,
        "kind": answer.kind,
        "quotes": [],
    }
    counted, noted, reason = A.check_quotes(answer.quotes, ctx["site_id"], env.library)
    data["quotes"] = noted
    if not counted:
        return Outcome(HELD, f"quotes: a quote does not count ({reason})", data)
    if answer.verdict == NOT_A_SITE:
        sites = {website(q["url"]) for q in noted if q["outcome"] == "found"}
        if len(sites) < MIN_SITES:
            return Outcome(
                HELD, f"quotes: found on {len(sites)} website(s), {MIN_SITES} needed", data
            )
    return Outcome(DECIDED, "", data)


def web_spec() -> StageSpec:
    return StageSpec(
        lane=LANE,
        stage=WEB,
        role="web_verifier",
        render=render_web,
        parse=parse_web,
        decide=decide_web,
        cited=cited,
        titles=lambda a, c: set(),
        per_batch=5,
        guidance=(
            "The stored date is the thing in doubt: find the site's real dating in a source, and "
            "quote it."
        ),
    )


# -------------------------------------------------------------------------------------- the re-check
def proposal_of(decision: Mapping[str, Any]) -> dict[str, Any]:
    data = decision["data"]
    return {
        "verdict": data["verdict"],
        "why": data["why"],
        "found_start": data["found_start"],
        "kind": data["kind"],
        "quotes": [{"url": q["url"], "quote": q["quote"]} for q in data["quotes"]],
    }


def recheck_questions(
    asked: Sequence[Question], decisions: Mapping[str, Mapping[str, Any]]
) -> list[Question]:
    """The re-check asks every decided web verdict that retires (`RETIRING`), with its proposal."""
    out = []
    for q in asked:
        decision = decisions.get(q.site_id)
        if decision is None or decision["status"] != DECIDED:
            continue
        if decision["data"]["verdict"] not in RETIRING:
            continue
        out.append(Question(q.site_id, {**q.context, "proposal": proposal_of(decision)}))
    return out


def _proposal_text(proposal: Mapping[str, Any]) -> str:
    lines = []
    if proposal["found_start"] is not None:
        lines.append(f"  found_start: {proposal['found_start']}")
    if proposal["kind"]:
        lines.append(f"  kind: {proposal['kind']}")
    lines += [f'  quote: "{q["quote"]}" - {q["url"]}' for q in proposal["quotes"]]
    return "\n".join(lines)


def render_recheck(ctx: Mapping[str, Any], earlier: str | None = None) -> str:
    proposal = ctx["proposal"]
    return RECHECK_TEMPLATE.format(
        exported_at=ctx["exported_at"],
        site_id=ctx["site_id"],
        name=ctx["name"],
        country=ctx["country"],
        lat=ctx["lat"],
        lon=ctx["lon"],
        site_type=ctx["site_type"],
        period=_period(ctx),
        status=ctx["scope_status"] or "none yet",
        source_url=ctx["source_url"],
        qids=", ".join(ctx["qids"]) or "none",
        titles=", ".join(ctx["enwiki"]) or "none",
        description=" ".join(str(ctx["description"] or "(none)").split()),
        cache=cache_section(ctx),
        region=ctx["region"],
        cutoff=ctx["cutoff"],
        date_used=_date_text(ctx),
        origin_note=(
            "it was written by a withdrawn field wave"
            if ctx["recheck_d10"]
            else f"origin {ctx['origin']}"
        ),
        verdict=proposal["verdict"],
        why=proposal["why"],
        proposal=_proposal_text(proposal),
        earlier=earlier_section(earlier),
        question=QUESTIONS[proposal["verdict"]],
    )


@dataclass(frozen=True)
class Review:
    site_id: str
    verdict: str
    why: str
    quotes: tuple[dict[str, str], ...]


def parse_recheck(text: str, ctx: Mapping[str, Any]) -> Review:
    data = A.load_object(text, RECHECK_KEYS)
    if data["site_id"] != ctx["site_id"]:
        raise AnswerError(f"site_id {data['site_id']!r} is not this question's {ctx['site_id']}")
    if data["verdict"] not in (CONFIRM, REJECT):
        raise AnswerError(f"verdict {data['verdict']!r} is not CONFIRM or REJECT")
    why = A.text_of(data["why"], "why", max_chars=600)
    quotes = A.quotes_of(data["quotes"], "quotes", minimum=1 if data["verdict"] == CONFIRM else 0)
    return Review(ctx["site_id"], data["verdict"], why, quotes)


def decide_recheck(review: Review, ctx: Mapping[str, Any], env: Env) -> Outcome:
    counted, noted, reason = A.check_quotes(review.quotes, ctx["site_id"], env.library)
    data = {
        "verdict": review.verdict,
        "why": review.why,
        "proposed": ctx["proposal"]["verdict"],
        "quotes": noted,
    }
    if not counted:
        return Outcome(HELD, f"quotes: a quote does not count ({reason})", data)
    return Outcome(DECIDED, "", data)


def recheck_spec() -> StageSpec:
    return StageSpec(
        lane=LANE,
        stage=RECHECK,
        role="adversarial",
        render=render_recheck,
        parse=parse_recheck,
        decide=decide_recheck,
        cited=lambda r, c: A.urls_of(r.quotes),
        titles=lambda r, c: set(),
        per_batch=5,
        guidance="You are not told the proposal is right. Look for the reason it is wrong.",
    )


# ------------------------------------------------------------------------------------ the result
def final_state(
    web: Mapping[str, Mapping[str, Any]], recheck: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Where every asked site stands: `kept` (PERIOD_WRONG, MUSEUM_KEEP: decided, no re-check),
    `confirmed` (a retiring verdict the re-check confirmed), `rejected`, `waiting-for-recheck` or
    `held` (the web answer is still held after the rounds)."""
    out = []
    for sid, decision in sorted(web.items()):
        if decision["status"] != DECIDED:
            state, verdict = "held", None
        else:
            verdict = decision["data"]["verdict"]
            second = recheck.get(sid)
            if verdict not in RETIRING:
                state = "kept"
            elif second is None or second["status"] != DECIDED:
                state = "waiting-for-recheck"
            elif second["data"]["verdict"] == CONFIRM:
                state = "confirmed"
            else:
                state = "rejected"
        out.append({"site_id": sid, "verdict": verdict, "state": state})
    return out


# ------------------------------------------------------------------------------------ the plan
def live_sql(site_ids: Sequence[str]) -> str:
    """The entries as production holds them now, with the lane's premise. Read-only."""
    ids = ", ".join(f"{sql_literal(s)}::uuid" for s in sorted(site_ids))
    return (
        "SELECT u.id::text AS site_id, u.source_id, u.name, u.site_type, u.country, u.lat, u.lon, "
        "u.period_start, u.period_end, u.scope_status, u.scope_reason, "
        f"{SCOPE_REVIEW_PREMISE_SQL} AS premise FROM unified_sites u WHERE u.id IN ({ids}) "
        "ORDER BY u.id"
    )


#: The fields of an entry the decision judged: a decision about another entry says nothing here.
JUDGED = (
    "name",
    "site_type",
    "country",
    "lat",
    "lon",
    "period_start",
    "period_end",
    "scope_status",
    "scope_reason",
)


@dataclass
class ScopePlan:
    lane: Lane
    changes: list[MP.Verdict] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    period_wrong: list[dict[str, Any]] = field(default_factory=list)

    @property
    def sites(self) -> list[str]:
        return sorted({c.site_id for c in self.changes})


def reason_of(verdict: str, data: Mapping[str, Any], ctx: Mapping[str, Any]) -> str:
    """The `scope_reason` a decision writes: the lane's documented texts."""
    quote = next(q["quote"] for q in data["quotes"] if q["outcome"] == "found")
    if verdict == OUT_OF_WINDOW:
        return f"E3: period_start {data['found_start']} is past the cutoff; {quote}"
    if verdict == NOT_A_SITE:
        return f"{NOT_A_SITE_PREFIX} ({data['kind']}): {data['why']}"
    if verdict == MUSEUM_KEEP:
        return f"E3 museum rule: the museum exhibits ancient material; {quote}"
    if ctx["date_used"] is not None and ctx["date_used"] > ctx["cutoff"]:
        return (
            f"E3: period_start {ctx['date_used']} is past the cutoff, but a source dates the start "
            f"at {data['period_start']}; {quote}"
        )
    return f"E3: kept in scope, a source dates the start at {data['period_start']}; {quote}"


def _cells(
    live: Mapping[str, Any], status: str, reason: str, evidence: Sequence[dict[str, Any]]
) -> list[MP.Verdict]:
    return [
        MP.Verdict(
            site_id=str(live["site_id"]),
            site_name=str(live["name"]),
            ok=True,
            old_value=live[column],
            new_value=value,
            rule="d20-scope-window",
            reason="",
            note=f"{column} {live[column]!r} -> {value!r}",
            phase3=False,
            finding_test_id="D20/scope-window",
            evidence=tuple(evidence),
            premise=str(live["premise"]),
            column=column,
        )
        for column, value in (("scope_status", status), ("scope_reason", reason))
    ]


def build(
    final: Mapping[str, Mapping[str, Any]],
    rechecks: Mapping[str, Mapping[str, Any]],
    asked: Mapping[str, Mapping[str, Any]],
    live: Mapping[str, Mapping[str, Any]],
    wave: str,
) -> ScopePlan:
    """A pure function of the final decisions, the contexts they judged and the live read: the cells
    of every site that can be written, the skips with their reasons, and the corrected starts the
    fields lane is handed. `final` maps a site to its web decision (a site that is not final is not
    passed in)."""
    plan = ScopePlan(scope_window_lane(wave))

    def skip(sid: str, reason: str, note: str) -> None:
        plan.skipped.append(
            {"site_id": sid, "name": asked[sid]["name"], "reason": reason, "note": note}
        )

    for sid in sorted(final):
        decision, ctx = final[sid], asked[sid]
        data = decision["data"]
        verdict = data["verdict"]
        now = live.get(sid)
        if now is None:
            skip(sid, "gone", "the site is no longer in unified_sites")
            continue
        if now["source_id"] != "ancient_nerds":
            skip(sid, "not-curated", f"a {now['source_id']} row")
            continue
        moved = [f"{k}: {ctx[k]!r} -> {now[k]!r}" for k in JUDGED if ctx[k] != now[k]]
        if moved:
            skip(
                sid,
                "entry-moved",
                "the entry the decision judged changed: " + "; ".join(moved) + " - asked again",
            )
            continue
        if now["scope_status"] == RETIRED:
            skip(sid, "already-retired", "retired since the question was asked")
            continue
        if verdict == PERIOD_WRONG and data["period_start"] != ctx["period_start"]:
            plan.period_wrong.append(
                {
                    "site_id": sid,
                    "wave": wave,
                    "name": ctx["name"],
                    "stored_period_start": ctx["period_start"],
                    "stored_period_name": ctx["period_name"],
                    "period_start": data["period_start"],
                    "origin": ctx["origin"],
                    "recheck_d10": ctx["recheck_d10"],
                    "quotes": [q for q in data["quotes"] if q["outcome"] == "found"],
                    "ask": "the WD4 fields lane writes the corrected start with its own gates",
                }
            )
        status = IN_SCOPE if verdict in (PERIOD_WRONG, MUSEUM_KEEP) else RETIRED
        if now["scope_status"] == status:
            skip(sid, "already-decided", f"scope_status is already {status!r}")
            continue
        if verdict in RETIRING:
            second = rechecks.get(sid)
            if second is None or second["data"]["verdict"] != CONFIRM:
                raise MP.PlanError(f"{sid}: a retirement is written only after a CONFIRM")
        evidence = [
            {"source": q["url"], "url": q["url"], "quote": q["quote"]}
            for q in data["quotes"]
            if q["outcome"] == "found"
        ]
        who = decision["answered_by"]
        evidence.append({"source": who, "url": "handoff", "quote": data["why"]})
        if verdict in RETIRING:
            second = rechecks[sid]
            evidence.append(
                {"source": second["answered_by"], "url": "handoff", "quote": second["data"]["why"]}
            )
        plan.changes += _cells(now, status, reason_of(verdict, data, ctx), evidence)
    return plan


def to_plan(plan: ScopePlan, built_at: str) -> MP.Plan:
    sites = plan.sites
    if len(sites) > waves.SITES_PER_WAVE:
        raise MP.PlanError(f"{len(sites)} sites exceed one wave of {waves.SITES_PER_WAVE}")
    counters: dict[str, int] = {"sites": len(sites), "cells": len(plan.changes)}
    for c in plan.changes:
        if c.column == "scope_status":
            key = f"{c.old_value or 'NULL'}->{c.new_value}"
            counters[key] = counters.get(key, 0) + 1
    counters["skipped"] = len(plan.skipped)
    counters["period_wrong_handoffs"] = len(plan.period_wrong)
    return MP.Plan(tuple(plan.changes), (), built_at=built_at, counters=counters, lane=plan.lane)
