"""Phase 6 acceptance, sections 5-7 of the sealed protocol: the fields, the values, the questions.

`output/remediation/acceptance/PROTOCOL.md` fixes what a judge sees. Stage 1 (section 6) shows the
site's identity (name, country, point), the field's served value - the canary value where the draw
put one -, the field's row of section 5 and the plan's false-alarm patterns (section 4.3 of
`docs/procedures/SITES_DB_REMEDIATION_2026-09.md`), and nothing else: never the journal, remediation
evidence, provenance, another field's value, the canary key. Where a row names a vocabulary - "a
canonical type", "the bucket" - the vocabulary is shown with it (`definitions`), because the row
cannot be applied without it. Stage 2 (section 7) shows the claim - field, served value, proposed
value, class, and for a text field the disputed part - but not stage 1's sources or reasoning; stage
3 shows both reasonings.

**The texts are the sealed ones.** The rows are read from PROTOCOL.md, refused unless its LF bytes
hash to the seal (`PROTOCOL_SHA256`, SEAL.json); the patterns are cut from the plan and refused
unless they hash to `PATTERNS_SHA256`, so a later edit of the plan cannot change a question.

**A canary looks like every other question.** The canary value takes the place of the served value
and of the identity's country or point in that one question; the real value is asked in an extra
question of the same form. A point is printed with at most six decimals and no trailing zeros
(`coord`), the form the draw's shifted canary point has; a label is a digest of site, field and value
(`label_of`), so neither the label nor the file order says which question is which.

**No judge answers two questions of one site** (section 6): `batches` gives each field its own
batches, round-robin over the questions sorted by site, with at least as many batches as the field
asks one site - a canary site asks its canary field twice.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.normalizers.site_type import CANONICAL_TYPES
from pipeline.utils.text import PERIOD_BUCKETS

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
ACCEPTANCE = ROOT / "output" / "remediation" / "acceptance"
PROTOCOL = ACCEPTANCE / "PROTOCOL.md"
PLAN = ROOT / "docs" / "procedures" / "SITES_DB_REMEDIATION_2026-09.md"

#: PROTOCOL.md's LF bytes as sealed (SEAL.json, AUDIT_LOG 2026-09-25) - the rows come from it.
PROTOCOL_SHA256 = "f40fac87230a26e7b1a4818e9d50d16dedfcb6936fc795b532e2cb35789f8bff"
#: The plan's false-alarm patterns 1-11 (section 4.3) as cut by `false_alarm_patterns`, LF.
PATTERNS_SHA256 = "011279e1d7aabc0bfb336d575526f8d5b8c1c2aa717f4a3ec3a13ad98fa8ced6"

#: The three classes of section 5, lowest first.
SEVERITIES = ("cosmetic", "moderate", "severe")
TEXT_FIELDS = frozenset({"description", "card_description"})


class QuestionError(ValueError):
    """A question that must not be asked. Nothing was written."""


@dataclass(frozen=True)
class Field:
    """One judged field of section 5: its number, its key, its title in the table, its classes."""

    number: str
    key: str
    title: str
    severities: tuple[str, ...]
    #: Questions per batch: the text fields need every claim quoted, so their batches are smaller.
    batch_size: int = 15


FIELDS: tuple[Field, ...] = (
    Field("F1", "name", "name", ("cosmetic", "severe")),
    Field("F2", "country", "country", ("severe",)),
    Field("F3", "coordinates", "coordinates", ("moderate", "severe")),
    Field("F4", "site_type", "site_type", ("moderate",)),
    Field("F5", "period_start", "period_start", ("moderate", "severe")),
    Field("F6", "period_name", "period_name", ("moderate",)),
    Field("F7", "description", "description", ("severe",), batch_size=6),
    Field("F8", "card_description", "card_description", ("severe",), batch_size=10),
    Field("F9", "scope", "scope", ("severe",)),
    Field("F10", "served_image", "served image", ("moderate", "severe")),
    Field("F11", "source_url", "source_url", ("moderate",)),
)
FIELD_BY_KEY = {field.key: field for field in FIELDS}
#: The draw's canary fields (`draw.CANARY_PLAN`) and the question each one replaces.
CANARY_FIELDS = {"country": "country", "coordinates": "coordinates"}


# ------------------------------------------------------------------------------ the sealed texts
def _lf_text(path: Path) -> str:
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


@dataclass(frozen=True)
class Row:
    """A field's row of PROTOCOL.md section 5."""

    number: str
    title: str
    right: str
    wrong: str


