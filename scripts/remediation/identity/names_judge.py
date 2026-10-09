"""D23: broken or foreign names become the English name; a short spoken name for the Short.

Owner decision D23 (2026-10-08): "both: broken or foreign names cleaned to the English name
(journalled, the old name kept as an alias) and a separate short spoken name for the Short". The
triage (`names_triage.py`) lists 631 shown records with a defective name and, for 330 of them, a repair
that is itself an attested form of the site's own item (`suggestion`); the other 301 need a model.

## The clean name

* **Stage `name-clean-web`** (role `web_verifier`, Sonnet): `KEEP` the stored name, or `RENAME` to a
  name of this very site - the English label or an English alias of its item, or the title of its
  English Wikipedia article (a bracketed qualifier may be left off) - with a quote of a page that
  holds it. The machine checks the name against the item's entity page (fetched, cited or not) and
  the article titles the record carries (`l5/decide.py`'s rule for a rename).
* **Stage `name-clean-recheck`** (role `adversarial`, Opus) re-checks **every** rename, the
  model-made ones and the triage's rule-made suggestions alike: `CONFIRM` (with a quote that holds the
  name) or `REJECT`.
* **The write** is `name-clean-<wave>` with its alias chunk (`name_write.py`).

## The spoken name

The short name the Short's closing line says (`pipeline/video/shorts_tts.spoken_name`). The rule
(`names_triage.spoken_record`) resolves 4,653 of 4,900; 619 of those differ from the stored name and
are written as they are. The 247 it cannot make clean go to the model (stage `spoken-model`, role
`web_verifier`, Sonnet): `SPEAK` one of the site's attested forms, respelled TTS-safe, or `NONE` (the
name is spoken as stored). The machine constrains the answer: it derives from one of the attested
forms (`from_form`, folded equal), carries only characters a narrator reads (`tts_problems`: Latin
letters and marks, spaces, hyphen, ASCII apostrophe; no modifier letters, no digits) and is at most
`SPOKEN_MAX_CHARS` long. `spoken-<wave>` fills `unified_sites.spoken_name` where it is NULL.
"""

from __future__ import annotations

import sys
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(_HERE.parents[1]), str(REPO / "output" / "remediation" / "tools")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from l5 import decide as L5D  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical.identity_lanes import SPOKEN_MAX_CHARS, name_lane, spoken_lane  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from identity import answers as A  # noqa: E402
from identity import common, export, name_write, names_triage  # noqa: E402
from identity.prompts import (  # noqa: E402
    cache_entries,
    cache_section,
    earlier_section,
    wiki_cache_dir,
)
from identity.retarget import ENTITY_DATA, NAME_CHARS, QID_RE, attested_names  # noqa: E402
from identity.rounds import (  # noqa: E402
    DECIDED,
    HELD,
    AnswerError,
    Env,
    Outcome,
    Question,
    StageSpec,
)

LANE = "names"
CLEAN_WEB, CLEAN_RECHECK, SPOKEN = "name-clean-web", "name-clean-recheck", "spoken-model"
KEEP, RENAME = "KEEP", "RENAME"
CONFIRM, REJECT = "CONFIRM", "REJECT"
SPEAK, NONE = "SPEAK", "NONE"
ATTESTED_AS = ("label", "alias", "enwiki_title")
CLEAN_KEYS = frozenset({"site_id", "verdict", "new_name", "attested_as", "why", "quotes"})
RECHECK_KEYS = frozenset({"site_id", "verdict", "why", "quotes"})
SPOKEN_KEYS = frozenset({"site_id", "verdict", "spoken", "from_form", "why"})
TRIAGE_FILE = names_triage.TRIAGE_OUTPUT
SPOKEN_FILE = names_triage.SPOKEN_OUTPUT
DIR = "names"
RULE = "rule"
MODEL = "model"

DEFECT_WORDS = {
    "nonlatin_script": "it is not written in Latin letters",
    "mixed_script": "a word mixes scripts (a look-alike letter of another alphabet)",
    "whitespace_artifact": "it holds a zero-width character, a double space or edge spaces",
    "edge_punctuation": "it starts or ends with a dash, comma or colon",
    "all_caps": "it is all capitals",
    "mojibake": "it holds mis-decoded characters",
    "digit": "it holds a digit",
    "parenthesis": "it holds a (parenthesis)",
    "foreign_prefix": "it opens with a foreign word for the kind of the thing",
    "comma_qualifier": "it holds a comma qualifier",
    "long": f"it is longer than {names_triage.LONG_NAME_CHARS} characters",
}


# ------------------------------------------------------------------------------------ the contexts
def _ext_of(exported: export.Export) -> dict[str, dict[str, list[str]]]:
    ext: dict[str, dict[str, list[str]]] = {}
    for e in exported.ext_ids:
        ext.setdefault(e["site_id"], {}).setdefault(e["kind"], []).append(e["value"])
    return ext


