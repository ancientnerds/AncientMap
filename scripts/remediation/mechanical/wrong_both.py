"""The wrong-both correction lane: the Opus re-verification's proposed values, where a machine-verified
verbatim quote carries them.

## Where it comes from

The Opus re-verification (`output/remediation/opus_audit/RULES.md`, sealed before its first
verdict) judged every DeepSeek-decided production row. A `wrong-both` verdict says the written value
is wrong and so was the old one, and names the right value. Rule 5: "wrong-both rows carry a
proposed value; it is not written by this audit. It goes to a later correction lane that writes only
with a machine-verified verbatim quote." journal-reversal-3 restored the old value of every final
revert (applied 2026-09-25); this lane writes the proposed value over it where the rules below hold,
and lists every other row with the reason it is not written.

The candidates are every `DECISIONS.jsonl` row whose route carries a `wrong-both` verdict
(`load_candidates`), with each route verdict read from the verdict file its `basis[].from` names -
refused where the decision and its verdict file disagree (the checks `reversal.load_opus` makes).

## How a row is decided (`classify`, the first failure is the reason; a refused row is listed)

1. **The final decision is revert** (`not-reverted`): a kept row keeps its written value.
2. **(a) The value is live at the old value journal-reversal-3 restored** - read-only from
   production: the site is curated (`row-not-in-curated-source`); the cell's journal is continuous
   and ends at the live value (`plan.journal_break`: `journal-chain-broken`, `journal-disagrees`);
   and its last link is a journal-reversal-3 row that wrote exactly the judged write's old value
   over its written value (`not-restored-by-journal-reversal-3` - a superseded row, restored by
   another lane or not at all, is one). With the chain ending at the live value, the live value is
   then the old one.
3. **(b) The judges agree** (`judges-disagree`): every counted verdict on the route that names a
   `right_value` names the same one. A `wrong-both` names its proposal; a `keep` that names one
   names the written value and a `revert` the old one, and either is a judge naming another value.
4. **(c) The value is valid for the field**: not the old value (`not-a-change`) nor the written one
   (`proposes-the-reverted-value`); a `site_type` is a canonical type and a fixed point of the
   pipeline's normalizer, `normalize_site_type(v) == v` (`not-a-site-type`; the canonical list is
   the lane's guard 4, and every type on it is a fixed point); a `period_start` is an
   integer year as the database prints it (`not-an-integer-year`), whose bucket the pipeline's
   `categorize_period` and the frontend's `categorizePeriod` agree on (`bucket-rules-disagree`) - the
   rule the period-name lane uses; a `country` is a spelling the census T05 predicate accepts, that
   resolves to an ISO code, and is never the United Kingdom spelled whole (the UK-parts rule, owner
   decision B9) (`not-the-country-convention`).
   A `period_start` whose bucket is not the site's live `period_name` writes the label with it: the
   label must hold a value (`period-name-empty`) and its journal must end at it
   (`period-name-journal-chain-broken`, `period-name-journal-disagrees`).
5. **(d) A verbatim quote carries the value** (`no-verbatim-evidence`): a quote of a counted verdict
   on the route, whose outcome in the audit's machine quote check (`opus_audit/quotes.py`) is
   `found`, that **states the value** (`states`) and **stands in text about the site**
   (`about_the_site`).

## What a quote must say (`states`)

* `site_type`: a run of consecutive words of the quote (letters, a `/` between two letters kept in
  the word) that the pipeline's own normalizer resolves to the value -
  `normalize_site_type(run) == value`: the canonical name in any case, or one of its synonyms
  ("statue" is a Monument, "hillfort" a Fort). "fortified" is no Fort, "memorial" no Monument,
  "sacred building" no Religious.
* `period_start`: the year with its era. For a year before Christ, its absolute value as a whole
  number (digits, thousands commas allowed; no digit, point or comma against it) followed by a BC
  marker - BC, BCE, B.C., B.C.E., a.C., a. C., v. Chr., av. J.-C., пр. Хр. - directly or after the
  rest of a range ("2500–2200 BC", "2000/1750–500 BC", "4000 and 1700 BCE"); for a year after
  Christ the same with AD, CE, A.D., C.E., d.C., d. C., n. Chr., ap. J.-C., or AD before it ("AD
  900"). A number without an era ("dating to 900"), a century or millennium ("5th century BC"),
  "years ago" and a year in the other era state nothing: they are listed for a human.
* `country`: the name standing whole, not inside a longer name the country vocabulary holds
  ("Ireland" in "Northern Ireland" is not Ireland).

**About the site**: a quote from one of the row's own evidence files (the pages the finder fetched
for this site; the audit's check accepts no other file) is about it. A quote from a fetched page is
about the site only when a distinctive word of the site's name - or the whole name - stands within
1,500 characters of it in the reading where the audit found it: the identity rule the coordinate
lane's web witnesses are held to (`bcases.web_witness.named_near`). A quote from a general article
("The Bronze Age in Great Britain spanned from c. 2500–2200 BC") states a year, but not the site's.

## Files

`--list` reads production (read-only) and writes `wrong_both_list.py` beside this module: the
journal-reversal-3 row of every cell a correction replaces - the lane's list (`lane.WRONG_BOTH`,
its residual). `--write` decides again, refuses unless its corrections follow exactly that list,
and writes `output/remediation/mechanical_wrong_both/`: `PLAN.jsonl`, `PLAN.md`, `SKIPPED.jsonl`
(every listed row with its reason), `ROLLBACK.sql`. `apply.py --lane wrong-both` renders and runs
it. Nothing here writes to production.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from bcases.web_witness import IDENTITY_WINDOW, named_near  # noqa: E402
from bcases.web_witness import normalise as page_normalise  # noqa: E402
from census.tests.t05_country_values import _is_canonical, _iso, _vocabulary  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from mechanical.apply import lane_dir, typed_value  # noqa: E402
from mechanical.lane import (  # noqa: E402
    REVERSAL_3,
    UK_PARTS,
    WRONG_BOTH,
    WRONG_BOTH_JOURNAL_IDS,
    sql_literal,
)
from mechanical.period_name import SITES_TS, frontend_rule  # noqa: E402
from mechanical.plan import (  # noqa: E402
    CURATED_SOURCE,
    JournalLink,
    Plan,
    PlanError,
    Verdict,
    _now,
    journal_break,
    psql_json_reader,
    sql_ids,
    write_plan_jsonl,
    write_rollback_sql,
    write_skipped_jsonl,
)
from mechanical.reversal import OPUS_AUDIT, OPUS_DECISIONS, OPUS_URL, _opus_verdict  # noqa: E402
from pipeline.normalizers.site_type import CANONICAL_TYPES, normalize_site_type  # noqa: E402
from pipeline.utils.text import categorize_period  # noqa: E402

LANE = WRONG_BOTH
LIST_MODULE = _HERE.parent / "wrong_both_list.py"
DECISIONS_PATH = "output/remediation/opus_audit/DECISIONS.jsonl"
RULE = "wrong-both-correction"
LABEL_RULE = "period-name-bucket"
#: The evidence entry that says how the quote carries the value.
RULE_SOURCE = "mechanical/wrong_both.py:states"
RULE_URL = "scripts/remediation/mechanical/wrong_both.py"
WRONG_BOTH_VERDICT, REVERT = "wrong-both", "revert"
SITE_TYPE, PERIOD_START, PERIOD_NAME, COUNTRY = (
    "site_type",
    "period_start",
    "period_name",
    "country",
)
EVIDENCE_FILE = "an evidence file of the row (fetched for this site)"


# ------------------------------------------------------------------------------ the candidates
@dataclass(frozen=True)
class Judge:
    """One verdict on a row's route: its pass, the file and section it came from, its verdict, the
    value it names as right, whether it counted, and each quote with the audit's check outcome."""

    stage: str
    origin: str
    verdict: str
    right_value: str | None
    counted: bool
    quotes: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class Candidate:
    """A decided row whose route carries a `wrong-both` verdict."""

    change_key: str
    site_id: str
    name: str
    column: str
    old_value: str
    written_value: str
    decision: str
    judges: tuple[Judge, ...]