_ROW = re.compile(r"\| (F\d+) \| (.+?) \| (.+?) \| (.+?) \|")


def protocol_rows(text: str) -> dict[str, Row]:
    rows: dict[str, Row] = {}
    for line in text.split("\n"):
        match = _ROW.fullmatch(line)
        if match:
            rows[match[1]] = Row(*match.groups())
    if list(rows) != [field.number for field in FIELDS]:
        raise QuestionError(f"section 5 lists {list(rows)}, not the eleven fields")
    for field in FIELDS:
        if rows[field.number].title != field.title:
            raise QuestionError(
                f"{field.number} is {rows[field.number].title!r}, not {field.title}"
            )
    return rows


def read_protocol(path: Path = PROTOCOL) -> dict[str, Row]:
    """Section 5's rows, from the sealed protocol only."""
    text = _lf_text(path)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != PROTOCOL_SHA256:
        raise QuestionError(f"{path} is not the sealed protocol (sha256 {digest})")
    return protocol_rows(text)


def false_alarm_patterns(plan: str) -> str:
    """The numbered list of the plan's section 4.3, verbatim: from its `1. ` to the blank line."""
    lines = plan.split("\n")
    heading = next(i for i, line in enumerate(lines) if line.startswith("### 4.3 "))
    start = next(i for i in range(heading, len(lines)) if lines[i].startswith("1. "))
    end = start
    while end < len(lines) and lines[end].strip():
        end += 1
    return "\n".join(lines[start:end])


def read_patterns(path: Path = PLAN) -> str:
    patterns = false_alarm_patterns(_lf_text(path))
    digest = hashlib.sha256(patterns.encode("utf-8")).hexdigest()
    if digest != PATTERNS_SHA256:
        raise QuestionError(f"the plan's false-alarm patterns changed (sha256 {digest})")
    return patterns


# --------------------------------------------------------------------------------- the values
def coord(value: float) -> str:
    """A coordinate at most six decimals long, without trailing zeros - the canary point's form."""
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def point(lat: float, lon: float) -> str:
    return f"{coord(lat)}, {coord(lon)}"


def canary_point(value: str) -> str:
    """The draw's `"lat,lon"` canary value in the form every point is shown in."""
    lat, lon = (float(part) for part in value.split(","))
    return point(lat, lon)


def _scope(status: Any, reason: Any) -> str:
    if status == "retired":
        raise QuestionError("a retired site is not shown and never drawn")
    shown = status or "empty (never assessed; the site counts as in scope)"
    text = f"shown on the public map; scope_status: {shown}"
    return f"{text}; scope_reason: {reason}" if reason else text


def _image(image: Mapping[str, Any]) -> str:
    parts = [
        f"{what}: {image[key]}"
        for what, key in (
            ("title", "title"),
            ("Commons file page", "commons_page_url"),
            ("image file", "original_url"),
        )
        if image.get(key)
    ]
    if not parts:
        raise QuestionError(f"served image {image.get('id')} names no title and no page")
    return "\n".join(parts)


_COLUMNS = {
    "name": "name",
    "country": "country",
    "site_type": "site_type",
    "period_name": "period_name",
    "description": "description",
    "card_description": "card_description",
    "source_url": "source_url",
}