def clean_context(
    triage: Mapping[str, Any],
    row: Mapping[str, Any],
    ext: Mapping[str, Sequence[str]],
    cache: Sequence[Mapping[str, str]],
    exported_at: str,
) -> dict[str, Any]:
    """Everything the name-clean question is a function of, JSON-able and stored with the round."""
    return {
        "site_id": triage["id"],
        "exported_at": exported_at,
        "name": triage["name"],
        "country": triage["country"],
        "site_type": triage["site_type"],
        "lat": row["lat"],
        "lon": row["lon"],
        "description": row["description"][:400],
        "scope_status": row["scope_status"],
        "qids": list(ext.get("wikidata_qid", [])),
        "enwiki": list(ext.get("enwiki_title", [])),
        "defects": list(triage["defects"]),
        "severity": triage["severity"],
        "differs_from_label": bool(triage["differs_from_label"]),
        "label": triage["label"],
        "aliases": list(triage["aliases"]),
        "suggestion": triage["suggestion"],
        "cache": list(cache),
    }


def _load(run: Path, root: Path | None):
    exported = export.load_export(run / common.EXPORT_FILE)
    return (
        exported,
        common.rows_by_id(exported.shown),
        _ext_of(exported),
        cache_entries(wiki_cache_dir(root)),
    )


def clean_questions(
    run: Path, *, root: Path | None = None, exclude: Sequence[str] = (), rule_made: bool = False
) -> list[Question]:
    """The triage records that need a model (`rule_made=False`) or the ones the triage repaired
    itself (`rule_made=True`; they skip the web stage and go to the re-check), one question each."""
    exported, by_id, ext, cache = _load(run, root)
    skip = set(exclude)
    out = []
    for t in common.read_jsonl(run / TRIAGE_FILE):
        if t["id"] in skip or t["needs_model"] == rule_made:
            continue
        out.append(
            Question(
                t["id"],
                clean_context(
                    t,
                    by_id[t["id"]],
                    ext.get(t["id"], {}),
                    cache.get(t["id"], []),
                    exported.exported_at,
                ),
            )
        )
    return out


# -------------------------------------------------------------------------------------- the prompt
CLEAN_TEMPLATE = """You are a web verifier of the name pass (owner decision D23) of the Ancient \
Nerds final repair. One curated site of a map of ancient sites has a name that may be broken or \
foreign. Decide whether the stored name is the English name of this site, and if not, which \
attested English name it should carry. Research on the open web; read the pages you cite.

THE SITE (read {exported_at})
  id:           {site_id}
  name:         {name}
  country:      {country}
  point:        {lat}, {lon}
  type:         {site_type}
  Wikidata:     {qids}
  Wikipedia:    {titles}
  description (first {chars} characters):
{description}

WHY THE NAME IS ASKED
{defects}
KNOWN FORMS OF THIS SITE'S OWN ITEM
  English label: {label}
  English aliases: {aliases}
{cache}{earlier}
THE QUESTION. Decide ONE verdict:
  KEEP    the stored name is an English name of this site as it stands: a comma qualifier or a \
bracket that tells two places apart and that English sources use, a name the item and the article \
bear themselves. A name that merely differs from the item's label is NOT a defect.
  RENAME  the stored name is broken or foreign (a look-alike letter, an untranslated Spanish, French \
or Italian kind word, a cut-off title, a catalogue number) and this site has an attested English \
name. Give it as "new_name".

THE RULES (L5's rule for a rename, B1-N)
1. "new_name" is a name of THIS site: the English label or an English alias of its Wikidata item, \
or the title of its English Wikipedia article (a bracketed qualifier such as "(Roman fort)" may be \
left off). The machine checks it against the item's entity page and the article titles above; \
"attested_as" says which: label, alias or enwiki_title.
2. It is not the stored name. It is not a translation or a descriptive form you made up, and not \
the name of the town, region or complex the site lies in.
3. A RENAME carries at least one quote: verbatim text (whitespace may differ) of a page you cite by \
its URL that holds the new name for this site. The machine fetches it and does not count a verdict \
whose quote it cannot find. Cite https://www.wikidata.org/wiki/Special:EntityData/<QID>.json for \
a label or alias. Never cite ancientnerds.com.
4. A KEEP may carry quotes too, none are required.

ANSWER with only this JSON object:
{{
 "site_id": "{site_id}",
 "verdict": "KEEP | RENAME",
 "new_name": null,
 "attested_as": null,
 "why": "one or two sentences",
 "quotes": [{{"url": "https://...", "quote": "..."}}]
}}
For RENAME "new_name" is the name and "attested_as" is "label", "alias" or "enwiki_title".
"""