def _judge(
    audit: Path, files: dict[str, Any], decided: Mapping[str, Any], basis: Mapping[str, Any]
) -> Judge:
    key = str(decided["change_key"])
    verdict = _opus_verdict(audit, files, basis["from"], key)
    if verdict["verdict"] != basis["verdict"]:
        raise PlanError(
            f"{OPUS_DECISIONS} reads {basis['verdict']!r} for {key}, "
            f"{basis['from']} holds {verdict['verdict']!r}"
        )
    checked = decided["quote_check"][basis["pass"]]["quotes"]
    if [c["source"] for c in checked] != [q["source"] for q in verdict["quotes"]]:
        raise PlanError(f"the quote check of {basis['from']} for {key} is not that verdict's")
    return Judge(
        stage=str(basis["pass"]),
        origin=str(basis["from"]),
        verdict=str(verdict["verdict"]),
        right_value=verdict.get("right_value") or None,
        counted=bool(basis["counted"]),
        quotes=tuple(
            (str(q["source"]), str(q["quote"]), str(c["outcome"]))
            for q, c in zip(verdict["quotes"], checked, strict=True)
        ),
    )


def load_candidates(audit: Path) -> list[Candidate]:
    """Every decided row whose route carries a `wrong-both` verdict, with its route's judges."""
    path = audit / OPUS_DECISIONS
    if not path.exists():
        raise PlanError(f"{path} is missing - the Opus re-verification's decisions")
    files: dict[str, Any] = {}
    seen: set[str] = set()
    out: list[Candidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        decided = json.loads(line)
        key = str(decided["change_key"])
        if key in seen:
            raise PlanError(f"{path.name} decides {key} twice")
        seen.add(key)
        judges = tuple(_judge(audit, files, decided, basis) for basis in decided["basis"])
        if not any(j.verdict == WRONG_BOTH_VERDICT for j in judges):
            continue
        out.append(
            Candidate(
                change_key=key,
                site_id=str(decided["site_id"]),
                name=str(decided["site_name"]),
                column=str(decided["column"]),
                old_value=str(decided["old_value"]),
                written_value=str(decided["written_value"]),
                decision=str(decided["decision"]),
                judges=judges,
            )
        )
    return out


# ------------------------------------------------------------------------------ production
@dataclass(frozen=True)
class State:
    """The candidates' sites (the lane's columns as text) and every journal row of their cells."""

    sites: Mapping[str, Mapping[str, Any]]
    chains: Mapping[tuple[str, str], tuple[JournalLink, ...]]

    def chain(self, site_id: str, column: str) -> tuple[JournalLink, ...]:
        return tuple(self.chains.get((site_id, column), ()))


def read_state(
    reader: Callable[[str], list[dict[str, Any]]], candidates: Sequence[Candidate]
) -> State:
    """The live sites and their cells' journals, read-only (`id IN ('...')`: the primary key)."""
    ids = sql_ids(c.site_id for c in candidates)
    values = ", ".join(f"{column}::text AS {column}" for column in LANE.columns)
    sites = {
        str(s["id"]): s
        for s in reader(
            f"SELECT id::text AS id, name, source_id, {values} FROM unified_sites "
            f"WHERE id IN ({ids})"
        )
    }
    columns = ", ".join(sql_literal(c) for c in sorted(LANE.columns))
    chains: dict[tuple[str, str], list[JournalLink]] = {}
    for row in reader(
        "SELECT id, row_pk, column_name, run_stamp, coalesce(test_id, '') AS test_id, old_value, "
        "new_value FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND column_name IN ({columns}) AND row_pk IN ({ids}) ORDER BY id"
    ):
        chains.setdefault((str(row["row_pk"]), str(row["column_name"])), []).append(
            JournalLink(
                int(row["id"]),
                str(row["run_stamp"]),
                str(row["test_id"]),
                row["old_value"],
                row["new_value"],
            )
        )
    return State(sites=sites, chains={key: tuple(links) for key, links in chains.items()})


# ------------------------------------------------------------------------------ what a quote states
_WORD = re.compile(r"[^\W\d_]+(?:/[^\W\d_]+)*")
#: The longest canonical type in words: no run of more words can resolve to a type (every synonym
#: of the normalizer is shorter - pinned by a test).
MAX_TERM_WORDS = max(len(_WORD.findall(t)) for t in CANONICAL_TYPES)

#: A whole number - thousands commas allowed - read from where `_DIGIT` says one starts.
_NUMBER = r"(?P<n>\d{1,3}(?:,\d{3})+|\d+)"
_RANGE = r"(?:\s?[–—\-/]\s?\d[\d,]*|\s(?:to|and)\s\d[\d,]*)*"
_BC = r"B\.\s?C\.\s?E\.|B\.\s?C\.|BCE|BC|a\.\s?C\.|v\.\s?Chr\.|av\.\s?J\.-C\.|пр\.\s?Хр\."
_AD = r"A\.\s?D\.|C\.\s?E\.|AD|CE|d\.\s?C\.|n\.\s?Chr\.|ap\.\s?J\.-C\."
_SUFFIX = re.compile(
    _NUMBER + _RANGE + r"\s?(?:(?P<bc>" + _BC + r")|(?P<ad>" + _AD + r"))(?![^\W\d_])"
)
_PREFIX = re.compile(r"(?<![^\W\d_])(?:A\.\s?D\.|AD)\s?" + _NUMBER)
#: Where a whole number starts: no digit, point or comma before it ("13700", "1.700", "1,700").
_DIGIT = re.compile(r"(?<![\d.,])\d")


def _states_type(value: str, text: str) -> str | None:
    words = _WORD.findall(text)
    for i in range(len(words)):
        for j in range(i + 1, min(len(words), i + MAX_TERM_WORDS) + 1):
            run = " ".join(words[i:j])
            if normalize_site_type(run) == value:
                return run
    return None


def _states_year(year: int, text: str) -> str | None:
    for digit in _DIGIT.finditer(text):
        match = _SUFFIX.match(text, digit.start())
        if match is None or int(match["n"].replace(",", "")) != abs(year):
            continue
        if (match["bc"] is not None) == (year < 0):
            return match.group(0)
    if year > 0:
        for match in _PREFIX.finditer(text):
            if int(match["n"].replace(",", "")) == year:
                return match.group(0)
    return None


def _states_country(value: str, text: str) -> str | None:
    codes, _normalize = country_vocabulary()
    for longer in sorted((k for k in codes if value in k and k != value), key=len, reverse=True):
        text = text.replace(longer, " " * len(longer))
    match = re.search(r"(?<![^\W_])" + re.escape(value) + r"(?![^\W_])", text)
    return None if match is None else match.group(0)


def states(column: str, value: str, text: str) -> str | None:
    """The words of `text` that state `value` for `column` (module docstring), or None."""
    if column == SITE_TYPE:
        return _states_type(value, text)
    if column == PERIOD_START:
        return _states_year(int(value), text)
    if column == COUNTRY:
        return _states_country(value, text)
    raise PlanError(f"{column!r} is not a column a wrong-both correction writes")


class Pages(Protocol):
    """What `about_the_site` reads a page with: `opus_audit.quotes.Library`."""

    def url(self, url: str) -> Q.Source: ...


def about_the_site(source: str, text: str, name: str, library: Pages) -> str | None:
    """How the quote is about the site, or None (module docstring). A page the audit found the quote
    on that cannot be read now, or no longer holds it, is refused: the plan cannot be checked."""
    if not Q.is_url(source):
        return EVIDENCE_FILE
    read = library.url(source)
    if read.failure:
        raise PlanError(
            f"{source} cannot be read ({read.failure}: {read.detail}) - the audit found "
            f"{text!r} there; the pages are `opus_audit/run.py fetch`'s"
        )
    wanted = Q.normalise(text)
    for _reading, hay in read.texts:
        if wanted in hay:
            word = named_near(
                page_normalise(hay).casefold(), page_normalise(wanted).casefold(), name
            )
            if word is None:
                return None
            return f"{word!r} stands within {IDENTITY_WINDOW:,} characters of it on the page"
    raise PlanError(f"{source} no longer holds {text!r}, which the audit's check found there")


# ------------------------------------------------------------------------------ the convention
@functools.cache
def country_vocabulary() -> tuple[dict[str, str], Callable[[str], str]]:
    """`COUNTRY_CODES` and `normalize_country`, the census T05 predicate's vocabulary."""
    return _vocabulary()


def country_problem(value: str, vocabulary: tuple[Mapping[str, str], Any]) -> str | None:
    """Why `value` is not a country of the dataset's convention, or None."""
    codes, normalize = vocabulary
    if not _is_canonical(value, dict(codes), normalize):
        return f"{value!r} is not a country spelling the project carries (census T05)"
    iso = _iso(value, normalize)
    if iso is None:
        return f"{value!r} resolves to no ISO code through normalize_country"
    if iso == "GB" and value not in UK_PARTS.allowed_new_values:
        return (
            f"{value!r} spells the United Kingdom whole; its parts are spelled by region "
            f"({', '.join(UK_PARTS.allowed_new_values)}; owner decision B9)"
        )
    return None


# ------------------------------------------------------------------------------ the decision
def named_values(c: Candidate) -> dict[str, list[str]]:
    """Each value a counted judge on the route names as right, with the passes that name it."""
    named: dict[str, list[str]] = {}
    for judge in c.judges:
        if judge.counted and judge.right_value:
            named.setdefault(judge.right_value, []).append(judge.stage)
    return named


@dataclass(frozen=True)
class Evidence:
    judge: Judge
    source: str
    text: str
    stated: str
    about: str


def find_evidence(c: Candidate, value: str, library: Pages) -> tuple[Evidence | None, str]:
    """The first found quote of a counted route verdict that states `value` and is about the site,
    or None and why none is."""
    stating: list[str] = []
    for judge in c.judges:
        if not judge.counted:
            continue
        for source, text, outcome in judge.quotes:
            if outcome != Q.FOUND:
                continue
            stated = states(c.column, value, text)
            if stated is None:
                continue
            about = about_the_site(source, text, c.name, library)
            if about is None:
                stating.append(source)
                continue
            return Evidence(judge, source, text, stated, about), ""
    if not stating:
        return (
            None,
            f"no counted quote states {value!r} (the audit's found quotes, read by `states`)",
        )
    return None, (
        f"{len(stating)} counted quote(s) state {value!r}, but none in text about the site (no "
        f"word of {c.name!r} within {IDENTITY_WINDOW:,} characters on the page): "
        + ", ".join(dict.fromkeys(stating))
    )


def classify(
    c: Candidate,
    st: State,
    *,
    library: Pages,
    vocabulary: tuple[Mapping[str, str], Any],
    frontend: Callable[[int], str | None],
) -> tuple[Verdict, ...]:
    """Decide one candidate: its correction (and a period label), or one refusal (module doc)."""
    site = st.sites.get(c.site_id)
    live = None if site is None else site.get(c.column)
    named = named_values(c)
    single = next(iter(named)) if len(named) == 1 else None
    finding = f"opus:{c.change_key}"
    name = c.name if site is None else str(site["name"])

    def refuse(reason: str, note: str) -> tuple[Verdict, ...]:
        return (
            Verdict(
                site_id=c.site_id,
                site_name=name,
                ok=False,
                old_value=live,
                new_value=single,
                rule=RULE,
                reason=reason,
                note=note,
                phase3=True,
                finding_test_id=finding,
                column=c.column,
            ),
        )

    if c.decision != REVERT:
        return refuse(
            "not-reverted",
            f"the audit's final decision is {c.decision!r}: the written value stands",
        )
    if site is None or site["source_id"] != CURATED_SOURCE:
        return refuse("row-not-in-curated-source", "not a curated site")
    chain = st.chain(c.site_id, c.column)
    broken = journal_break(chain, live)
    if broken is not None:
        return refuse(*broken)
    last = chain[-1] if chain else None
    if (
        last is None
        or last.run_stamp != REVERSAL_3.run_stamp
        or (last.old_value, last.new_value) != (c.written_value, c.old_value)
    ):
        what = "no journal row" if last is None else f"journal row {last.id} ({last.run_stamp})"
        return refuse(
            "not-restored-by-journal-reversal-3",
            f"the cell's last write is {what}, not journal-reversal-3 restoring "
            f"{c.old_value!r} over {c.written_value!r}",
        )
    if len(named) != 1:
        return refuse(
            "judges-disagree",
            "the counted judges name "
            + (
                ", ".join(f"{v!r} ({'/'.join(passes)})" for v, passes in named.items())
                or "no value"
            ),
        )
    value = next(iter(named))
    if value == c.old_value:
        return refuse("not-a-change", f"the judges name {value!r}, the value restored")
    if value == c.written_value:
        return refuse(
            "proposes-the-reverted-value", f"the judges name {value!r}, the write that was reverted"
        )
    label: tuple[str | None, str] | None = None
    if c.column == SITE_TYPE:
        # every canonical type is a fixed point of the normalizer (pinned by a test), so this is
        # `normalize_site_type(value) == value` without the pass-through of an unknown word
        if value not in CANONICAL_TYPES:
            return refuse(
                "not-a-site-type",
                f"{value!r} is not a canonical type (normalize_site_type gives "
                f"{normalize_site_type(value)!r})",
            )
    elif c.column == PERIOD_START:
        try:
            year = typed_value(LANE.cell(PERIOD_START), value)
        except PlanError as exc:
            return refuse("not-an-integer-year", str(exc))
        bucket = categorize_period(year)
        if frontend(year) != bucket:
            return refuse(
                "bucket-rules-disagree",
                f"categorize_period({year}) = {bucket!r}, the frontend's categorizePeriod "
                f"{frontend(year)!r}",
            )
        live_label = site.get(PERIOD_NAME)
        if live_label != bucket:
            if live_label is None:
                return refuse(
                    "period-name-empty",
                    f"period_start {value} needs the label {bucket!r}, and the row holds none to "
                    "condition the write on",
                )
            label_broken = journal_break(st.chain(c.site_id, PERIOD_NAME), live_label)
            if label_broken is not None:
                return refuse(f"period-name-{label_broken[0]}", label_broken[1])
            label = (live_label, str(bucket))
    else:
        problem = country_problem(value, vocabulary)
        if problem is not None:
            return refuse("not-the-country-convention", problem)
    evidence, why = find_evidence(c, value, library)
    if evidence is None:
        return refuse("no-verbatim-evidence", why)
    counted = [j for j in c.judges if j.counted]
    written = Verdict(
        site_id=c.site_id,
        site_name=name,
        ok=True,
        old_value=live,
        new_value=value,
        rule=RULE,
        reason="",
        note=f"the Opus re-verification's judges name {value!r} for {c.column} (RULES.md rule "
        f"5), and a verbatim quote of {evidence.judge.stage} states it",
        phase3=True,
        finding_test_id=finding,
        evidence=(
            {
                "source": f"remediation_change_log:{last.id}",
                "url": "remediation_change_log",
                "quote": f"{last.run_stamp}: {c.column} {c.written_value!r} -> {c.old_value!r} - "
                "the reversal of the judged write, which this correction follows",
            },
            {
                "source": finding,
                "url": OPUS_URL,
                "quote": "decision 'revert'; "
                + "; ".join(
                    f"{j.stage} {j.verdict}"
                    + (f" names {j.right_value!r}" if j.right_value else "")
                    + f" ({j.origin})"
                    for j in counted
                ),
            },
            {"source": evidence.source, "url": evidence.source, "quote": evidence.text},
            {
                "source": RULE_SOURCE,
                "url": RULE_URL,
                "quote": f"the quote of {evidence.judge.stage} ({evidence.judge.origin}), found by "
                f"the audit's machine check, states {evidence.stated!r}; it is about the site: "
                f"{evidence.about}",
            },
        ),
        column=c.column,
        journal_id=last.id,
    )
    if label is None:
        return (written,)
    old_label, bucket_label = label
    return (
        written,
        Verdict(
            site_id=c.site_id,
            site_name=name,
            ok=True,
            old_value=old_label,
            new_value=bucket_label,
            rule=LABEL_RULE,
            reason="",
            note=f"period_name follows period_start {value} (the period-name lane's rule)",
            phase3=False,
            finding_test_id=finding,
            evidence=(
                {
                    "source": "pipeline/utils/text.py:categorize_period",
                    "url": "pipeline/utils/text.py",
                    "quote": f"categorize_period({value}) = {bucket_label!r} - the period_start "
                    "this correction writes; the frontend's categorizePeriod agrees",
                },
            ),
            column=PERIOD_NAME,
        ),
    )


def build(
    candidates: Sequence[Candidate],
    st: State,
    *,
    library: Pages,
    vocabulary: tuple[Mapping[str, str], Any],
    frontend: Callable[[int], str | None],
    built_at: str,
) -> Plan:
    """A pure function of its inputs: no database, no network, no clock of its own."""
    verdicts = [
        v
        for c in sorted(candidates, key=lambda c: (c.site_id, c.column))
        for v in classify(c, st, library=library, vocabulary=vocabulary, frontend=frontend)
    ]
    changes = tuple(v for v in verdicts if v.ok)
    skipped = tuple(v for v in verdicts if not v.ok)
    return Plan(
        changes=changes,
        skipped=skipped,
        built_at=built_at,
        counters={
            "candidates": len(candidates),
            "corrections": sum(v.rule == RULE for v in changes),
            "labels": sum(v.rule == LABEL_RULE for v in changes),
            "listed": len(skipped),
        },
        lane=LANE,
    )


def followed_rows(plan: Plan) -> tuple[int, ...]:
    """The journal-reversal-3 rows the plan's corrections follow - the lane's list."""
    return tuple(sorted(int(str(v.journal_id)) for v in plan.changes if v.rule == RULE))


def listed_rows() -> tuple[int, ...]:
    """The list the lane was registered with (`wrong_both_list.py`, imported by `lane.py`)."""
    return WRONG_BOTH_JOURNAL_IDS


# ------------------------------------------------------------------------------ the files
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_list_module(ids: Sequence[int], digest: str) -> str:
    """`wrong_both_list.py`: the journal ids as generated code, 13 to a line."""
    lines = [
        '"""The journal rows the wrong-both corrections follow - generated, do not edit by hand.',
        "",
        "Written by `scripts/remediation/mechanical/wrong_both.py --list` from",
        f"`{DECISIONS_PATH}`",
        f"(sha256 {digest}).",
        "Each is the journal-reversal-3 row whose restored value a correction replaces.",
        '"""',
        "",
        "JOURNAL_IDS: tuple[int, ...] = (",
        *(
            "    " + " ".join(f"{i}," for i in ids[start : start + 13])
            for start in range(0, len(ids), 13)
        ),
        ")  # fmt: skip",
        "",
    ]
    return "\n".join(lines)


REFUSAL_MEANING = {
    "not-reverted": "the audit's final decision kept the written value",
    "row-not-in-curated-source": "the site is gone or not curated",
    "journal-chain-broken": "the cell's journal is not continuous",
    "journal-disagrees": "the cell's journal does not end at its live value",
    "not-restored-by-journal-reversal-3": "the cell's last write is not journal-reversal-3 "
    "restoring the old value (superseded rows: another lane wrote the cell)",
    "judges-disagree": "the counted judges name more than one value",
    "not-a-change": "the judges name the old value",
    "proposes-the-reverted-value": "the judges name the value that was reverted",
    "not-a-site-type": "not a canonical site type",
    "not-an-integer-year": "not an integer year",
    "bucket-rules-disagree": "the pipeline's and the frontend's bucket rules disagree",
    "period-name-empty": "the label to write with the start has no value to condition on",
    "period-name-journal-chain-broken": "the label's journal is not continuous",
    "period-name-journal-disagrees": "the label's journal does not end at it",
    "not-the-country-convention": "not a country of the dataset's convention",
    "no-verbatim-evidence": "no found quote of a counted judge states the value in text about "
    "the site - for a human",
}


def write_plan_md(plan: Plan, path: Path, *, digest: str) -> None:
    lane = plan.lane
    add = (lines := []).append
    add(f"# Wrong-both corrections - plan ({lane.name})")
    add("")
    add(
        f"Built {plan.built_at} by `scripts/remediation/mechanical/wrong_both.py` from "
        f"`{DECISIONS_PATH}` (sha256 {digest}). Lane `{lane.name}`: run stamp `{lane.run_stamp}`, "
        f"journal test id `{lane.test_id}`, change keys `{lane.key_prefix}:<site_id>:<column>`."
    )
    add("")
    counters = plan.counters
    add(
        f"**{len(plan.changes)} cell(s) will be written** - {counters['corrections']} "
        f"correction(s) and {counters['labels']} period label(s) - **{counters['listed']} of "
        f"{counters['candidates']} candidate(s) are listed, not written.** A candidate is a row "
        "the audit decided whose route carries a wrong-both verdict. Each write is conditioned on "
        "the live value being the old value journal-reversal-3 restored (guard 3)."
    )
    add("")
    add("The rules, the first failure listing the row, are in the module's docstring: (a) the old")
    add("value is live, restored by journal-reversal-3; (b) every counted judge that names a value")
    add("names this one; (c) the value is valid for its field; (d) a quote of a counted verdict,")
    add("found by the audit's machine check, states the value in text about the site.")
    add("")
    add("## Written")
    add("")
    for change in plan.changes:
        add(f"### {change.site_name} - `{change.column}` {change.old_value} -> {change.new_value}")
        add("")
        add(f"Site `{change.site_id}`. {change.note}.")
        add("")
        for e in change.evidence:
            add(f"* {e['source']}: {e['quote']}")
        add("")
    add("## Listed, not written")
    add("")
    add("| reason | rows | what it means |")
    add("|---|---|---|")
    for reason, count in sorted(Counter(v.reason for v in plan.skipped).items()):
        add(f"| `{reason}` | {count} | {REFUSAL_MEANING.get(reason, '')} |")
    add("")
    for v in plan.skipped:
        add(
            f"* {v.site_name} `{v.column}` {v.old_value} -> proposal {v.new_value}: "
            f"`{v.reason}` - {v.note}"
        )
    add("")
    add("## After the apply")
    add("")
    add(
        "The phase-3 acceptance reads these cells as superseded once it is told the stamp: "
        f"`verify_writes.py --allow-stamp {lane.run_stamp}`, with the stamps applied before it. "
        "Re-plan the scope lane and the card_stats recompute afterwards: the scope premise and the "
        "cards derive from these columns."
    )
    add("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def open_library(audit: Path) -> Q.Library:
    """The pages the audit fetched (`opus_audit/pages/`), read as its quote check read them."""
    return Q.Library(REPO, audit / "pages")


# ------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Plan the wrong-both corrections (mechanical lane)")
    ap.add_argument("--list", action="store_true", help="read production, write the lane's list")
    ap.add_argument("--write", action="store_true", help="read production, write the plan")
    ap.add_argument("--audit", type=Path, default=OPUS_AUDIT)
    ap.add_argument("--out", type=Path, help="the lane's directory unless given")
    ap.add_argument("--module", type=Path, default=LIST_MODULE)
    args = ap.parse_args(argv)
    if args.list and args.write:
        ap.error("--list and --write are two runs: the lane imports the list the plan is held to")
    if not (args.list or args.write):
        ap.print_help()
        return 0
    out = lane_dir(LANE) if args.out is None else args.out
    try:
        candidates = load_candidates(args.audit)
        plan = build(
            candidates,
            read_state(psql_json_reader(), candidates),
            library=open_library(args.audit),
            vocabulary=country_vocabulary(),
            frontend=frontend_rule(SITES_TS.read_text(encoding="utf-8")),
            built_at=_now(),
        )
        digest = sha256_file(args.audit / OPUS_DECISIONS)
        rows = followed_rows(plan)
        if args.list:
            args.module.write_text(render_list_module(rows, digest), encoding="utf-8", newline="\n")
        else:
            if rows != listed_rows():
                raise PlanError(
                    f"the corrections follow journal rows {list(rows)}, the lane lists "
                    f"{list(listed_rows())} - run --list first, then --write in a new run"
                )
            write_plan_jsonl(plan, out / "PLAN.jsonl")
            write_skipped_jsonl(plan, out / "SKIPPED.jsonl")
            write_plan_md(plan, out / "PLAN.md", digest=digest)
            write_rollback_sql(plan, out / "ROLLBACK.sql", plan_path=out / "PLAN.jsonl")
    except PlanError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({**plan.counters, "journal_rows": list(rows)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