def served_value(field: str, site: Mapping[str, Any]) -> str | None:
    """The field's served value as the judge sees it, or None when the field is empty."""
    if field == "coordinates":
        lat, lon = site.get("lat"), site.get("lon")
        return None if lat is None or lon is None else point(lat, lon)
    if field == "period_start":
        year = site.get("period_start")
        if year is None:
            return None
        if isinstance(year, bool) or not isinstance(year, int):
            raise QuestionError(f"{site['site_id']}: period_start {year!r} is not an integer")
        return str(year)
    if field == "scope":
        return _scope(site.get("scope_status"), site.get("scope_reason"))
    if field == "served_image":
        image = site.get("served_image")
        return _image(image) if image else None
    value = site.get(_COLUMNS[field])
    if value is None or not str(value).strip():
        return None
    return str(value)


# ------------------------------------------------------------------------------ the questions
@dataclass(frozen=True)
class Question:
    """One stage-1 question: the field of one site with the value shown and the identity shown."""

    label: str
    site_id: str
    field: str
    value: str
    name: str
    country: str
    point: str


def label_of(site_id: str, field: str, value: str) -> str:
    digest = hashlib.sha256(f"{site_id}\n{field}\n{value}".encode()).hexdigest()
    return f"q{digest[:16]}"


def _question(site: Mapping[str, Any], field: str, value: str) -> Question:
    lat, lon = site.get("lat"), site.get("lon")
    shown_point = "(empty)" if lat is None or lon is None else point(lat, lon)
    return Question(
        label=label_of(str(site["site_id"]), field, value),
        site_id=str(site["site_id"]),
        field=field,
        value=value,
        name=str(site["name"]),
        country=value if field == "country" else str(site.get("country") or "(empty)"),
        point=value if field == "coordinates" else shown_point,
    )


def _canary_values(
    sample: Sequence[Mapping[str, Any]], canaries: Sequence[Mapping[str, Any]]
) -> dict[tuple[str, str], str]:
    by_id = {str(site["site_id"]): site for site in sample}
    values: dict[tuple[str, str], str] = {}
    for canary in canaries:
        site_id, field = str(canary["site_id"]), str(canary["field"])
        if site_id not in by_id:
            raise QuestionError(f"canary {site_id} is not a drawn site")
        if field not in CANARY_FIELDS:
            raise QuestionError(f"canary {site_id}: field {field!r} is no canary field")
        key = CANARY_FIELDS[field]
        stored = served_value(key, by_id[site_id])
        if field == "country":
            true, value = canary["true_stored"], canary["canary_value"]
        else:
            true, value = canary_point(canary["true_stored"]), canary_point(canary["canary_value"])
        if stored is None or true != stored or value == stored or (site_id, key) in values:
            raise QuestionError(f"canary {site_id}/{field} does not fit the stored value")
        values[(site_id, key)] = value
    return values


def stage1_questions(
    sample: Sequence[Mapping[str, Any]], canaries: Sequence[Mapping[str, Any]]
) -> list[Question]:
    """Every non-empty field of every drawn site; a canary field asked twice, sorted by label."""
    canary = _canary_values(sample, canaries)
    questions: list[Question] = []
    for site in sample:
        for field in FIELDS:
            value = served_value(field.key, site)
            if value is None:
                continue
            questions.append(_question(site, field.key, value))
            planted = canary.get((str(site["site_id"]), field.key))
            if planted is not None:
                questions.append(_question(site, field.key, planted))
    labels = [q.label for q in questions]
    if len(set(labels)) != len(labels):
        raise QuestionError("two questions carry one label")
    return sorted(questions, key=lambda q: q.label)


def batches(questions: Sequence[Question], prefix: str) -> list[tuple[str, list[Question]]]:
    """One field per batch, at most its batch size, never two questions of one site."""
    out: list[tuple[str, list[Question]]] = []
    for field in FIELDS:
        asked = sorted(
            (q for q in questions if q.field == field.key), key=lambda q: (q.site_id, q.label)
        )
        if not asked:
            continue
        most = max(Counter(q.site_id for q in asked).values())
        count = max(math.ceil(len(asked) / field.batch_size), most)
        groups: list[list[Question]] = [[] for _ in range(count)]
        for position, question in enumerate(asked):
            groups[position % count].append(question)
        for number, group in enumerate(groups, start=1):
            if len({q.site_id for q in group}) != len(group):
                raise QuestionError(f"batch {prefix}-{field.key}-{number} asks one site twice")
            out.append((f"{prefix}-{field.key}-{number:02d}", group))
    return out