RECHECK_TEMPLATE = """You are the adversarial reviewer of the name pass (owner decision D23) of the \
Ancient Nerds final repair. A name of one curated site of a map of ancient sites is to be \
changed, and the old name will become an alias; a wrong rename is shown to every visitor and read \
aloud in a video. Try to REFUTE it before you confirm it. Research on the open web with your own \
searches; read the pages.

THE SITE (read {exported_at})
  id: {site_id}   name: {name}   country: {country}   point: {lat}, {lon}   type: {site_type}
  Wikidata: {qids}   Wikipedia: {titles}
  description: {description}
{cache}
WHY THE NAME IS ASKED
{defects}
THE PROPOSAL ({source})
  rename "{name}" -> "{new_name}"   (attested as {attested_as})
  {why}
{proposal}
{earlier}
THE QUESTION
Is "{new_name}" an English name of THIS very site (not of the town, region or complex around it, \
not of a namesake elsewhere), attested by its Wikidata item's English label or alias or by the title \
of its English Wikipedia article - and is the stored name really broken or foreign, so that \
the change is an improvement and not a swap of one good name for another?
Answer CONFIRM only when you found the proof on pages you read yourself; every CONFIRM carries at \
least one quote - verbatim text of a page you cite by its URL that holds "{new_name}" for this \
site; the machine fetches it and does not count a confirmation whose quote it cannot find. Answer \
REJECT when anything is wrong or unproven (say what). Never cite ancientnerds.com.

ANSWER with only this JSON object:
{{"site_id": "{site_id}", "verdict": "CONFIRM | REJECT", "why": "one or two sentences", \
"quotes": [{{"url": "https://...", "quote": "..."}}]}}
"""


def _defects(ctx: Mapping[str, Any]) -> str:
    lines = [f"  - {DEFECT_WORDS[d]}" for d in ctx["defects"]]
    if ctx["differs_from_label"]:
        lines.append(
            "  - (a note, not a defect) it shares almost no word with the item's English label"
        )
    return "\n".join(lines)


def _titles(ctx: Mapping[str, Any]) -> str:
    return ", ".join(ctx["enwiki"]) or "none"


def render_clean(ctx: Mapping[str, Any], earlier: str | None = None) -> str:
    description = str(ctx["description"] or "(none)")
    return CLEAN_TEMPLATE.format(
        exported_at=ctx["exported_at"],
        site_id=ctx["site_id"],
        name=ctx["name"],
        country=ctx["country"],
        lat=ctx["lat"],
        lon=ctx["lon"],
        site_type=ctx["site_type"],
        qids=", ".join(f"{q} (https://www.wikidata.org/wiki/{q})" for q in ctx["qids"]) or "none",
        titles=_titles(ctx),
        chars=len(description),
        description="    " + description.replace("\n", "\n    "),
        defects=_defects(ctx),
        label=ctx["label"] or "none",
        aliases="; ".join(ctx["aliases"]) or "none",
        cache=cache_section(ctx),
        earlier=earlier_section(earlier),
    )


# ------------------------------------------------------------------------------------ the answer
@dataclass(frozen=True)
class Clean:
    site_id: str
    verdict: str
    new_name: str | None
    attested_as: str | None
    why: str
    quotes: tuple[dict[str, str], ...]


def parse_clean(text: str, ctx: Mapping[str, Any]) -> Clean:
    data = A.load_object(text, CLEAN_KEYS)
    if data["site_id"] != ctx["site_id"]:
        raise AnswerError(f"site_id {data['site_id']!r} is not this question's {ctx['site_id']}")
    verdict = data["verdict"]
    if verdict not in (KEEP, RENAME):
        raise AnswerError(f"verdict {verdict!r} is not KEEP or RENAME")
    why = A.text_of(data["why"], "why", max_chars=600)
    quotes = A.quotes_of(data["quotes"], "quotes", minimum=1 if verdict == RENAME else 0)
    new, attested = data["new_name"], data["attested_as"]
    if verdict == KEEP:
        if new is not None or attested is not None:
            raise AnswerError("new_name and attested_as are null for KEEP")
        return Clean(ctx["site_id"], KEEP, None, None, why, quotes)
    new = A.text_of(new, "new_name", max_chars=NAME_CHARS)
    if new == ctx["name"]:
        raise AnswerError("new_name is the stored name - that is KEEP")
    if attested not in ATTESTED_AS:
        raise AnswerError(f"attested_as {attested!r} is not one of {', '.join(ATTESTED_AS)}")
    if not any(Q.normalise(new) in Q.normalise(q["quote"]) for q in quotes):
        raise AnswerError("a RENAME quotes a page with the new name in the quote")
    return Clean(ctx["site_id"], RENAME, new, attested, why, quotes)


def _entity_urls(ctx: Mapping[str, Any]) -> set[str]:
    return {ENTITY_DATA.format(q) for q in ctx["qids"] if QID_RE.fullmatch(q)}


def cited_clean(answer: Clean, ctx: Mapping[str, Any]) -> set[str]:
    """Every cited page, and - for a rename - the entity page of each item the record carries,
    cited or not: the name is checked against it."""
    urls = A.urls_of(answer.quotes)
    return urls | _entity_urls(ctx) if answer.verdict == RENAME else urls


