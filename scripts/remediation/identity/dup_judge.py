"""D14: the duplicate question - one per cluster - its answer, its adversarial recheck, and the
decisions the merge lanes are planned from.

`dup_clusters.py` lists the shown sites that may be one site (`DUP_CLUSTERS.jsonl`). A cluster is
not a verdict: a shared item is sometimes a class or a container (Abu Simbel, Aspendos, Kilmartin)
and sometimes the wrong item. Two model stages decide it, both Claude, both through the handoff
(`opus_handoff.py answer --role`, owner decision D6):

1. **`dup-verdict`** - role `web_verifier` (Sonnet, high). One question per cluster, five clusters per
   agent. Each *member* gets one verdict:

   * `DISTINCT` - an own site; nothing happens (a survivor and a parent are DISTINCT);
   * `MERGE` + `survivor` - the same site as the survivor: it is retired and its images and links
     move (`mechanical/dup_merge.py`, lanes `dup-merge-move-<wave>` and `dup-merge-retire-<wave>`);
   * `PART_OF` + `parent` - a component of the parent: both stay, the child names its parent (D25);
   * `WRONG_ID` - its shared item or article names something else; repaired through `qid_repair`,
     nothing is merged here.

   MERGE, PART_OF and WRONG_ID carry verbatim quotes of cited pages, which the machine finds
   (`opus_audit/quotes.py`; a cited Wikipedia article is read from the shared cache when it holds
   it). The survivor is chosen by the agent on the facts - the English name, the Wikipedia-based
   text, the images and links, the item - never by `scope.survivor_rank` alone.

2. **`dup-recheck`** - role `adversarial` (Opus, high; `pilot_judge` for the first ten clusters).
   Every MERGE and PART_OF member is asked again with the first answer in front of the reader:
   `CONFIRM` (the same target), `RETARGET` (the same kind of relation, another survivor or parent)
   or `REJECT` (neither). Only a CONFIRMed relation is decided.

`build_decisions` merges both into `DUP_DECISIONS.jsonl`, one record per cluster, plus one per
already-retired loser that still holds images or links (no model: the survivor is the one its
`scope_reason` names). A MERGE further apart than `DEFAULT_METRES` is held unless
`OVERRIDES.json` gives its loser a limit with a quote (per-pair override, evidence required).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (REPO, REPO / "scripts" / "remediation"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import opus_handoff as OH  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from identity import common, export, rounds  # noqa: E402
from identity.wiki import WikiIndex, article_url, load_cache  # noqa: E402

STAGE_VERDICT = "dup-verdict"
STAGE_RECHECK = "dup-recheck"
ROLE_VERDICT = "web_verifier"
#: The recheck is the adversarial Opus's; the pilot judge (Opus xhigh) reads the first ten clusters.
ROLES_RECHECK = ("adversarial", "pilot_judge")
VERDICTS = ("DISTINCT", "MERGE", "PART_OF", "WRONG_ID")
RECHECK_DECISIONS = ("CONFIRM", "RETARGET", "REJECT")
#: The default distance a survivor may be at, `lane.DUP_RETIRE_METRES`, the owner-case list's cap.
DEFAULT_METRES = 2000
DUP_DECISIONS = "DUP_DECISIONS.jsonl"
OVERRIDES_FILE = "OVERRIDES.json"
DUP_DIR = "dup"
MEMBER_KEYS = frozenset({"site_id", "verdict", "survivor", "parent", "why", "quotes"})
RECHECK_KEYS = frozenset({"site_id", "decision", "target", "why", "quotes"})


AnswerError = rounds.AnswerError
DECIDED, HELD = rounds.DECIDED, rounds.HELD


# ------------------------------------------------------------------------------------ the data
@dataclass(frozen=True)
class Context:
    """What the questions and the import are pure functions of: the clusters, the shown rows, the
    English names, the cached Wikipedia pages and the export's clock."""

    clusters: Mapping[str, Mapping[str, Any]]
    retired_losers: tuple[Mapping[str, Any], ...]
    shown: Mapping[str, Mapping[str, Any]]
    names: Mapping[str, tuple[str, ...]]
    wiki: WikiIndex | None
    basis: str


def dup_run(run: Path) -> Path:
    return run / DUP_DIR


def load_context(run: Path, wiki: WikiIndex | None = None, *, root: Path | None = None) -> Context:
    """The context of a run: `DUP_CLUSTERS.jsonl` and `EXPORT.jsonl` of the identity run
    directory, and the shared Wikipedia cache (`wiki`, or the main checkout's, which must exist)."""
    exported = export.load_export(run / common.EXPORT_FILE)
    records = common.read_jsonl(run / "DUP_CLUSTERS.jsonl")
    clusters = {r["cluster_id"]: r for r in records if r["record"] == "cluster"}
    losers = tuple(r for r in records if r["record"] == "retired_loser")
    names: dict[str, list[str]] = {}
    for row in exported.names:
        names.setdefault(row["site_id"], []).append(row["name"])
    if wiki is None:
        wiki = load_cache(root)
    return Context(
        clusters=clusters,
        retired_losers=losers,
        shown=common.rows_by_id(exported.shown),
        names={k: tuple(sorted(set(v))) for k, v in names.items()},
        wiki=wiki,
        basis=exported.exported_at,
    )