# -------------------------------------------------------------------------------- the prompts
def _buckets() -> str:
    spans = []
    for name, low, high in PERIOD_BUCKETS:
        if low == PERIOD_BUCKETS[0][1]:
            spans.append(f"`{name}`: before {high}")
        elif high == PERIOD_BUCKETS[-1][2]:
            spans.append(f"`{name}`: {low} and later")
        else:
            spans.append(f"`{name}`: {low} up to but not including {high}")
    return "; ".join(spans)


def definitions(field: str) -> str:
    """The vocabulary a row names, or "" - the row cannot be applied without it."""
    if field == "site_type":
        types = ", ".join(f"`{name}`" for name in CANONICAL_TYPES)
        return f"The canonical types - the only values this field can hold: {types}."
    if field == "period_start":
        return (
            "The value is a year, negative for BC. The buckets, each from its first year up to but "
            f"not including its second: {_buckets()}."
        )
    if field == "period_name":
        return f"The buckets, by the year of the site's attested start: {_buckets()}."
    if field == "scope":
        return (
            "scope_status: empty = never assessed, shown as in scope; `in_scope` = assessed and "
            "kept; `pending` = assessment open, still shown."
        )
    return ""


RIGHT_VALUE = {
    "name": "the name reputable sources give this site",
    "country": "the country the site lies in",
    "coordinates": 'the site\'s point as "lat, lon" in decimal degrees, for example '
    '"51.178882, -1.826215"; more than 5 km from the served point is "severe", 1-5 km is '
    '"moderate" unless the served point is another place, and less than 1 km is not wrong',
    "site_type": "the canonical type (one of the list above) that holds what the sources describe",
    "period_start": "a year, negative for BC, in the bucket of the site's securely attested start, "
    'for example "-1500"; one bucket from the served value\'s bucket is "moderate", two or more '
    'is "severe", and the same bucket is not wrong',
    "period_name": "the bucket (one of the list above) of the site's attested start",
    "description": "the corrected statement of the contradicted claim",
    "card_description": "the corrected statement of the contradicted claim",
    "scope": "the site's attested start, and why it lies outside the E3 window",
    "served_image": "what the image shows instead (a site, a place or an object)",
    "source_url": "what the served page is about instead, or a page that is about this site",
}


def _severity_words(classes: Sequence[str]) -> str:
    return ", ".join(f'"{name}"' for name in classes)


def _head(question: Question, rows: Mapping[str, Row], patterns: str) -> str:
    field = FIELD_BY_KEY[question.field]
    row = rows[field.number]
    vocabulary = definitions(question.field)
    return (
        "You are an independent judge in the final acceptance test of a curated database of "
        "ancient sites. This question is about ONE field of ONE site.\n"
        "\n"
        "## The site\n"
        "\n"
        f"- name: {question.name}\n"
        f"- country: {question.country}\n"
        f"- point: {question.point} (latitude, longitude in decimal degrees)\n"
        "\n"
        f"## The field: {field.number} {field.title}\n"
        "\n"
        "The value the database serves:\n"
        "\n"
        "<<<\n"
        f"{question.value}\n"
        ">>>\n"
        "\n"
        f"The served value is right when: {row.right}\n"
        "\n"
        f"Wrong, and its severity: {row.wrong}\n"
        + (f"\n{vocabulary}\n" if vocabulary else "")
        + "\n"
        "## False alarms - these patterns are not errors\n"
        "\n"
        "Claims of these kinds were checked before and refuted; a verdict must not rest on one:\n"
        "\n"
        f"{patterns}\n"
    )