def attested_in(ctx: Mapping[str, Any], library: Q.Library) -> tuple[set[str], list[str]]:
    """The names this record may take: the English labels and aliases of the entity pages of its
    items and the titles of its articles (with and without the bracketed qualifier). Also the
    problems of reading the pages."""
    names: set[str] = set()
    problems: list[str] = []
    for title in ctx["enwiki"]:
        names |= {title, L5D.QUALIFIER.sub("", title)}
    for qid in ctx["qids"]:
        try:
            names |= attested_names(L5D.entity_page(library, qid, "name"), "")
        except L5D.Held as exc:
            problems.append(str(exc))
    names.discard("")
    return names, problems


def decide_clean(answer: Clean, ctx: Mapping[str, Any], env: Env) -> Outcome:
    data: dict[str, Any] = {
        "verdict": answer.verdict,
        "new_name": answer.new_name,
        "attested_as": answer.attested_as,
        "why": answer.why,
        "quotes": [],
        "note": "",
    }
    counted, noted, reason = A.check_quotes(answer.quotes, ctx["site_id"], env.library)
    data["quotes"] = noted
    if not counted:
        return Outcome(HELD, f"quotes: a quote does not count ({reason})", data)
    if answer.verdict == KEEP:
        return Outcome(DECIDED, "", data)
    names, problems = attested_in(ctx, env.library)
    if problems:
        return Outcome(HELD, problems[0], data)
    if not ctx["qids"] and not ctx["enwiki"]:
        return Outcome(
            HELD, "name: the record carries no item and no article - nothing attests a name", data
        )
    if Q.normalise(str(answer.new_name)) not in {Q.normalise(n) for n in names}:
        shown = ", ".join(repr(n) for n in sorted(names)[:8])
        return Outcome(
            HELD,
            f"name: {answer.new_name!r} is no English label or alias of the record's item and no "
            f"title of its article ({shown or 'none'})",
            data,
        )
    data["note"] = f"{answer.new_name!r} is a name of the record's own item or article"
    return Outcome(DECIDED, "", data)


def clean_spec() -> StageSpec:
    return StageSpec(
        lane=LANE,
        stage=CLEAN_WEB,
        role="web_verifier",
        render=render_clean,
        parse=parse_clean,
        decide=decide_clean,
        cited=cited_clean,
        titles=lambda a, c: set(),
        per_batch=5,
        guidance="A name that only differs from the item's label is no defect: KEEP it.",
    )


# -------------------------------------------------------------------------------------- the re-check
def web_proposal(decision: Mapping[str, Any]) -> dict[str, Any]:
    data = decision["data"]
    return {
        "source": MODEL,
        "new_name": data["new_name"],
        "attested_as": data["attested_as"],
        "why": data["why"],
        "quotes": [{"url": q["url"], "quote": q["quote"]} for q in data["quotes"]],
    }


def rule_proposal(ctx: Mapping[str, Any]) -> dict[str, Any]:
    s = ctx["suggestion"]
    return {
        "source": RULE,
        "new_name": s["value"],
        "attested_as": {"label": "label", "alias": "alias", "enwiki_title": "enwiki_title"}.get(
            s["source"], s["source"]
        ),
        "why": f"the triage repaired the name by rule ({s['kind']}): the repair is an attested form "
        f"of the site's own item ({s['source']}).",
        "quotes": [],
    }


def recheck_questions(
    web_asked: Sequence[Question],
    web_decisions: Mapping[str, Mapping[str, Any]],
    rule_asked: Sequence[Question],
) -> list[Question]:
    """The re-check asks every rename: each decided model-made RENAME and every rule-made suggestion."""
    out = []
    for q in web_asked:
        d = web_decisions.get(q.site_id)
        if d is not None and d["status"] == DECIDED and d["data"]["verdict"] == RENAME:
            out.append(Question(q.site_id, {**q.context, "proposal": web_proposal(d)}))
    for q in rule_asked:
        out.append(Question(q.site_id, {**q.context, "proposal": rule_proposal(q.context)}))
    return sorted(out, key=lambda q: q.site_id)


