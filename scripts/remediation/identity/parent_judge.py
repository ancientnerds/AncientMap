"""D25: the parent question - one per parent - its answer, its adversarial recheck and the decisions
the `parent-<wave>` lanes are planned from.

`parents.py` lists the shown sites whose name contains another shown site's name within 2 km
(`PARENT_CANDIDATES.jsonl`, one record per parent with its children), and the duplicate verdicts
(`dup_judge.py`) add the children they decided `PART_OF`. A candidate is not a component: "Abu
Simbel Small Temple" is part of Abu Simbel, "Temple of Apollo" next to "Apollo" is not. Two Claude
stages decide it (owner decision D6), both through the handoff:

1. **`parent-verdict`** - role `web_verifier` (Sonnet, high). One question per parent, with its
   children; each child gets `PART` (a component of this parent, with a quote: Wikipedia text, or the
   child's Wikidata P361 naming the parent's item), `NOT_PART` (a neighbour, a namesake, a different
   site) or `DUPLICATE` (the same site: D14's). A child that is a candidate of several parents is
   only `PART` of the one that directly contains it.
2. **`parent-recheck`** - role `adversarial` (Opus, high). Every `PART` is asked again with the first
   answer in front of the reader: `CONFIRM` or `REJECT`. Only a confirmed `PART` is decided.

`build_decisions` writes `PARENT_DECISIONS.jsonl`, one record per child: the parent, the distance,
whether the child's Wikidata item names the parent's through P361 (read from the harvest, evidence on
top of the quote), and its status. A child decided `PART` of two parents is a `conflict` and is not
written; a parent or child that a decided MERGE retires is left out of the questions. The
`parent-<wave>` lane's invariants (parent shown, depth one, same country, at most 5 km, no duplicate
loser) are proved again in the transaction and by the planner (`mechanical/parent.py`).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import opus_handoff as OH  # noqa: E402
from fields import harvest as H  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from identity import common, export, rounds  # noqa: E402
from identity.entities import EntityStore  # noqa: E402
from identity.wiki import CACHE_SUBDIR, WikiIndex, article_url  # noqa: E402

STAGE_VERDICT = "parent-verdict"
STAGE_RECHECK = "parent-recheck"
ROLE_VERDICT = "web_verifier"
ROLES_RECHECK = ("adversarial", "pilot_judge")
VERDICTS = ("PART", "NOT_PART", "DUPLICATE")
RECHECK_DECISIONS = ("CONFIRM", "REJECT")
PARENT_DECISIONS = "PARENT_DECISIONS.jsonl"
PARENT_DIR = "parent"
P_PART_OF = "P361"
CHILD_KEYS = frozenset({"site_id", "verdict", "why", "quotes"})
RECHECK_KEYS = frozenset({"site_id", "decision", "why", "quotes"})
AnswerError = rounds.AnswerError
DECIDED, HELD = rounds.DECIDED, rounds.HELD


# ------------------------------------------------------------------------------------ the data
@dataclass(frozen=True)
class Context:
    """What the questions and the import are pure functions of."""

    questions: Mapping[str, Mapping[str, Any]]  # parent id -> {"parent": brief, "children": [...]}
    shown: Mapping[str, Mapping[str, Any]]
    names: Mapping[str, tuple[str, ...]]
    qids: Mapping[str, tuple[str, ...]]
    wiki: WikiIndex | None
    store: EntityStore | None
    basis: str


def parent_run(run: Path) -> Path:
    return run / PARENT_DIR


def _brief(row: Mapping[str, Any], qids: Sequence[str]) -> dict[str, Any]:
    return {
        "id": row["id"], "name": row["name"], "country": row["country"],
        "site_type": row["site_type"], "lat": row["lat"], "lon": row["lon"], "qids": list(qids),
        "images": row["images"], "links": row["links"], "description_lane": row["description_lane"],
        "parent_site_id": row["parent_site_id"],
    }  # fmt: skip


def merge_questions(
    candidates: Sequence[Mapping[str, Any]],
    part_of: Sequence[Mapping[str, Any]],
    shown: Mapping[str, Mapping[str, Any]],
    qids: Mapping[str, Sequence[str]],
    losers: set[str],
) -> dict[str, dict[str, Any]]:
    """The parent questions: the name-contained candidates plus the children D14 decided `PART_OF`,
    without a site a decided MERGE retires and without a child that already names a parent."""
    out: dict[str, dict[str, Any]] = {}
    for record in candidates:
        parent = record["parent"]
        if parent["id"] in losers or parent["id"] not in shown:
            continue
        kids = {
            c["id"]: {**c, "sources": ["name-contained"]}
            for c in record["children"]
            if c["id"] not in losers and c["id"] in shown and c["parent_site_id"] is None
        }
        if kids:
            out[parent["id"]] = {"parent": parent, "children": kids}
    for item in part_of:
        child, parent = item["site_id"], item["target"]
        if child in losers or parent in losers or child not in shown or parent not in shown:
            continue
        if shown[child]["parent_site_id"] is not None:
            continue
        entry = out.setdefault(
            parent, {"parent": _brief(shown[parent], qids.get(parent, ())), "children": {}}
        )
        kid = entry["children"].setdefault(
            child,
            {
                **_brief(shown[child], qids.get(child, ())),
                "metres": round(common.metres(shown[child], shown[parent]), 1),
                "shared_qid": bool(set(qids.get(child, ())) & set(qids.get(parent, ()))),
                "competing_parents": [],
                "sources": [],
            },
        )
        kid["sources"].append("dup-part-of")
    competing: dict[str, set[str]] = defaultdict(set)
    for parent, entry in out.items():
        for child in entry["children"]:
            competing[child].add(parent)
    for parent, entry in out.items():
        for child, kid in entry["children"].items():
            kid["competing_parents"] = sorted(competing[child] - {parent})
        entry["children"] = [entry["children"][c] for c in sorted(entry["children"])]
        entry["parent_is_child"] = parent in competing
    return out


def load_context(
    run: Path, *, root: Path | None = None, store: EntityStore | None = None
) -> Context:
    exported = export.load_export(run / common.EXPORT_FILE)
    shown = common.rows_by_id(exported.shown)
    qids = export.qids_by_site(exported.ext_ids)
    candidates = common.read_jsonl(run / "PARENT_CANDIDATES.jsonl")
    decisions_path = run / "DUP_DECISIONS.jsonl"
    decisions = common.read_jsonl(decisions_path) if decisions_path.exists() else []
    losers = {m["site_id"] for r in decisions for m in r["merges"]}
    part_of = [m for r in decisions for m in r["part_of"]]
    names: dict[str, list[str]] = {}
    for row in exported.names:
        names.setdefault(row["site_id"], []).append(row["name"])
    cache = (root or common.main_checkout()) / CACHE_SUBDIR
    return Context(
        questions=merge_questions(candidates, part_of, shown, qids, losers),
        shown=shown,
        names={k: tuple(sorted(set(v))) for k, v in names.items()},
        qids={k: tuple(v) for k, v in qids.items()},
        wiki=WikiIndex.load(cache) if (cache / "INDEX.jsonl").exists() else None,
        store=store,
        basis=exported.exported_at,
    )


# ------------------------------------------------------------------------------------- prompts
VERDICT_TEMPLATE = """You are a web verifier of the D25 parent question of the Ancient Nerds sites \
remediation (owner decision of 2026-10-08). Below is one curated site record, the PARENT, and {n} \
other records near it whose names contain its name. Decide for each of them whether it is a \
COMPONENT of the parent site. Research on the open web; read the pages you cite.