RESEARCH = (
    "## How to research\n"
    "\n"
    "- Research on the web yourself: search, then read reputable pages - heritage agencies and "
    "national monument registers, UNESCO, museums, universities, scholarly publications, "
    "established encyclopedias, Wikipedia and Wikidata.\n"
    "- Before any verdict, make sure each source is about this very site: its name AND its place.\n"
    "- Sources are independent only when they come from different source families. One Wikipedia "
    "article (in any language), its Wikidata item and Wikimedia Commons are ONE source family; all "
    "pages of one website or one publisher are ONE source family; a page that copies another is "
    "not independent of it.\n"
    "\n"
    "## Quotes are checked by machine\n"
    "\n"
    "Each quote is looked up in the page at its URL, fetched once with a plain HTTP GET (no "
    "script, no login). It counts only when its exact text occurs verbatim in the page's visible "
    "text: runs of whitespace are forgiven, nothing else - case, punctuation, quotation marks, "
    "dashes, diacritics and footnote markers must be as on the page. Copy one contiguous passage "
    "of the page: not a search snippet, a summary, a translation or an excerpt joined with "
    "'...'. If your page-reading tool summarises, confirm the exact words from the page itself "
    "before you quote them. A page that refuses automated requests or needs a script to show its "
    "text cannot be checked - cite another. A verdict with a quote that is not found does not "
    "count.\n"
)


def _claim_rule(field: str) -> str:
    if field in TEXT_FIELDS:
        return (
            '"claim" (the part of the served text this quote supports or contradicts, copied '
            "exactly from the served text)"
        )
    return '"claim": null'


def stage1_prompt(question: Question, rows: Mapping[str, Row], patterns: str) -> str:
    field = FIELD_BY_KEY[question.field]
    text_field = question.field in TEXT_FIELDS
    correct = (
        "every factual claim of the served text is supported by a verbatim quote from a source, "
        "and the quotes come from at least two independent source families; every sentence of "
        "the served text must contain (or overlap) at least one claim you list"
        if text_field
        else "at least two independent sources support the served value, each with a verbatim quote"
    )
    return (
        _head(question, rows, patterns) + "\n" + RESEARCH + "\n"
        "## Verdicts\n"
        "\n"
        f"- CORRECT: {correct}.\n"
        "- WRONG: a source contradicts the served value - give the contradicting verbatim quote "
        "with its URL, the right value, and the severity class from the row above.\n"
        "- UNVERIFIABLE: the sources do not decide it. Silence is not agreement.\n"
        "\n"
        "## Your answer\n"
        "\n"
        "Answer with one JSON object and nothing else - no code fence, no text before or after it "
        '- with exactly the keys "verdict", "quotes", "right_value", "severity", "reasoning":\n'
        "\n"
        '- "verdict": "CORRECT", "WRONG" or "UNVERIFIABLE".\n'
        '- "quotes": a list of objects with exactly the keys "url" (the page, http or https), '
        f'"quote" (verbatim text of that page) and {_claim_rule(question.field)}. CORRECT: at '
        "least two quotes from at least two independent source families. WRONG: at least one "
        "quote that contradicts the served value. UNVERIFIABLE: an empty list.\n"
        f'- "right_value": for WRONG, {RIGHT_VALUE[question.field]}; it must differ from the '
        "served value. Otherwise null.\n"
        f'- "severity": one of {_severity_words(field.severities)}. Only for WRONG, as the row '
        "above defines the classes; otherwise null.\n"
        '- "reasoning": a few sentences - what the sources say and why the verdict follows.\n'
    )


@dataclass(frozen=True)
class Claim:
    """What stage 2 is shown of a stage-1 WRONG: the proposal, its class, the disputed part."""

    right_value: str
    severity: str
    disputed: tuple[str, ...]


@dataclass(frozen=True)
class Reasoning:
    """A counted answer as the third judge is shown it."""

    reasoning: str
    quotes: tuple[tuple[str, str], ...]