def render_recheck(ctx: Mapping[str, Any], earlier: str | None = None) -> str:
    p = ctx["proposal"]
    quotes = "\n".join(f'  quote: "{q["quote"]}" - {q["url"]}' for q in p["quotes"])
    return RECHECK_TEMPLATE.format(
        exported_at=ctx["exported_at"],
        site_id=ctx["site_id"],
        name=ctx["name"],
        country=ctx["country"],
        lat=ctx["lat"],
        lon=ctx["lon"],
        site_type=ctx["site_type"],
        qids=", ".join(ctx["qids"]) or "none",
        titles=_titles(ctx),
        description=" ".join(str(ctx["description"] or "(none)").split()),
        cache=cache_section(ctx),
        defects=_defects(ctx),
        source={"model": "made by a web verifier", "rule": "made by the triage's rule"}[
            p["source"]
        ],
        new_name=p["new_name"],
        attested_as=p["attested_as"],
        why=p["why"],
        proposal=quotes,
        earlier=earlier_section(earlier),
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
    if data["verdict"] == CONFIRM and not any(
        Q.normalise(ctx["proposal"]["new_name"]) in Q.normalise(q["quote"]) for q in quotes
    ):
        raise AnswerError("a CONFIRM quotes a page that holds the new name")
    return Review(ctx["site_id"], data["verdict"], why, quotes)


def decide_recheck(review: Review, ctx: Mapping[str, Any], env: Env) -> Outcome:
    counted, noted, reason = A.check_quotes(review.quotes, ctx["site_id"], env.library)
    data = {
        "verdict": review.verdict,
        "why": review.why,
        "proposed": ctx["proposal"]["new_name"],
        "quotes": noted,
    }
    if not counted:
        return Outcome(HELD, f"quotes: a quote does not count ({reason})", data)
    return Outcome(DECIDED, "", data)


def recheck_spec() -> StageSpec:
    return StageSpec(
        lane=LANE,
        stage=CLEAN_RECHECK,
        role="adversarial",
        render=render_recheck,
        parse=parse_recheck,
        decide=decide_recheck,
        cited=lambda r, c: A.urls_of(r.quotes),
        titles=lambda r, c: set(),
        per_batch=5,
        guidance="You are not told the rename is right. Look for the reason it is wrong.",
    )


def final_state(
    web: Mapping[str, Mapping[str, Any]],
    recheck: Mapping[str, Mapping[str, Any]],
    rule_sites: Sequence[str],
) -> list[dict[str, Any]]:
    """Where every asked site stands: `keep` (the web verdict KEEP), `confirmed` (a rename the
    re-check confirmed), `rejected`, `waiting-for-recheck` or `held`. A rule-made suggestion has no
    web decision: it is `confirmed`, `rejected` or `waiting-for-recheck` on the re-check alone."""
    out = []
    for sid in sorted({*web, *rule_sites}):
        second = recheck.get(sid)
        if sid in web and sid not in rule_sites:
            decision = web[sid]
            if decision["status"] != DECIDED:
                out.append({"site_id": sid, "source": MODEL, "state": "held"})
                continue
            if decision["data"]["verdict"] == KEEP:
                out.append({"site_id": sid, "source": MODEL, "state": "keep"})
                continue
        source = RULE if sid in rule_sites else MODEL
        if second is None or second["status"] != DECIDED:
            state = "waiting-for-recheck"
        elif second["data"]["verdict"] == CONFIRM:
            state = "confirmed"
        else:
            state = "rejected"
        out.append({"site_id": sid, "source": source, "state": state})
    return out


# -------------------------------------------------------------------------------------- the plan
def confirmed_renames(
    asked_web: Mapping[str, Mapping[str, Any]],
    web: Mapping[str, Mapping[str, Any]],
    rule_asked: Mapping[str, Mapping[str, Any]],
    recheck: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """The renames both stages agree on: `site -> {new_name, attested_as, source, quotes, why, who}`."""
    final = final_state(web, recheck, list(rule_asked))
    out: dict[str, dict[str, Any]] = {}
    for row in final:
        if row["state"] != "confirmed":
            continue
        sid, second = row["site_id"], recheck[row["site_id"]]
        if row["source"] == RULE:
            proposal = rule_proposal(rule_asked[sid])
            who, round_ = "rule:names_triage", "-"
            found = []
        else:
            d = web[sid]
            proposal = web_proposal(d)
            who, round_ = d["answered_by"], d["round"]
            found = [q for q in d["data"]["quotes"] if q["outcome"] == "found"]
        found += [q for q in second["data"]["quotes"] if q["outcome"] == "found"]
        out[sid] = {
            "new_name": proposal["new_name"],
            "attested_as": proposal["attested_as"],
            "source": row["source"],
            "why": proposal["why"],
            "who": who,
            "round": round_,
            "recheck": f"{second['answered_by']} ({second['round']}): {second['data']['why']}",
            "quotes": found,
        }
    return out


def build_clean(
    renames: Mapping[str, Mapping[str, Any]],
    asked: Mapping[str, Mapping[str, Any]],
    live: Mapping[str, Mapping[str, Any]],
    keys: Mapping[str, str],
    key_holders: Mapping[str, Sequence[Mapping[str, Any]]],
    name_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    wave: str,
) -> name_write.NamePlan:
    """The renames and aliases of a wave, from the decisions, the contexts they judged and one live
    read. A record whose name or links moved since it was asked is skipped, as is a name another
    visible record already bears (`name_write.plan_rename`)."""
    plan = name_write.NamePlan(name_lane("name-clean", wave))
    for sid in sorted(renames):
        rename, ctx, now = renames[sid], asked[sid], live.get(sid)

        def skip(reason: str, note: str, _sid: str = sid, _name: str = ctx["name"]) -> None:
            plan.skipped.append({"site_id": _sid, "name": _name, "reason": reason, "note": note})

        if now is None:
            skip("gone", "the site is no longer in unified_sites")
            continue
        if now["source_id"] != "ancient_nerds" or now["scope_status"] == "retired":
            skip("not-live", f"{now['source_id']} row, scope {now['scope_status']!r}")
            continue
        links = {"wikidata_qid": [], "enwiki_title": []}
        for e in now["ext"]:
            if e["kind"] in links:
                links[e["kind"]].append(str(e["value"]))
        moved = [
            f"{what}: {was!r} -> {is_!r}"
            for what, was, is_ in (
                ("name", ctx["name"], now["name"]),
                ("wikidata_qid", sorted(ctx["qids"]), sorted(links["wikidata_qid"])),
                ("enwiki_title", sorted(ctx["enwiki"]), sorted(links["enwiki_title"])),
                ("scope_status", ctx["scope_status"], now["scope_status"]),
            )
            if was != is_
        ]
        if moved:
            skip("changed-since-the-question", "; ".join(moved))
            continue
        evidence = [
            {"source": q["url"], "url": q["url"], "quote": q["quote"]} for q in rename["quotes"]
        ]
        if rename["source"] == RULE:
            evidence.append(
                {"source": rename["who"], "url": "names_triage", "quote": rename["why"]}
            )
        name_write.plan_rename(
            plan,
            site_id=sid,
            live=now,
            new_name=rename["new_name"],
            new_key=keys[rename["new_name"]],
            holders=key_holders.get(keys[rename["new_name"]], []),
            name_rows=name_rows.get(sid, []),
            evidence=evidence,
            note=(
                f"D23 ({rename['source']}: {rename['who']}) {rename['why']} Re-check "
                f"{rename['recheck']}"
            ),
            wave=wave,
            rule="d23-name-clean",
            finding_test_id="D23/name-clean",
        )
    return plan


# --------------------------------------------------------------------------------- the spoken name
#: A narrator reads these: Latin letters (accents allowed), spaces, hyphen, ASCII apostrophe, a full stop.
SPOKEN_PUNCTUATION = frozenset(" -'.")


def tts_problems(text: str) -> list[str]:
    """Why a spoken name is not TTS-safe: a modifier letter (U+02BC and the like, which a voice reads
    as a pause or drops), a digit, a letter of another script, a bracket, comma or slash."""
    problems = []
    for ch in dict.fromkeys(text):
        if ch.isalpha():
            if unicodedata.category(ch) == "Lm":
                problems.append(f"modifier letter {ch!r} ({unicodedata.name(ch, '?')})")
            elif not names_triage.is_latin(ch):
                problems.append(f"letter {ch!r} of another script")
        elif ch.isdigit():
            problems.append("a digit")
        elif ch not in SPOKEN_PUNCTUATION:
            problems.append(f"character {ch!r}")
    return problems


def _fold(text: str) -> str:
    """Case, accents and punctuation folded away: `Qʼumarkaj` and `Qumarkaj` are one spelling."""
    return "".join(common.fold(text).split())


def spoken_context(
    record: Mapping[str, Any],
    homonyms: Sequence[Mapping[str, Any]],
    cache: Sequence[Mapping[str, str]],
    exported_at: str,
    site: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "site_id": record["id"],
        "exported_at": exported_at,
        "name": record["name"],
        "country": record["country"],
        "site_type": site["site_type"],
        "reasons": list(record["reasons"]),
        "attested": list(record["attested"]),
        "homonyms": list(homonyms),
        "description": site["description"][:300],
        "cache": list(cache),
    }


def rule_spoken(run: Path) -> list[dict[str, Any]]:
    """The rule-made spoken names that differ from the stored name, for the sites that have a
    description (a site without one gets no Short): written as they are, no model."""
    return [
        r
        for r in common.read_jsonl(run / SPOKEN_FILE)
        if not r["needs_model"] and r["has_description"] and r["spoken"] != r["name"]
    ]


def spoken_questions(
    run: Path, *, root: Path | None = None, exclude: Collection[str] = ()
) -> list[Question]:
    """The sites the rule could not make a spoken name for, that have a description, except
    `exclude` (the sites whose name another lane still changes)."""
    exported, by_id, _ext, cache = _load(run, root)
    skip = set(exclude)
    cleaned: dict[str, list[Mapping[str, Any]]] = {}
    for row in exported.shown:
        cleaned.setdefault(names_triage.cleaned_name(row["name"])[0].casefold(), []).append(row)
    out = []
    for r in common.read_jsonl(run / SPOKEN_FILE):
        if not r["needs_model"] or not r["has_description"] or r["id"] in skip:
            continue
        key = names_triage.cleaned_name(r["name"])[0].casefold()
        homonyms = [
            {"name": o["name"], "country": o["country"]}
            for o in cleaned.get(key, [])
            if o["id"] != r["id"]
        ]
        out.append(
            Question(
                r["id"],
                spoken_context(
                    r, homonyms, cache.get(r["id"], []), exported.exported_at, by_id[r["id"]]
                ),
            )
        )
    return out


SPOKEN_TEMPLATE = """You are choosing the short name a narrator speaks in the closing line of a \
video about one ancient site (owner decision D23, stage spoken-model) of the Ancient Nerds final \
repair: "<name>, <country>." The stored name of the site is not good to say aloud. You do not \
research: you choose among the English forms the site's own item and article already carry.

THE SITE (read {exported_at})
  id:       {site_id}
  name:     {name}
  country:  {country}
  type:     {site_type}
  description: {description}

WHY THE RULE COULD NOT CHOOSE
{reasons}
THE ATTESTED ENGLISH FORMS (the item's label and aliases, the article's title, the stored label)
{attested}
{homonyms}{cache}{earlier}
THE QUESTION. Decide ONE verdict:
  SPEAK  one of the attested forms is a good short English name of this site. Give it as "spoken" \
and the attested form it comes from as "from_form" (copied exactly from the list above). "spoken" \
is that form, respelled for a voice: no modifier letters (write Qumarkaj for Qʼumarkaj, Jabal \
al-Hayn for Jabal al-ʿHayn), no digits, no brackets, no comma, no slash; accents are fine. It may \
leave out a leading word for the kind of the thing ("Cave of", "Archaeological Site of") only when \
the rest still names this site; it never adds a word.
  NONE   no attested form is better than the stored name: it is spoken as stored.

THE RULES
1. "spoken" is at most {max_chars} characters and carries only Latin letters, spaces, hyphens, the \
ASCII apostrophe and full stops.
2. A short name must still tell this site from another: where other records of the map share it \
(listed above), keep the qualifier that tells them apart.
3. Never a translation or a description of your own.

ANSWER with only this JSON object:
{{"site_id": "{site_id}", "verdict": "SPEAK | NONE", "spoken": null, "from_form": null, \
"why": "one sentence"}}
"""


def render_spoken(ctx: Mapping[str, Any], earlier: str | None = None) -> str:
    homonyms = ctx["homonyms"]
    return SPOKEN_TEMPLATE.format(
        exported_at=ctx["exported_at"],
        site_id=ctx["site_id"],
        name=ctx["name"],
        country=ctx["country"],
        site_type=ctx["site_type"],
        description=" ".join(str(ctx["description"] or "(none)").split()),
        reasons="\n".join(f"  - {r.replace('_', ' ')}" for r in ctx["reasons"]),
        attested="\n".join(f"  - {a}" for a in ctx["attested"]) or "  (none)",
        homonyms=(
            "OTHER RECORDS WHOSE NAME BECOMES THE SAME ONCE ITS QUALIFIER IS DROPPED\n"
            + "\n".join(f"  - {h['name']} ({h['country']})" for h in homonyms)
            + "\n"
            if homonyms
            else ""
        ),
        cache=cache_section(ctx),
        earlier=earlier_section(earlier),
        max_chars=SPOKEN_MAX_CHARS,
    )


@dataclass(frozen=True)
class Spoken:
    site_id: str
    verdict: str
    spoken: str | None
    from_form: str | None
    why: str


def parse_spoken(text: str, ctx: Mapping[str, Any]) -> Spoken:
    """The spoken answer in its exact shape; the spoken name derives from one attested form, is
    TTS-safe and short. Nothing is fetched."""
    data = A.load_object(text, SPOKEN_KEYS)
    if data["site_id"] != ctx["site_id"]:
        raise AnswerError(f"site_id {data['site_id']!r} is not this question's {ctx['site_id']}")
    verdict = data["verdict"]
    if verdict not in (SPEAK, NONE):
        raise AnswerError(f"verdict {verdict!r} is not SPEAK or NONE")
    why = A.text_of(data["why"], "why", max_chars=300)
    if verdict == NONE:
        if data["spoken"] is not None or data["from_form"] is not None:
            raise AnswerError("spoken and from_form are null for NONE")
        return Spoken(ctx["site_id"], NONE, None, None, why)
    spoken = A.text_of(data["spoken"], "spoken", max_chars=SPOKEN_MAX_CHARS)
    form = A.text_of(data["from_form"], "from_form")
    if form not in ctx["attested"]:
        raise AnswerError(f"from_form {form!r} is none of the attested forms {ctx['attested']}")
    if _fold(spoken) != _fold(form) and not _leaves_out_only_kinds(form, spoken):
        raise AnswerError(
            f"spoken {spoken!r} is not the attested form {form!r} respelled or shortened"
        )
    problems = tts_problems(spoken)
    if problems:
        raise AnswerError(f"spoken {spoken!r} is not TTS-safe: {'; '.join(problems)}")
    if spoken == ctx["name"]:
        raise AnswerError("spoken is the stored name - that is NONE")
    return Spoken(ctx["site_id"], SPEAK, spoken, form, why)


def _leaves_out_only_kinds(form: str, spoken: str) -> bool:
    """`spoken` is `form` with only droppable words (articles, kind words) left out and none added."""
    return names_triage.shortens(_ascii_words(form), _ascii_words(spoken)) and bool(_fold(spoken))


def _ascii_words(text: str) -> str:
    return " ".join(common.fold(text).split())


def decide_spoken(answer: Spoken, ctx: Mapping[str, Any], env: Env) -> Outcome:
    """Nothing to fetch: the answer is constrained to the record's own forms and was checked in
    `parse_spoken`."""
    return Outcome(
        DECIDED,
        "",
        {
            "verdict": answer.verdict,
            "spoken": answer.spoken,
            "from_form": answer.from_form,
            "why": answer.why,
        },
    )


def spoken_spec() -> StageSpec:
    return StageSpec(
        lane=LANE,
        stage=SPOKEN,
        role="web_verifier",
        render=render_spoken,
        parse=parse_spoken,
        decide=decide_spoken,
        cited=lambda a, c: set(),
        titles=lambda a, c: set(),
        per_batch=10,
        guidance="You do not research: choose among the attested forms the prompt lists.",
    )


def spoken_rows(
    rule: Sequence[Mapping[str, Any]],
    model: Mapping[str, Mapping[str, Any]],
    asked: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Every spoken name to write, by site: the rule-made ones and the decided model `SPEAK`s, each
    with the name it was made from (`asked` holds the contexts the model was asked with)."""
    out = {
        r["id"]: {
            "name": r["name"],
            "spoken": r["spoken"],
            "source": f"rule:{r['source']}",
            "why": f"names_triage: {r['name']!r} -> {r['spoken']!r} (steps {r['steps']}, from {r['source']})",
        }
        for r in rule
    }
    for sid, d in sorted(model.items()):
        if d["status"] == DECIDED and d["data"]["verdict"] == SPEAK:
            out[sid] = {
                "name": asked[sid]["name"],
                "spoken": d["data"]["spoken"],
                "source": f"model:{d['answered_by']}",
                "why": f"{d['data']['why']} (from the attested form {d['data']['from_form']!r})",
            }
    return out


def spoken_live_sql(site_ids: Sequence[str]) -> str:
    from mechanical.lane import sql_literal

    ids = ", ".join(f"{sql_literal(s)}::uuid" for s in sorted(site_ids))
    return (
        "SELECT u.id::text AS site_id, u.source_id, u.name, u.scope_status, u.spoken_name, "
        f"u.name AS premise FROM unified_sites u WHERE u.id IN ({ids}) ORDER BY u.id"
    )


@dataclass
class SpokenPlan:
    changes: list[MP.Verdict]
    skipped: list[dict[str, Any]]

    @property
    def sites(self) -> list[str]:
        return sorted({c.site_id for c in self.changes})


def build_spoken(
    rows: Mapping[str, Mapping[str, Any]], live: Mapping[str, Mapping[str, Any]]
) -> SpokenPlan:
    """`spoken_name` filled where it is NULL, for the sites whose name is still the one the spoken
    name was derived from. A site that already has one is left alone (the lane fills NULL)."""
    plan = SpokenPlan([], [])
    for sid in sorted(rows):
        row, now = rows[sid], live.get(sid)

        def skip(reason: str, note: str, _sid: str = sid, _name: str = row["name"]) -> None:
            plan.skipped.append({"site_id": _sid, "name": _name, "reason": reason, "note": note})

        if now is None:
            skip("gone", "the site is no longer in unified_sites")
        elif now["source_id"] != "ancient_nerds" or now["scope_status"] == "retired":
            skip("not-live", f"{now['source_id']} row, scope {now['scope_status']!r}")
        elif now["name"] != row["name"]:
            skip(
                "name-moved",
                f"the name is {now['name']!r} now, the spoken name was made from {row['name']!r}",
            )
        elif now["spoken_name"] is not None:
            skip("already-set", f"spoken_name is {now['spoken_name']!r}")
        elif row["spoken"] == now["name"]:
            skip("same-as-name", "the spoken name is the stored name")
        else:
            plan.changes.append(
                MP.Verdict(
                    site_id=sid,
                    site_name=str(now["name"]),
                    ok=True,
                    old_value=None,
                    new_value=row["spoken"],
                    rule="d23-spoken-name",
                    reason="",
                    note=row["why"],
                    phase3=False,
                    finding_test_id="D23/spoken-name",
                    evidence=({"source": row["source"], "url": "names", "quote": row["why"]},),
                    premise=str(now["premise"]),
                    column="spoken_name",
                )
            )
    return plan


def spoken_plan(plan: SpokenPlan, wave: str, built_at: str) -> MP.Plan:
    from identity.waves import SITES_PER_WAVE

    if len(plan.sites) > SITES_PER_WAVE:
        raise MP.PlanError(f"{len(plan.sites)} sites exceed one wave of {SITES_PER_WAVE}")
    return MP.Plan(
        tuple(plan.changes),
        (),
        built_at=built_at,
        counters={
            "sites": len(plan.sites),
            "cells": len(plan.changes),
            "skipped": len(plan.skipped),
        },
        lane=spoken_lane(wave),
    )