THE PARENT (data read {read_at})
{parent}
THE CANDIDATE CHILDREN
{children}
WHERE TO READ
Wikipedia articles: each record names its cached article (a local text file, the article as plain \
text). Read the cached file FIRST - Wikimedia throttles this office, so do not fetch Wikipedia pages \
that are cached. Everything else (Wikidata, a museum, a ministry) is fetched live, a few requests, \
one at a time; an HTTP 403 or 429 is a throttle and never a finding. When you cite a Wikipedia \
article, cite its URL (https://en.wikipedia.org/wiki/<Title>) and quote its text.

THE RULES
1. Give EVERY candidate child one verdict:
   - PART - the record is a COMPONENT of the parent site: a temple, gate, tomb, building or sector \
that lies within or forms part of it. Both stay on the map; the child's page says "part of <parent>".
   - NOT_PART - a neighbour, a namesake, a site of its own that merely shares a word, a museum that \
holds finds, the parent's container (the town or park the parent lies in), or a component of a \
DIFFERENT parent (see "also a candidate of").
   - DUPLICATE - the child and the parent are ONE site under two records (the duplicate question \
decides that, not this one).
2. PART needs proof: quote the sentence that says the child is part of / within / a component of the \
parent (an article about either), or the child's Wikidata item with "part of" (P361) naming the \
parent's item (cite https://www.wikidata.org/wiki/Special:EntityData/<QID>.json and quote the text). \
The shared words in the names are no proof.
3. A child that is a candidate of several parents is PART of the one that DIRECTLY contains it, and \
NOT_PART of the others.
4. "quotes": PART and DUPLICATE carry at least one; each is {{"source": "<URL of the page>", "quote": \
"<verbatim text of that page>"}}. The machine fetches every cited URL (a cached Wikipedia article is \
read from the cache) and looks for the quote: verbatim, whitespace may differ. Keep a quote short \
(one clause, about 5 to 25 words), never across a footnote marker, a table cell or a list item. Never \
cite ancientnerds.com.
5. If you cannot PROVE a child is a component with a quote, answer NOT_PART: a wrong parent puts a \
false "part of" line on a page.
{earlier}
ANSWER with only this JSON object (one entry per candidate child):
{{
 "parent_id": "{parent_id}",
 "children": [
  {{"site_id": "<id>", "verdict": "PART | NOT_PART | DUPLICATE", "why": "...", \
"quotes": [{{"source": "https://...", "quote": "..."}}]}}
 ]
}}
"""


def _record_block(m: Mapping[str, Any], ctx: Context, *, extra: str = "") -> str:
    shown = ctx.shown[m["id"]]
    pages = ""
    if ctx.wiki is not None:
        listed = ctx.wiki.site_pages(m["id"])
        pages = (
            "".join(
                f"      cached Wikipedia ({p.lang}): {article_url(p.lang, p.resolved_title or p.title)}"
                f"\n        file: {p.path.as_posix()}\n"
                for p in listed
            )
            or "      cached Wikipedia: none\n"
        )
    aliases = [n for n in ctx.names.get(m["id"], ()) if n != m["name"]]
    return (
        f"  {m['id']}  {m['name']}\n"
        f"      {m['country']}; {m['site_type']}; point {m['lat']}, {m['lon']}\n"
        f"      images {m['images']}, content links {m['links']}, description lane "
        f"{m['description_lane'] or 'none'}\n"
        f"      wikidata: {', '.join(m['qids']) or 'none'}\n"
        + (f"      English names: {'; '.join(aliases[:8])}\n" if aliases else "")
        + pages
        + extra
        + f"      description: {str(shown.get('description') or '(none)')[:300]}\n"
    )


def verdict_prompt(question: Mapping[str, Any], ctx: Context, earlier: str | None = None) -> str:
    """The exact question for one parent. Pure: the question, the shown rows, the names, the cached
    pages and, for a re-ask, why the earlier answer was held."""
    parent = question["parent"]
    names = {c["id"]: c["name"] for c in question["children"]} | {parent["id"]: parent["name"]}
    children = "".join(
        _record_block(
            c,
            ctx,
            extra=(
                f"      {c['metres']:.0f} m from the parent"
                + (", sharing its Wikidata item" if c["shared_qid"] else "")
                + (
                    "; also a candidate of "
                    + ", ".join(
                        f"{names.get(p, ctx.shown[p]['name'])} ({p})"
                        for p in c["competing_parents"]
                    )
                    if c["competing_parents"]
                    else ""
                )
                + "\n"
            ),
        )
        for c in question["children"]
    )
    note = (
        "      NOTE: this record is itself a candidate component of another record.\n"
        if question.get("parent_is_child")
        else ""
    )
    return VERDICT_TEMPLATE.format(
        n=len(question["children"]),
        read_at=ctx.basis,
        parent=_record_block(parent, ctx, extra=note),
        children=children,
        parent_id=parent["id"],
        earlier=(
            ""
            if earlier is None
            else f"\nAN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED\n  {earlier}\n"
        ),
    )


RECHECK_TEMPLATE = """You are the adversarial reader of the D25 parent question of the Ancient \
Nerds sites remediation (owner decision of 2026-10-08). A web verifier answered the question below; \
your job is to try to REFUTE each "PART" it asserts - not to agree with it. A relation you cannot \
refute with your own reading of the sources stands.

THE PARENT (data read {read_at})
{parent}
THE RELATIONS TO CHECK (each with the first answer's quotes and whether the machine found them)
{relations}
{earlier}
WHERE TO READ
Wikipedia articles are cached as local files (listed per record): read the cached file FIRST, never \
fetch a cached Wikipedia page. Everything else is fetched live, a few requests, one at a time; an HTTP \
403 or 429 is a throttle, never a finding.

THE RULES
1. For EVERY relation listed, decide CONFIRM (the child is a component of exactly this parent) or \
REJECT (it is not: a neighbour, a namesake, a museum with finds, the parent's container, a component \
of a different parent, or the same site as the parent).
2. Look first for the reasons the relation is WRONG: a "part of" line on a site's page that is false \
is worse than none.
3. Every decision carries at least one quote: {{"source": "<URL of the page>", "quote": "<verbatim \
text of that page>"}}, found by the machine as in the first answer. Short, verbatim, never across a \
footnote marker; never ancientnerds.com.

ANSWER with only this JSON object (one entry per relation):
{{
 "parent_id": "{parent_id}",
 "children": [
  {{"site_id": "<id of the child>", "decision": "CONFIRM | REJECT", "why": "...", \
"quotes": [{{"source": "https://...", "quote": "..."}}]}}
 ]
}}
"""


def parts_of(decision: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The children a decided verdict calls PART - what the recheck is asked about."""
    return [m for m in decision["members"] if m["verdict"] == "PART"]


def recheck_prompt(
    question: Mapping[str, Any],
    ctx: Context,
    decision: Mapping[str, Any],
    earlier: str | None = None,
) -> str:
    parent = question["parent"]
    relations = "".join(
        f"  PART: {m['name']} ({m['site_id']}) is part of {parent['name']} ({parent['id']})\n"
        f"    why: {m['why']}\n"
        + "".join(
            f"    quote [{outcome}]: {q['source']} - {q['quote']}\n"
            for q, outcome in zip(m["quotes"], m["quote_outcomes"], strict=True)
        )
        for m in parts_of(decision)
    )
    return RECHECK_TEMPLATE.format(
        read_at=ctx.basis,
        parent=_record_block(parent, ctx),
        relations=relations,
        parent_id=parent["id"],
        earlier=(
            ""
            if earlier is None
            else f"\nAN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED\n  {earlier}\n"
        ),
    )


# ------------------------------------------------------------------------------------ the answer
@dataclass(frozen=True)
class Child:
    site_id: str
    verdict: str
    why: str
    quotes: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class Relation:
    site_id: str
    decision: str
    why: str
    quotes: tuple[dict[str, str], ...]


def _object(text: str, parent_id: str) -> list[Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnswerError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"parent_id", "children"}:
        got = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise AnswerError(f"the answer carries {got}, not ['children', 'parent_id']")
    if data["parent_id"] != parent_id:
        raise AnswerError(f"parent_id {data['parent_id']!r} is not this question's {parent_id}")
    if not isinstance(data["children"], list):
        raise AnswerError("children is not a list")
    return data["children"]


def parse_verdict(text: str, question: Mapping[str, Any]) -> dict[str, Child]:
    """The answer to one parent's question, in its exact shape, or `AnswerError`."""
    ids = [c["id"] for c in question["children"]]
    children: dict[str, Child] = {}
    for row in _object(text, question["parent"]["id"]):
        if not isinstance(row, dict) or set(row) != CHILD_KEYS:
            raise AnswerError(f"a child is not an object with exactly {sorted(CHILD_KEYS)}")
        site = row["site_id"]
        if site not in ids:
            raise AnswerError(f"site_id {site!r} is no candidate child of this parent")
        if site in children:
            raise AnswerError(f"{site} is answered twice")
        if row["verdict"] not in VERDICTS:
            raise AnswerError(
                f"{site}: verdict {row['verdict']!r} is not one of {', '.join(VERDICTS)}"
            )
        if not isinstance(row["why"], str) or not row["why"].strip():
            raise AnswerError(f"{site}: why is empty")
        quotes = rounds.parse_quotes(row["quotes"], site)
        if row["verdict"] != "NOT_PART" and not quotes:
            raise AnswerError(f"{site}: a {row['verdict']} needs at least one quote")
        children[site] = Child(site, row["verdict"], row["why"], quotes)
    if set(children) != set(ids):
        raise AnswerError(
            f"every child needs one verdict; missing {sorted(set(ids) - set(children))}"
        )
    return children


def parse_recheck(
    text: str, question: Mapping[str, Any], asked: Mapping[str, Any]
) -> dict[str, Relation]:
    relations: dict[str, Relation] = {}
    for row in _object(text, question["parent"]["id"]):
        if not isinstance(row, dict) or set(row) != RECHECK_KEYS:
            raise AnswerError(f"a relation is not an object with exactly {sorted(RECHECK_KEYS)}")
        site = row["site_id"]
        if site not in asked:
            raise AnswerError(f"{site!r} is no relation this recheck asks")
        if site in relations:
            raise AnswerError(f"{site} is answered twice")
        if row["decision"] not in RECHECK_DECISIONS:
            raise AnswerError(f"{site}: decision {row['decision']!r} is not CONFIRM or REJECT")
        if not isinstance(row["why"], str) or not row["why"].strip():
            raise AnswerError(f"{site}: why is empty")
        quotes = rounds.parse_quotes(row["quotes"], site)
        if not quotes:
            raise AnswerError(f"{site}: a {row['decision']} needs at least one quote")
        relations[site] = Relation(site, row["decision"], row["why"], quotes)
    if set(relations) != set(asked):
        raise AnswerError(
            f"every relation needs one decision; missing {sorted(set(asked) - set(relations))}"
        )
    return relations


# ----------------------------------------------------------------------------------- the machine
def p361_proved(ctx: Context, child_id: str, parent_id: str) -> bool:
    """Whether the child's Wikidata item names the parent's item through P361 (the harvest's items;
    `False` without a store or when either site has no item) - evidence on top of the quote."""
    if ctx.store is None:
        return False
    parents = set(ctx.qids.get(parent_id, ()))
    for qid in ctx.qids.get(child_id, ()):
        entity, _source = ctx.store.get(qid)
        if entity is not None and parents & set(H.item_ids(entity, P_PART_OF)):
            return True
    return False


def _decide(
    label: str,
    items: Mapping[str, Any],
    names: Mapping[str, str],
    library: Q.Library,
    round_name: str,
    answered_by: str,
    extra: Callable[[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    out = []
    for site in sorted(items):
        item = items[site]
        outcomes, failure = rounds.quote_outcomes(item.quotes, f"{label}/{site}", library)
        out.append(
            {
                "site_id": site,
                "name": names[site],
                "why": item.why,
                "quotes": list(item.quotes),
                "quote_outcomes": outcomes,
                "status": HELD if failure else DECIDED,
                "reason": failure or "",
                **extra(site, item),
            }
        )
    held = [m for m in out if m["status"] == HELD]
    return {
        "label": label,
        "parent_id": label,
        "status": HELD if held else DECIDED,
        "reason": "; ".join(f"{m['name']}: {m['reason']}" for m in held),
        "round": round_name,
        "answered_by": answered_by,
        "members": out,
    }


def decide_verdict(
    question: Mapping[str, Any], children: Mapping[str, Child], ctx: Context, *, round_name: str,
    answered_by: str, library: Q.Library,
) -> dict[str, Any]:  # fmt: skip
    parent = question["parent"]
    names = {c["id"]: c["name"] for c in question["children"]}
    metres = {c["id"]: c["metres"] for c in question["children"]}
    return _decide(
        parent["id"], children, names, library, round_name, answered_by,
        lambda site, item: {
            "verdict": item.verdict,
            "metres": metres[site],
            "p361": item.verdict == "PART" and p361_proved(ctx, site, parent["id"]),
        },
    )  # fmt: skip


def decide_recheck(
    question: Mapping[str, Any], relations: Mapping[str, Relation], *, round_name: str,
    answered_by: str, library: Q.Library,
) -> dict[str, Any]:  # fmt: skip
    names = {c["id"]: c["name"] for c in question["children"]}
    return _decide(
        question["parent"]["id"], relations, names, library, round_name, answered_by,
        lambda _site, item: {"decision": item.decision},
    )  # fmt: skip


def build_decisions(
    ctx: Context,
    verdicts: Mapping[str, Mapping[str, Any]],
    rechecks: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """`PARENT_DECISIONS.jsonl`: one record per child some parent's verdict calls PART.

    `decided` needs the verdict decided and the recheck's CONFIRM of the same child, both with
    quotes found; a REJECT or a held recheck holds it; `pending-recheck` waits for the recheck; a
    child decided PART of two parents is a `conflict`. Nothing is guessed."""
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for parent_id in sorted(ctx.questions):
        verdict = verdicts.get(parent_id)
        if verdict is None:
            continue
        recheck = rechecks.get(parent_id)
        asked = {m["site_id"]: m for m in recheck["members"]} if recheck else {}
        parent = ctx.questions[parent_id]["parent"]
        for m in parts_of(verdict):
            second = asked.get(m["site_id"])
            if m["status"] == HELD:
                status, reason = "held", m["reason"]
            elif second is None:
                status, reason = "pending-recheck", ""
            elif second["status"] == HELD:
                status, reason = "held", f"the recheck is held ({second['reason']})"
            elif second["decision"] != "CONFIRM":
                status, reason = "held", f"the recheck REJECTs ({second['why']})"
            else:
                status, reason = "decided", ""
            found[m["site_id"]].append(
                {
                    "child": m["site_id"],
                    "child_name": m["name"],
                    "parent": parent_id,
                    "parent_name": parent["name"],
                    "metres": m["metres"],
                    "p361": m["p361"],
                    "status": status,
                    "reason": reason,
                    "why": m["why"],
                    "recheck_why": second["why"] if second else None,
                    "quotes": m["quotes"] + (second["quotes"] if second else []),
                }
            )
    records = []
    for child in sorted(found):
        claims = found[child]
        decided = [c for c in claims if c["status"] == "decided"]
        if len(decided) > 1:
            parents = ", ".join(c["parent_name"] for c in decided)
            records.append({**decided[0], "status": "conflict", "reason": f"PART of {parents}"})
        else:
            records.append(claims[0] if len(claims) == 1 else (decided or claims)[0])
    return records


# ------------------------------------------------------------------------------ the rounds' glue
def load_decisions(run: Path, stage: str) -> dict[str, dict[str, Any]]:
    return rounds.load_decisions(parent_run(run), stage)


def _prompt_of(
    stage: str, ctx: Context, verdicts: Mapping[str, Mapping[str, Any]] | None = None
) -> Callable[[str, str | None], str]:
    def build(label: str, earlier: str | None) -> str:
        question = ctx.questions[label]
        if stage == STAGE_VERDICT:
            return verdict_prompt(question, ctx, earlier)
        assert verdicts is not None
        return recheck_prompt(question, ctx, verdicts[label], earlier)

    return build


def export_verdicts(
    run: Path, ctx: Context, handoff: Path, *, now: Callable[[], str] = rounds.now_utc
) -> rounds.Round:
    labels, earlier = rounds.labels_for_round(parent_run(run), STAGE_VERDICT, sorted(ctx.questions))
    return rounds.export_round(
        parent_run(run), STAGE_VERDICT, labels, _prompt_of(STAGE_VERDICT, ctx), handoff,
        basis=ctx.basis, earlier=earlier, now=now,
    )  # fmt: skip


def export_rechecks(
    run: Path, ctx: Context, handoff: Path, *, now: Callable[[], str] = rounds.now_utc
) -> rounds.Round:
    verdicts = load_decisions(run, STAGE_VERDICT)
    first = [c for c, d in verdicts.items() if d["status"] == DECIDED and parts_of(d)]
    if not first and not rounds.load_rounds(parent_run(run), STAGE_RECHECK):
        raise rounds.RoundError("no parent has a decided PART to recheck")
    labels, earlier = rounds.labels_for_round(parent_run(run), STAGE_RECHECK, first)
    return rounds.export_round(
        parent_run(run), STAGE_RECHECK, labels, _prompt_of(STAGE_RECHECK, ctx, verdicts), handoff,
        basis=ctx.basis, earlier=earlier, now=now,
    )  # fmt: skip


def import_round(
    run: Path, stage: str, round_name: str, ctx: Context, fetch: rounds.Fetch, *,
    now: Callable[[], str] = rounds.now_utc, root: Path | None = None,
) -> dict[str, Any]:  # fmt: skip
    verdicts = load_decisions(run, STAGE_VERDICT)

    def parse(label: str, text: str) -> Any:
        question = ctx.questions[label]
        if stage == STAGE_VERDICT:
            return parse_verdict(text, question)
        return parse_recheck(text, question, {m["site_id"]: m for m in parts_of(verdicts[label])})

    def decide(
        label: str, items: Any, round_name: str, by: str, library: Q.Library
    ) -> dict[str, Any]:
        question = ctx.questions[label]
        if stage == STAGE_VERDICT:
            return decide_verdict(
                question, items, ctx, round_name=round_name, answered_by=by, library=library
            )
        return decide_recheck(
            question, items, round_name=round_name, answered_by=by, library=library
        )

    return rounds.import_stage(
        parent_run(run), stage, round_name,
        prompt_of=_prompt_of(stage, ctx, verdicts if stage == STAGE_RECHECK else None),
        allowed_roles=(ROLE_VERDICT,) if stage == STAGE_VERDICT else ROLES_RECHECK,
        parse=parse, decide=decide, wiki=ctx.wiki, fetch=fetch, now=now, root=root, repo=REPO,
    )  # fmt: skip


def write_decisions(run: Path, ctx: Context) -> dict[str, Any]:
    records = build_decisions(
        ctx, load_decisions(run, STAGE_VERDICT), load_decisions(run, STAGE_RECHECK)
    )
    common.write_jsonl(run / PARENT_DECISIONS, records)
    counts: dict[str, int] = defaultdict(int)
    for r in records:
        counts[r["status"]] += 1
    return {"children": len(records), **dict(counts)}


BRIEF = """You are agent {batch} of the D25 parent question of the Ancient Nerds sites remediation \
(stage {stage}, round {round}), role {role}. You answer {count} question(s), each about one parent \
site record and its candidate children. Answer each one on its own.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per question \
with its "label" (the parent id) and its "prompt_path" (relative to {handoff}), plus the cached \
Wikipedia files and the web pages your prompt names. Open no other file of the repository, no database, \
no git history. Fetch live at most a few requests, one at a time; an HTTP 403 or 429 is a throttle, \
never a finding.

For each question:
1. Read {handoff}/<prompt_path>.
2. Decide exactly as the prompt's rules say.
3. Write only the JSON object the prompt specifies to a new UTF-8 file of your own:
   {scratch}/<label>.json
4. Check its shape (nothing is fetched, your verdict is not judged):
   {python} {run_tool} check-answer --stage {stage} --round {round} --label <label> \\
--text-file {scratch}/<label>.json
   It prints the problem, if any: fix the shape, never the finding.
5. Record it - an answer is written once:
   {python} {handoff_tool} answer --dir {handoff} --batch-id {batch} --stage {stage} \\
--label <label> --answered-by {batch} --model {model} --role {role} --text-file {scratch}/<label>.json

When every question of the batch is recorded, report how many answers you recorded.
"""


def brief(
    run: Path,
    stage: str,
    round_name: str,
    batch_id: str,
    *,
    stage_run: Path | None = None,
    check: bool = True,
) -> str:
    import roles as RO

    record = rounds.find_round(stage_run or parent_run(run), stage, round_name)
    if batch_id not in record.batches:
        raise rounds.RoundError(f"{batch_id} is no batch of {stage} round {round_name}")
    role = ROLE_VERDICT if stage == STAGE_VERDICT else ROLES_RECHECK[0]
    text = BRIEF.format(
        batch=batch_id, stage=stage, round=round_name, role=role, model=RO.role(role).model,
        count=len(record.batches[batch_id]), handoff=record.handoff,
        scratch=f"{record.handoff}-scratch/{batch_id}", python="./.venv/Scripts/python.exe",
        run_tool="scripts/remediation/identity/parent_judge.py",
        handoff_tool="scripts/remediation/opus_handoff.py",
    )  # fmt: skip
    return text if check else _without_check(text)


def _without_check(text: str) -> str:
    """The brief of a calibration copy: it has no run to check an answer's shape against, so step 4
    is dropped and step 5 becomes step 4."""
    head, _, rest = text.partition("4. Check its shape")
    _, _, tail = rest.partition("5. Record it")
    return head + "4. Record it" + tail


def check_answer(
    run: Path, ctx: Context, stage: str, round_name: str, label: str, text: str
) -> str | None:
    record = rounds.find_round(parent_run(run), stage, round_name)
    if label not in record.labels:
        raise rounds.RoundError(f"{label} is no question of {stage} round {round_name}")
    question = ctx.questions[label]
    try:
        if stage == STAGE_VERDICT:
            parse_verdict(text, question)
        else:
            parse_recheck(
                text,
                question,
                {m["site_id"]: m for m in parts_of(load_decisions(run, STAGE_VERDICT)[label])},
            )
    except AnswerError as exc:
        return str(exc)
    return None


def _fetch_live(urls: list[str], pages: Path) -> dict[str, int]:
    http = Q.http_client()
    try:
        return Q.collect(urls, pages, http, now=rounds.now_utc)
    finally:
        http.close()


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description="D25 parent verdicts, rechecks and decisions.")
    ap.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    sub = ap.add_subparsers(dest="command", required=True)
    stages = (STAGE_VERDICT, STAGE_RECHECK)
    exp = sub.add_parser("export")
    exp.add_argument("--stage", choices=stages, required=True)
    exp.add_argument("--handoff", type=Path, required=True, help="a new directory")
    imp = sub.add_parser("import")
    imp.add_argument("--stage", choices=stages, required=True)
    imp.add_argument("--round", required=True)
    brief_cmd = sub.add_parser("brief")
    brief_cmd.add_argument("--stage", choices=stages, required=True)
    brief_cmd.add_argument("--round", required=True)
    brief_cmd.add_argument("--batch-id", required=True)
    check = sub.add_parser("check-answer")
    check.add_argument("--stage", choices=stages, required=True)
    check.add_argument("--round", required=True)
    check.add_argument("--label", required=True)
    check.add_argument("--text-file", type=Path, required=True)
    sub.add_parser("decisions", help="build PARENT_DECISIONS.jsonl from the imported rounds")
    args = ap.parse_args(argv)
    run = common.run_dir(args.root)
    try:
        from identity.entities import default_store

        ctx = load_context(run, root=args.root, store=default_store(args.root))
        if args.command == "export":
            fn = export_verdicts if args.stage == STAGE_VERDICT else export_rechecks
            record = fn(run, ctx, args.handoff)
            print(
                json.dumps(
                    {
                        "round": record.name,
                        "batches": {b: len(v) for b, v in record.batches.items()},
                    },
                    indent=1,
                )
            )
        elif args.command == "import":
            print(
                json.dumps(
                    import_round(run, args.stage, args.round, ctx, _fetch_live),
                    indent=1,
                    sort_keys=True,
                )
            )
        elif args.command == "brief":
            print(brief(run, args.stage, args.round, args.batch_id))
        elif args.command == "check-answer":
            problem = check_answer(
                run,
                ctx,
                args.stage,
                args.round,
                args.label,
                args.text_file.read_text(encoding="utf-8"),
            )
            print(problem or "shape ok")
            return 1 if problem else 0
        else:
            print(json.dumps(write_decisions(run, ctx), indent=1, sort_keys=True))
    except (rounds.RoundError, OH.HandoffError, common.IdentityError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