def _claim_block(claim: Claim) -> str:
    disputed = "".join(f"- {part}\n" for part in claim.disputed)
    return (
        "## The claim\n"
        "\n"
        "Another judge claims the served value is wrong.\n"
        "\n"
        + (f"The disputed part of the served text:\n\n{disputed}\n" if disputed else "")
        + f"Proposed right value: {claim.right_value}\n"
        f"Claimed severity: {claim.severity}\n"
    )


def _severity_rule(question: Question, claim: Claim) -> str:
    field = FIELD_BY_KEY[question.field]
    lower = [s for s in field.severities if SEVERITIES.index(s) < SEVERITIES.index(claim.severity)]
    if not lower:
        return '"severity" and "severity_reason" are null.'
    return (
        f'"severity" is null to keep the claimed class, or a lower class of this field (one of '
        f'{_severity_words(lower)}) with "severity_reason" saying why.'
    )


def stage2_prompt(question: Question, claim: Claim, rows: Mapping[str, Row], patterns: str) -> str:
    return (
        _head(question, rows, patterns) + "\n" + _claim_block(claim) + "\n" + RESEARCH + "\n"
        "## Verdicts\n"
        "\n"
        "- CONFIRMED: the served value is wrong as claimed - quote at least one source that "
        "contradicts it.\n"
        "- REFUTED: the served value is right, or the claim is one of the false-alarm patterns "
        '(name its number in "pattern").\n'
        "- UNDECIDED: you cannot decide it.\n"
        "\n"
        "## Your answer\n"
        "\n"
        "Answer with one JSON object and nothing else - no code fence, no text before or after it "
        '- with exactly the keys "verdict", "quotes", "severity", "severity_reason", "pattern", '
        '"reasoning":\n'
        "\n"
        '- "verdict": "CONFIRMED", "REFUTED" or "UNDECIDED".\n'
        '- "quotes": a list of objects with exactly the keys "url" (http or https) and "quote" '
        "(verbatim text of that page). CONFIRMED: at least one. REFUTED: optional, and every "
        "quote given is checked. UNDECIDED: an empty list.\n"
        f"- For CONFIRMED, {_severity_rule(question, claim)} For REFUTED and UNDECIDED, "
        '"severity" and "severity_reason" are null.\n'
        '- "pattern": for REFUTED, the number (1-11) of the false-alarm pattern the claim is, or '
        "null; otherwise null.\n"
        '- "reasoning": a few sentences - what the sources say and why the verdict follows.\n'
    )


def _reasoning_block(title: str, answer: Reasoning | None) -> str:
    if answer is None:
        return f"### {title}\n\nThis judge gave no counted answer.\n"
    quotes = "".join(f'- {url}: "{quote}"\n' for url, quote in answer.quotes)
    return f"### {title}\n\n{answer.reasoning}\n" + (f"\nQuotes:\n\n{quotes}" if quotes else "")


def stage3_prompt(
    question: Question,
    claim: Claim,
    first: Reasoning,
    second: Reasoning | None,
    rows: Mapping[str, Row],
    patterns: str,
) -> str:
    return (
        _head(question, rows, patterns) + "\n" + _claim_block(claim) + "\n"
        "## The two judges before you\n"
        "\n"
        "The first judge made the claim; the second could not decide it. Their reasonings:\n"
        "\n"
        + _reasoning_block("The first judge", first)
        + "\n"
        + _reasoning_block("The second judge", second)
        + "\n"
        + RESEARCH
        + "\n"
        "## Verdicts\n"
        "\n"
        "Decide it: CONFIRMED (the served value is wrong as claimed - quote at least one source "
        "that contradicts it) or REFUTED (the served value is right, or the claim is one of the "
        "false-alarm patterns).\n"
        "\n"
        "## Your answer\n"
        "\n"
        "Answer with one JSON object and nothing else - no code fence, no text before or after it "
        '- with exactly the keys "verdict", "quotes", "reasoning": "verdict" is "CONFIRMED" or '
        '"REFUTED"; "quotes" is a list of objects with exactly the keys "url" and "quote" (at '
        'least one for CONFIRMED; every quote given is checked); "reasoning" says why.\n'
    )