def _members(ctx: Context, cluster: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for m in cluster["members"]:
        shown = ctx.shown[m["id"]]
        out.append({**m, "description": shown["description"], "period": shown["period_name"]})
    return out


def metres_between(cluster: Mapping[str, Any]) -> dict[tuple[str, str], float]:
    """Great-circle metres of every pair of members, keyed by the sorted pair of ids."""
    rows = {m["id"]: m for m in cluster["members"]}
    return {
        tuple(sorted((a, b))): common.metres(rows[a], rows[b])  # type: ignore[misc]
        for a, b in combinations(sorted(rows), 2)
    }


# ------------------------------------------------------------------------------------- prompts
VERDICT_TEMPLATE = """You are a web verifier of the D14 duplicate question of the Ancient Nerds \
sites remediation (owner decision of 2026-10-08). Below are {n} curated site records of the map that \
may be ONE site under several records. Decide, for each record, whether it is a duplicate, a part of \
another, a record with a wrong link, or an own site. Research on the open web; read the pages you cite.

THE CLUSTER {cluster_id} (data read {read_at})
{members}
DISTANCES BETWEEN THE RECORDS (metres)
{distances}
WHY THESE RECORDS ARE ASKED TOGETHER
{why}
{earlier}
WHERE TO READ
Wikipedia articles: each record above names its cached article (a local text file, the article as \
plain text). Read the cached file FIRST - Wikimedia throttles this office, so do not fetch Wikipedia \
pages that are cached. Every other source (Wikidata, a museum, a ministry, a journal) is fetched live: \
at most a few requests, one at a time; an HTTP 403 or 429 is a throttle and never a finding. When you \
cite a Wikipedia article, cite its URL (https://en.wikipedia.org/wiki/<Title>) and quote its text.

THE RULES
1. Give EVERY record above exactly one verdict:
   - DISTINCT - an own site: no other record here is the same site, and it is not a component of \
another. Nothing happens to it. The record that other records MERGE into, and the record they are \
PART_OF, are DISTINCT themselves.
   - MERGE with "survivor" - this record and the survivor are ONE site: the same monument, \
excavation, city or building at the same place, kept twice under two names (an ancient and a modern \
name, a translation, a spelling, a name and its alias). The record that is merged away is retired and \
its images and links move to the survivor.
   - PART_OF with "parent" - this record is a COMPONENT (a temple, gate, tomb, sector, building) of \
the larger site that the parent record is. Both stay on the map; the child names its parent.
   - WRONG_ID - the Wikidata item or Wikipedia article this record carries does not name this record \
(it names a type, a container such as the town or the park, a namesake or another site). Nothing is \
merged for it here; its link is repaired elsewhere.
2. A shared Wikidata item or article is NO proof that two records are one site: it is often the item \
of the larger site, of a type, or of the wrong place. Prove identity: quote the sentence that says \
the two names are names of one site ("X, also known as Y", "the modern name of ..."), or that puts both \
records' points at one place. Prove a component: quote the sentence that says the child is part of / \
within / a component of the parent (or Wikidata P361 on the child's item).
3. Choose the SURVIVOR on the facts, as an editor of the map would: (a) the name the site is commonly \
called in English; (b) the better text (description lane W or S is a Wikipedia-based text, L the legacy \
one; longer is not better by itself); (c) more images and more content links; (d) the record whose \
item or article is the site's own. The older creation date breaks a tie and decides nothing else - \
do NOT pick the survivor by age or by count alone.
4. A survivor or a parent is itself a DISTINCT record. No chain (A into B into C): name the final \
survivor. Two records of different countries may still be one site (a border site): decide on the \
evidence.
5. A MERGE of records more than 2,000 m apart is held for the owner's decision whatever you answer; \
say the distance and the reason in "why".
6. "quotes": MERGE, PART_OF and WRONG_ID carry at least one; each is {{"source": "<URL of the page>", \
"quote": "<verbatim text of that page>"}}. The machine fetches every cited URL (a cached Wikipedia \
article is read from the cache) and looks for the quote: verbatim, whitespace may differ. Keep a \
quote short (one clause, about 5 to 25 words), never across a footnote marker, a table cell or a \
list item. Cite the page you quote, never a search page, never ancientnerds.com.
7. If you cannot PROVE two records are one site with quotes, answer DISTINCT: an unproven merge \
retires a real site (its page answers a redirect) and moves its pictures, which is worse than two \
records.

ANSWER with only this JSON object (one entry per record, in any order):
{{
 "cluster_id": "{cluster_id}",
 "members": [
  {{"site_id": "<id>", "verdict": "DISTINCT | MERGE | PART_OF | WRONG_ID", "survivor": null or "<id of \
the record it merges into>", "parent": null or "<id of the record it is part of>", "why": "...", \
"quotes": [{{"source": "https://...", "quote": "..."}}]}}
 ]
}}
"survivor" goes with MERGE and only with it, "parent" with PART_OF and only with it.
"""


def _member_block(index: int, m: Mapping[str, Any], ctx: Context) -> str:
    wiki_lines = ""
    if ctx.wiki is not None:
        pages = ctx.wiki.site_pages(m["id"])
        wiki_lines = (
            "".join(
                f"      cached Wikipedia ({p.lang}): {article_url(p.lang, p.resolved_title or p.title)}"
                f"\n        file: {p.path.as_posix()}\n"
                for p in pages
            )
            or "      cached Wikipedia: none\n"
        )
    aliases = [n for n in ctx.names.get(m["id"], ()) if n != m["name"]]
    description = str(m.get("description") or "(none)").replace("\n", " ")
    return (
        f"  [{index}] {m['id']}  {m['name']}\n"
        f"      {m['country']}; {m['site_type']}; point {m['lat']}, {m['lon']}; created "
        f"{m['created_at']}\n"
        f"      images {m['images']}, content links {m['links']}, description lane "
        f"{m['description_lane'] or 'none'} ({m['description_chars']} characters), "
        f"card {'yes' if m['has_card'] else 'no'}\n"
        f"      wikidata: {', '.join(m['qids']) or 'none'}; enwiki: "
        f"{', '.join(m['enwiki']) or 'none'}\n"
        + (f"      English names: {'; '.join(aliases[:8])}\n" if aliases else "")
        + wiki_lines
        + f"      description: {description}\n"
    )


def _why(cluster: Mapping[str, Any], names: Mapping[str, str]) -> str:
    """The edges that put the cluster together, in words - never the owner-case class (DUP, PART-OF),
    a heuristic that would anchor the reading."""
    lines = []
    for edge in cluster["edges"]:
        sites = ", ".join(names[s] for s in edge["sites"])
        if edge["kind"] == "shared_qid":
            lines.append(f"  - the records ({sites}) carry the same Wikidata item {edge['qid']}")
        elif edge["kind"] == "shared_enwiki":
            lines.append(f"  - the records ({sites}) carry the same article {edge['title']!r}")
        elif edge["kind"] == "name_point":
            lines.append(
                f"  - {sites}: {edge['metres']:.0f} m apart with similar names "
                f"(similarity {edge['similarity']})"
            )
        else:
            lines.append(
                f"  - {sites}: flagged by an earlier owner-case list ({edge['metres']:.0f} m)"
            )
    return "\n".join(sorted(set(lines)))


def verdict_prompt(cluster: Mapping[str, Any], ctx: Context, earlier: str | None = None) -> str:
    """The exact question for one cluster. Pure: the cluster record, the shown rows, the English
    names, the cached pages and, for a re-ask, why the earlier answer was held."""
    members = _members(ctx, cluster)
    labels = {m["id"]: m["name"] for m in members}
    distances = metres_between(cluster)
    return VERDICT_TEMPLATE.format(
        n=len(members),
        cluster_id=cluster["cluster_id"],
        read_at=ctx.basis,
        members="".join(_member_block(i + 1, m, ctx) for i, m in enumerate(members)),
        distances="\n".join(
            f"  {labels[a]} ({a[:8]}) - {labels[b]} ({b[:8]}): {m:.0f}"
            for (a, b), m in sorted(distances.items())
        ),
        why=_why(cluster, labels),
        earlier=(
            ""
            if earlier is None
            else f"\nAN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED\n  {earlier}\n"
        ),
    )


RECHECK_TEMPLATE = """You are the adversarial reader of the D14 duplicate question of the Ancient \
Nerds sites remediation (owner decision of 2026-10-08). A web verifier answered the question below; \
your job is to try to REFUTE each relation it asserts - not to agree with it. A relation that you \
cannot refute with your own reading of the sources stands.

THE CLUSTER {cluster_id} (data read {read_at})
{members}
DISTANCES BETWEEN THE RECORDS (metres)
{distances}

THE FIRST ANSWER'S RELATIONS (each with its quotes and whether the machine found them)
{relations}
{earlier}
WHERE TO READ
Wikipedia articles are cached as local files (listed per record above): read the cached file FIRST, \
never fetch a cached Wikipedia page. Everything else is fetched live, a few requests, one at a time; \
an HTTP 403 or 429 is a throttle, never a finding.

THE RULES
1. For EVERY relation listed above, decide:
   - CONFIRM - the relation is right, with the same target (the same survivor for a MERGE, the same \
parent for a PART_OF);
   - RETARGET - the relation is right but the target is wrong: another record of the cluster is the \
better survivor (the common English name, the better text, the images and links, the record whose item \
is the site's own - NOT the older record by default) or the real parent; name it in "target";
   - REJECT - the two records are not one site (for a MERGE) / the child is not a component of that \
parent (for a PART_OF): they are neighbours, a type and its instance, a site and its museum, a namesake.
2. Look for the reasons a merge is WRONG before you look for the reasons it is right: two buildings of \
one complex, a modern town and its ancient site, a site and the museum that holds its finds, two \
namesakes in one country. A merge retires a real page and moves its pictures.
3. "quotes": CONFIRM, RETARGET and REJECT each carry at least one: {{"source": "<URL of the page>", \
"quote": "<verbatim text of that page>"}}, found by the machine as in the first answer (a cached \
Wikipedia article from the cache). Short, verbatim, never across a footnote marker; never \
ancientnerds.com.
4. "target" is the survivor id (MERGE) or the parent id (PART_OF) you stand behind; for CONFIRM it is \
the first answer's, for REJECT it is null.

ANSWER with only this JSON object (one entry per relation above):
{{
 "cluster_id": "{cluster_id}",
 "members": [
  {{"site_id": "<id of the record the relation is about>", "decision": "CONFIRM | RETARGET | REJECT", \
"target": null or "<id>", "why": "...", "quotes": [{{"source": "https://...", "quote": "..."}}]}}
 ]
}}
"""


def relations_of(decision: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The MERGE and PART_OF members of a decided verdict - what the recheck is asked about."""
    return [m for m in decision["members"] if m["verdict"] in ("MERGE", "PART_OF")]


def recheck_prompt(
    cluster: Mapping[str, Any],
    ctx: Context,
    decision: Mapping[str, Any],
    earlier: str | None = None,
) -> str:
    """The recheck of one cluster, shown the first answer's relations. Pure."""
    members = _members(ctx, cluster)
    labels = {m["id"]: m["name"] for m in members}
    distances = metres_between(cluster)
    relations = []
    for m in relations_of(decision):
        target = m["survivor"] if m["verdict"] == "MERGE" else m["parent"]
        relations.append(
            f"  {m['verdict']}: {labels[m['site_id']]} ({m['site_id']}) "
            f"{'into' if m['verdict'] == 'MERGE' else 'is part of'} {labels[target]} ({target})\n"
            f"    why: {m['why']}\n"
            + "".join(
                f"    quote [{outcome}]: {q['source']} - {q['quote']}\n"
                for q, outcome in zip(m["quotes"], m["quote_outcomes"], strict=True)
            )
        )
    return RECHECK_TEMPLATE.format(
        cluster_id=cluster["cluster_id"],
        read_at=ctx.basis,
        members="".join(_member_block(i + 1, m, ctx) for i, m in enumerate(members)),
        distances="\n".join(
            f"  {labels[a]} ({a[:8]}) - {labels[b]} ({b[:8]}): {m:.0f}"
            for (a, b), m in sorted(distances.items())
        ),
        relations="".join(relations),
        earlier=(
            ""
            if earlier is None
            else f"\nAN EARLIER ANSWER TO THIS QUESTION WAS NOT COUNTED\n  {earlier}\n"
        ),
    )


# ------------------------------------------------------------------------------------ the answer
@dataclass(frozen=True)
class Member:
    site_id: str
    verdict: str
    survivor: str | None
    parent: str | None
    why: str
    quotes: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class Relation:
    site_id: str
    decision: str
    target: str | None
    why: str
    quotes: tuple[dict[str, str], ...]


def _id_or_none(value: Any, ids: Iterable[str], where: str) -> str | None:
    if value is None:
        return None
    if value not in set(ids):
        raise AnswerError(f"{where}: {value!r} is no record of this cluster")
    return str(value)


def _object(text: str, cluster_id: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AnswerError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict) or set(data) != {"cluster_id", "members"}:
        got = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise AnswerError(f"the answer carries {got}, not ['cluster_id', 'members']")
    if data["cluster_id"] != cluster_id:
        raise AnswerError(f"cluster_id {data['cluster_id']!r} is not this question's {cluster_id}")
    if not isinstance(data["members"], list):
        raise AnswerError("members is not a list")
    return data


def parse_verdict(text: str, cluster: Mapping[str, Any]) -> dict[str, Member]:
    """The answer to one cluster's question, in its exact shape, or `AnswerError`. Nothing fetched."""
    ids = [m["id"] for m in cluster["members"]]
    data = _object(text, cluster["cluster_id"])
    members: dict[str, Member] = {}
    for row in data["members"]:
        if not isinstance(row, dict) or set(row) != MEMBER_KEYS:
            raise AnswerError(f"a member is not an object with exactly {sorted(MEMBER_KEYS)}")
        site = row["site_id"]
        if site not in ids:
            raise AnswerError(f"site_id {site!r} is no record of this cluster")
        if site in members:
            raise AnswerError(f"{site} is answered twice")
        verdict = row["verdict"]
        if verdict not in VERDICTS:
            raise AnswerError(f"{site}: verdict {verdict!r} is not one of {', '.join(VERDICTS)}")
        survivor = _id_or_none(row["survivor"], ids, f"{site} survivor")
        parent = _id_or_none(row["parent"], ids, f"{site} parent")
        if (survivor is None) == (verdict == "MERGE"):
            raise AnswerError(f"{site}: a survivor goes with MERGE and only with it")
        if (parent is None) == (verdict == "PART_OF"):
            raise AnswerError(f"{site}: a parent goes with PART_OF and only with it")
        if site in (survivor, parent):
            raise AnswerError(f"{site}: a record is not its own survivor or parent")
        if not isinstance(row["why"], str) or not row["why"].strip():
            raise AnswerError(f"{site}: why is empty")
        quotes = rounds.parse_quotes(row["quotes"], site)
        if verdict != "DISTINCT" and not quotes:
            raise AnswerError(f"{site}: a {verdict} needs at least one quote")
        members[site] = Member(site, verdict, survivor, parent, row["why"], quotes)
    if set(members) != set(ids):
        raise AnswerError(
            f"every record needs exactly one verdict; missing {sorted(set(ids) - set(members))}"
        )
    for m in members.values():
        target = m.survivor or m.parent
        if target is not None and members[target].verdict != "DISTINCT":
            raise AnswerError(
                f"{m.site_id}: its {'survivor' if m.survivor else 'parent'} {target} is itself "
                f"{members[target].verdict} - a chain; name the final record (it is DISTINCT)"
            )
    return members


def parse_recheck(
    text: str, cluster: Mapping[str, Any], asked: Mapping[str, Mapping[str, Any]]
) -> dict[str, Relation]:
    """The recheck of one cluster; `asked` maps each relation's member to the first answer's member."""
    ids = [m["id"] for m in cluster["members"]]
    data = _object(text, cluster["cluster_id"])
    relations: dict[str, Relation] = {}
    for row in data["members"]:
        if not isinstance(row, dict) or set(row) != RECHECK_KEYS:
            raise AnswerError(f"a relation is not an object with exactly {sorted(RECHECK_KEYS)}")
        site = row["site_id"]
        if site not in asked:
            raise AnswerError(f"{site!r} is no relation this recheck asks")
        if site in relations:
            raise AnswerError(f"{site} is answered twice")
        decision = row["decision"]
        if decision not in RECHECK_DECISIONS:
            raise AnswerError(
                f"{site}: decision {decision!r} is not one of {', '.join(RECHECK_DECISIONS)}"
            )
        target = _id_or_none(row["target"], ids, f"{site} target")
        if (target is None) == (decision != "REJECT"):
            raise AnswerError(
                f"{site}: a target goes with CONFIRM and RETARGET and not with REJECT"
            )
        first = asked[site]
        first_target = first["survivor"] if first["verdict"] == "MERGE" else first["parent"]
        if decision == "CONFIRM" and target != first_target:
            raise AnswerError(f"{site}: CONFIRM names the first answer's target {first_target}")
        if decision == "RETARGET" and target in (first_target, site):
            raise AnswerError(
                f"{site}: RETARGET names another record than {first_target} and itself"
            )
        if not isinstance(row["why"], str) or not row["why"].strip():
            raise AnswerError(f"{site}: why is empty")
        quotes = rounds.parse_quotes(row["quotes"], site)
        if not quotes:
            raise AnswerError(f"{site}: a {decision} needs at least one quote")
        relations[site] = Relation(site, decision, target, row["why"], quotes)
    if set(relations) != set(asked):
        raise AnswerError(
            f"every relation needs one decision; missing {sorted(set(asked) - set(relations))}"
        )
    return relations


# ----------------------------------------------------------------------------------- the machine
def _overrides(run: Path) -> dict[str, dict[str, Any]]:
    path = dup_run(run) / OVERRIDES_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def decide_verdict(
    cluster: Mapping[str, Any],
    members: Mapping[str, Member],
    *,
    round_name: str,
    answered_by: str,
    library: Q.Library,
    overrides: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Every machine check of one parsed verdict; each member is decided or held with its reason.

    The cluster is `decided` only when every member is: a re-ask asks the whole cluster again."""
    names = {m["id"]: m["name"] for m in cluster["members"]}
    distance = metres_between(cluster)
    out_members = []
    for site in sorted(members):
        m = members[site]
        outcomes, failure = rounds.quote_outcomes(
            m.quotes, f"{cluster['cluster_id']}/{site}", library
        )
        metres = None
        reason = failure
        metres_limit, limit_evidence = DEFAULT_METRES, []
        if m.verdict == "MERGE" and m.survivor is not None:
            metres = distance[tuple(sorted((site, m.survivor)))]
            if metres > DEFAULT_METRES:
                granted = _limit(metres, overrides.get(site), library)
                if granted is None:
                    reason = reason or (
                        f"beyond {DEFAULT_METRES} m ({metres:.0f} m): a per-pair override with a "
                        "quote is the owner's to give (OVERRIDES.json)"
                    )
                else:
                    metres_limit, limit_evidence = granted
        out_members.append(
            {
                "site_id": site,
                "name": names[site],
                "verdict": m.verdict,
                "survivor": m.survivor,
                "parent": m.parent,
                "why": m.why,
                "quotes": list(m.quotes),
                "quote_outcomes": outcomes,
                "metres": None if metres is None else round(metres, 1),
                "metres_limit": metres_limit,
                "limit_evidence": limit_evidence,
                "status": HELD if reason else DECIDED,
                "reason": reason or "",
            }
        )
    held = [m for m in out_members if m["status"] == HELD]
    return {
        "label": cluster["cluster_id"],
        "cluster_id": cluster["cluster_id"],
        "status": HELD if held else DECIDED,
        "reason": "; ".join(f"{m['name']}: {m['reason']}" for m in held),
        "round": round_name,
        "answered_by": answered_by,
        "members": out_members,
    }


def _limit(
    metres: float, override: Mapping[str, Any] | None, library: Q.Library
) -> tuple[int, list[dict[str, str]]] | None:
    """The distance limit an override gives a loser with the evidence that carries it, or `None`:
    it needs a limit at or above the measured distance, and evidence whose quotes the machine
    finds. The limit and its quotes are what the decision, the pair and the plan journal."""
    if override is None:
        return None
    limit = int(override["metres_limit"])
    quotes = override.get("evidence") or []
    if limit < math.ceil(metres) or not quotes:
        return None
    _outcomes, failure = rounds.quote_outcomes(quotes, "override", library)
    return None if failure else (limit, [dict(q) for q in quotes])


def decide_recheck(
    cluster: Mapping[str, Any],
    relations: Mapping[str, Relation],
    *,
    round_name: str,
    answered_by: str,
    library: Q.Library,
) -> dict[str, Any]:
    names = {m["id"]: m["name"] for m in cluster["members"]}
    out = []
    for site in sorted(relations):
        r = relations[site]
        outcomes, failure = rounds.quote_outcomes(
            r.quotes, f"{cluster['cluster_id']}/{site}", library
        )
        out.append(
            {
                "site_id": site,
                "name": names[site],
                "decision": r.decision,
                "target": r.target,
                "why": r.why,
                "quotes": list(r.quotes),
                "quote_outcomes": outcomes,
                "status": HELD if failure else DECIDED,
                "reason": failure or "",
            }
        )
    held = [m for m in out if m["status"] == HELD]
    return {
        "label": cluster["cluster_id"],
        "cluster_id": cluster["cluster_id"],
        "status": HELD if held else DECIDED,
        "reason": "; ".join(f"{m['name']}: {m['reason']}" for m in held),
        "round": round_name,
        "answered_by": answered_by,
        "members": out,
    }


# ------------------------------------------------------------------------------- the decisions
def build_decisions(
    ctx: Context,
    verdicts: Mapping[str, Mapping[str, Any]],
    rechecks: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """`DUP_DECISIONS.jsonl`: per cluster what is decided, what waits for its recheck and what is
    held, and per already-retired loser the move that completes its retirement.

    A MERGE or PART_OF is **decided** only when its verdict is decided and its recheck CONFIRMs the
    same target; a RETARGET or REJECT, or a held recheck, holds it with the reasons of both readers.
    WRONG_ID needs no recheck (Opus rechecks MERGE and PART_OF). Nothing is guessed: a cluster with no
    verdict is `unanswered`."""
    records: list[dict[str, Any]] = []
    for cluster_id in sorted(ctx.clusters):
        cluster = ctx.clusters[cluster_id]
        verdict = verdicts.get(cluster_id)
        if verdict is None:
            records.append({"cluster_id": cluster_id, "status": "unanswered", "merges": [],
                            "part_of": [], "wrong_id": [], "distinct": [], "held": []})  # fmt: skip
            continue
        recheck = rechecks.get(cluster_id)
        asked = {m["site_id"]: m for m in recheck["members"]} if recheck else {}
        merges, parts, wrong, distinct, held = [], [], [], [], []
        pending = False
        names = {m["id"]: m["name"] for m in cluster["members"]}
        # an answer that was not in shape has no members: nothing of it is decided
        if not verdict["members"]:
            held.append({"site_id": None, "name": cluster_id, "reason": verdict["reason"]})
        for m in verdict["members"]:
            site = m["site_id"]
            if m["status"] == HELD:
                held.append({"site_id": site, "name": m["name"], "reason": m["reason"]})
                continue
            if m["verdict"] == "DISTINCT":
                distinct.append(site)
            elif m["verdict"] == "WRONG_ID":
                wrong.append(
                    {"site_id": site, "name": m["name"], "why": m["why"], "quotes": m["quotes"]}
                )
            else:
                target = m["survivor"] if m["verdict"] == "MERGE" else m["parent"]
                second = asked.get(site)
                if second is None or recheck is None:
                    pending = True
                    continue
                if second["status"] == HELD or second["decision"] != "CONFIRM":
                    held.append(
                        {
                            "site_id": site,
                            "name": m["name"],
                            "reason": (
                                f"the recheck {second['decision']}s ({second['why']})"
                                if second["status"] == DECIDED
                                else f"the recheck is held ({second['reason']})"
                            ),
                        }
                    )
                    continue
                item = {
                    "kind": m["verdict"],
                    "site_id": site,
                    "name": m["name"],
                    "target": target,
                    "target_name": names[target],
                    "why": m["why"],
                    "recheck_why": second["why"],
                    "quotes": m["quotes"] + second["quotes"],
                    "metres": m["metres"],
                }
                if m["verdict"] == "MERGE":
                    # the limit and its evidence are the verdict round's, checked once there
                    item["metres_limit"] = m["metres_limit"]
                    item["limit_evidence"] = m["limit_evidence"]
                    merges.append(item)
                else:
                    parts.append(item)
        records.append(
            {
                "cluster_id": cluster_id,
                "status": "held" if held else ("pending-recheck" if pending else "complete"),
                "round": verdict["round"],
                "answered_by": [verdict["answered_by"]]
                + ([recheck["answered_by"]] if recheck else []),
                "merges": merges,
                "part_of": parts,
                "wrong_id": wrong,
                "distinct": distinct,
                "held": held,
            }
        )
    for loser in ctx.retired_losers:
        records.append(
            {
                "cluster_id": f"retired-{loser['id'][:8]}",
                "status": "complete",
                "source": "retired-loser",
                "merges": [
                    {
                        "kind": "MERGE",
                        "site_id": loser["id"],
                        "name": loser["name"],
                        "target": loser["survivor_id"],
                        "target_name": loser["survivor_name"],
                        "why": "already retired as duplicate_of its survivor; its images and "
                        "links still sit on it",
                        "quotes": [],
                        "metres": None,
                        "metres_limit": DEFAULT_METRES,
                        "limit_evidence": [],
                        "already_retired": True,
                    }
                ],
                "part_of": [],
                "wrong_id": [],
                "distinct": [],
                "held": [],
            }
        )
    return records


def decisions_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "clusters": len(records),
        "status": dict(Counter(r["status"] for r in records)),
        "merges": sum(len(r["merges"]) for r in records),
        "part_of": sum(len(r["part_of"]) for r in records),
        "wrong_id": sum(len(r["wrong_id"]) for r in records),
        "held_members": sum(len(r["held"]) for r in records),
    }


# ------------------------------------------------------------------------------ the rounds' glue
def load_decisions(run: Path, stage: str) -> dict[str, dict[str, Any]]:
    """The latest decision per cluster of a stage."""
    return rounds.load_decisions(dup_run(run), stage)


def _prompt_of(
    stage: str, ctx: Context, recheck_of: Mapping[str, Mapping[str, Any]] | None = None
) -> Callable[[str, str | None], str]:
    def build(label: str, earlier: str | None) -> str:
        cluster = ctx.clusters[label]
        if stage == STAGE_VERDICT:
            return verdict_prompt(cluster, ctx, earlier)
        assert recheck_of is not None
        return recheck_prompt(cluster, ctx, recheck_of[label], earlier)

    return build


def export_verdicts(
    run: Path, ctx: Context, handoff: Path, *, now: Callable[[], str] = rounds.now_utc
) -> rounds.Round:
    """Round 1 asks every cluster; a later round asks the clusters whose latest verdict is held,
    each with why."""
    labels, earlier = rounds.labels_for_round(dup_run(run), STAGE_VERDICT, sorted(ctx.clusters))
    return rounds.export_round(
        dup_run(run), STAGE_VERDICT, labels, _prompt_of(STAGE_VERDICT, ctx), handoff,
        basis=ctx.basis, earlier=earlier, now=now,
    )  # fmt: skip


def export_rechecks(
    run: Path, ctx: Context, handoff: Path, *, now: Callable[[], str] = rounds.now_utc
) -> rounds.Round:
    """Round 1 asks every cluster with a decided MERGE or PART_OF; a later round the clusters whose
    latest recheck is held."""
    verdicts = load_decisions(run, STAGE_VERDICT)
    first = [c for c, d in verdicts.items() if d["status"] == DECIDED and relations_of(d)]
    if not first and not rounds.load_rounds(dup_run(run), STAGE_RECHECK):
        raise rounds.RoundError("no cluster has a decided MERGE or PART_OF to recheck")
    labels, earlier = rounds.labels_for_round(dup_run(run), STAGE_RECHECK, first)
    return rounds.export_round(
        dup_run(run), STAGE_RECHECK, labels, _prompt_of(STAGE_RECHECK, ctx, verdicts), handoff,
        basis=ctx.basis, earlier=earlier, now=now,
    )  # fmt: skip


def import_round(
    run: Path,
    stage: str,
    round_name: str,
    ctx: Context,
    fetch: rounds.Fetch,
    *,
    calibrations: Mapping[str, str],
    now: Callable[[], str] = rounds.now_utc,
    root: Path | None = None,
    calibration_root: Path | None = None,
) -> dict[str, Any]:
    """Parse, fetch and decide every answer of one round of `stage`; merge the decisions.

    `calibrations` names the passed calibration of each answering role (`rounds.check_calibrated`)."""
    verdicts = load_decisions(run, STAGE_VERDICT)
    overrides = _overrides(run)

    def parse(label: str, text: str) -> Any:
        cluster = ctx.clusters[label]
        if stage == STAGE_VERDICT:
            return parse_verdict(text, cluster)
        return parse_recheck(
            text, cluster, {m["site_id"]: m for m in relations_of(verdicts[label])}
        )

    def decide(
        label: str, items: Any, round_name: str, by: str, library: Q.Library
    ) -> dict[str, Any]:
        cluster = ctx.clusters[label]
        if stage == STAGE_VERDICT:
            return decide_verdict(
                cluster, items, round_name=round_name, answered_by=by, library=library,
                overrides=overrides,
            )  # fmt: skip
        return decide_recheck(
            cluster, items, round_name=round_name, answered_by=by, library=library
        )

    return rounds.import_stage(
        dup_run(run), stage, round_name,
        prompt_of=_prompt_of(stage, ctx, verdicts if stage == STAGE_RECHECK else None),
        allowed_roles=(ROLE_VERDICT,) if stage == STAGE_VERDICT else ROLES_RECHECK,
        parse=parse, decide=decide, wiki=ctx.wiki, fetch=fetch, calibrations=calibrations,
        calibration_root=calibration_root, extra_urls={q["source"] for o in overrides.values() for q in o.get("evidence", [])},
        now=now, root=root, repo=REPO,
    )  # fmt: skip


def write_decisions(run: Path, ctx: Context) -> dict[str, Any]:
    """Build `DUP_DECISIONS.jsonl` from the imported verdicts and rechecks."""
    records = build_decisions(
        ctx, load_decisions(run, STAGE_VERDICT), load_decisions(run, STAGE_RECHECK)
    )
    common.write_jsonl(run / DUP_DECISIONS, records)
    return decisions_summary(records)


# ----------------------------------------------------------------------------------- the brief
BRIEF = """You are agent {batch} of the D14 duplicate question of the Ancient Nerds sites remediation \
(stage {stage}, round {round}), role {role}. You answer {count} question(s), each about one cluster \
of site records. Answer each one on its own.

Read ONLY your prompt files: {handoff}/{batch}/MANIFEST.jsonl lists them, one JSON line per \
question with its "label" (the cluster id) and its "prompt_path" (relative to {handoff}), plus the \
cached Wikipedia files and the web pages your prompt names. Open no other file of the repository, no \
database, no git history. Fetch live at most a few requests, one at a time; an HTTP 403 or 429 is a \
throttle, never a finding.

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
    handoff: str | None = None,
    role: str | None = None,
) -> str:
    """The instruction of the agent that answers one batch of one round.

    `stage_run` and `handoff` point a calibration's brief at its own rounds and at the copy of the
    pool the role re-answers into; `check=False` drops the shape check, which a copy has no run for;
    `role` names the role the agent answers in when it is not the stage's first (the pilot judge
    rechecks the first clusters)."""
    import roles as RO

    record = rounds.find_round(stage_run or dup_run(run), stage, round_name)
    if batch_id not in record.batches:
        raise rounds.RoundError(f"{batch_id} is no batch of {stage} round {round_name}")
    allowed = (ROLE_VERDICT,) if stage == STAGE_VERDICT else ROLES_RECHECK
    role = role or allowed[0]
    if role not in allowed:
        raise rounds.RoundError(f"{role} is no role of {stage}: it asks {' or '.join(allowed)}")
    where = handoff or record.handoff
    text = BRIEF.format(
        batch=batch_id, stage=stage, round=round_name, role=role, model=RO.role(role).model,
        count=len(record.batches[batch_id]), handoff=where,
        scratch=f"{where}-scratch/{batch_id}", python="./.venv/Scripts/python.exe",
        run_tool="scripts/remediation/identity/dup_judge.py",
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
    """The shape problem of an answer text, or `None` - no page is fetched, no verdict judged."""
    record = rounds.find_round(dup_run(run), stage, round_name)
    if label not in record.labels:
        raise rounds.RoundError(f"{label} is no question of {stage} round {round_name}")
    cluster = ctx.clusters[label]
    try:
        if stage == STAGE_VERDICT:
            parse_verdict(text, cluster)
        else:
            verdicts = load_decisions(run, STAGE_VERDICT)
            parse_recheck(text, cluster, {m["site_id"]: m for m in relations_of(verdicts[label])})
    except AnswerError as exc:
        return str(exc)
    return None


# ------------------------------------------------------------------------------------------ CLI
def _fetch_live(urls: list[str], pages: Path) -> dict[str, int]:
    http = Q.http_client()
    try:
        return Q.collect(urls, pages, http, now=rounds.now_utc)
    finally:
        http.close()


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description="D14 duplicate verdicts, rechecks and decisions.")
    ap.add_argument("--root", type=Path, default=None, help="main checkout (default: found)")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("export", "import"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--stage", choices=(STAGE_VERDICT, STAGE_RECHECK), required=True)
        if name == "export":
            cmd.add_argument("--handoff", type=Path, required=True, help="a new directory")
        else:
            cmd.add_argument("--round", required=True)
            cmd.add_argument(
                "--calibration", action="append", default=[], metavar="ROLE=ID",
                help="the passed calibration of each answering role (repeatable)",
            )  # fmt: skip
    brief_cmd = sub.add_parser("brief")
    brief_cmd.add_argument("--stage", choices=(STAGE_VERDICT, STAGE_RECHECK), required=True)
    brief_cmd.add_argument("--round", required=True)
    brief_cmd.add_argument("--batch-id", required=True)
    brief_cmd.add_argument(
        "--role", help="the role the agent answers in (default: the stage's first)"
    )
    brief_cmd.add_argument("--stage-run", type=Path, help="a calibration's own rounds directory")
    brief_cmd.add_argument("--handoff", help="the handoff directory the agent answers into")
    brief_cmd.add_argument(
        "--no-check", action="store_true", help="drop the shape check (a calibration copy)"
    )
    check = sub.add_parser("check-answer")
    check.add_argument("--stage", choices=(STAGE_VERDICT, STAGE_RECHECK), required=True)
    check.add_argument("--round", required=True)
    check.add_argument("--label", required=True)
    check.add_argument("--text-file", type=Path, required=True)
    sub.add_parser("decisions", help="build DUP_DECISIONS.jsonl from the imported rounds")
    args = ap.parse_args(argv)
    run = common.run_dir(args.root)
    try:
        ctx = load_context(run, root=args.root)
        if args.command == "export":
            if args.stage == STAGE_VERDICT:
                record = export_verdicts(run, ctx, args.handoff)
            else:
                record = export_rechecks(run, ctx, args.handoff)
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
                    import_round(
                        run,
                        args.stage,
                        args.round,
                        ctx,
                        _fetch_live,
                        calibrations=rounds.parse_calibrations(args.calibration),
                    ),  # fmt: skip
                    indent=1,
                    sort_keys=True,
                )
            )
        elif args.command == "brief":
            print(
                brief(
                    run,
                    args.stage,
                    args.round,
                    args.batch_id,
                    stage_run=args.stage_run,
                    check=not args.no_check,
                    handoff=args.handoff,
                    role=args.role,
                )
            )
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
