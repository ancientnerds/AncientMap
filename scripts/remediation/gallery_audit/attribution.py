"""Backfill `author` / `author_url` of curated CC BY* images from the Commons file page itself.

The defect (design entry 7, item 11, measured 2026-09-22/23): 1,021 live images carry no author,
527 of them under a CC BY* licence, whose attribution requirement then rests on the licence and a
link alone. Only 3 of those 527 have an `Artist` value in the cached `extmetadata` - which is why the
original downloader (`parse_attribution`, `Artist` only) left them empty.

Four routes, tried in this order, each on the file page as Commons serves it today (one batched
`imageinfo` + `revisions` request per 50 files, so the metadata and the wikitext are one moment):

    A1  extmetadata `Artist`       - the field `parse_attribution` has always read
    A2  extmetadata `Attribution`  - the licensor's own "attribute me as" line
    A3  extmetadata `Credit` with the own-work marker (`class="int-own-work"`) and exactly one
        link to a user page - the uploader is the author, and the link names them
    A4  the file page wikitext, `{{Information|author=...}}`, when the value is exactly one user
        link, one external link, or plain text - parsed deterministically, never interpreted

A route whose field is absent moves on to the next. A route whose field is present but cannot be
read exactly (two user links, a template, a replacement character, more than 200 characters, a
non-name such as "Own work") ends the row as UNRESOLVED with that reason: a wrong credit is worse
than none (feedback_no_ai_slop), so nothing is guessed and every refusal is listed.

Every author is `parse_attribution` of the span it came from (for A4, of the one link or text the
wikitext names, rendered as the anchor Commons renders it), so this lane and the downloader cannot
spell an author two ways. Each resolved row has one line in `EVIDENCE.jsonl`: the file page revid,
the exact span, its sha256, when it was fetched and the sha256 of the whole API answer. The journal
evidence carries pointers only - that line's sha256, the revid, the rule.

The writes are `chunk_writer` chunks of 100 sites (`author` and, where the span names one and the
row has none, `author_url`); only rows whose `author` is still NULL or empty are touched.

Usage:
    attribution.py --plan      # production SELECT + Commons GETs; writes EVIDENCE.jsonl,
                               # UNRESOLVED.jsonl, PLAN.md and the chunks
    attribution.py --recheck   # re-fetches every cited page and re-derives every planned author
    chunk_writer.py <attribution dir>/chunk-NNN --check|--rehearse|--apply|--readback|
                                                 --rehearse-rollback
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation", _HERE.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import chunk_writer as CW  # noqa: E402
import persist_verdicts as pv  # noqa: E402
from census.fetch import Fetcher  # noqa: E402
from census.tests.t09_commons_dimensions import (  # noqa: E402
    COMMONS_API,
    _commons_file_name,
    _dereference,
)

from pipeline.wiki_image_downloader import parse_attribution  # noqa: E402

DATE = "2026-09-23"
OUT = ROOT / "output" / "remediation" / "gallery_audit" / f"attribution-{DATE}"
CACHE = ROOT / "output" / "remediation" / "cache"
CACHE_NS = "attribution"
BATCH = 50
PAUSE_S = 1.0  # Wikimedia robot policy: one request per second, serial
LANE = CW.Lane(
    "img-attrib", "T09/attribution", f"img-attrib-{DATE}", "authoritative", "img attribution"
)
FIELDS = ("Artist", "Attribution", "Credit")
MAX_AUTHOR = 200  # parse_attribution cuts longer values to 200 + "...": no longer the source's text
#: Values of an author field that name nobody. Compared case-folded, after the span is read.
NOT_A_NAME = frozenset({"unknown", "anonymous", "own work", "self", "author", "see below", "n/a"})
_ENTITY = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#x[0-9A-Fa-f]+);")

SCOPE_SQL = """SELECT row_to_json(t) FROM (
  SELECT w.id, w.site_id::text AS site_id, w.author, w.author_url, w.license,
         w.original_url, w.commons_page_url
    FROM wiki_images w JOIN unified_sites s ON s.id = w.site_id
   WHERE s.source_id = 'ancient_nerds' AND w.is_excluded IS NOT TRUE
     AND (w.author IS NULL OR w.author = '') AND w.license LIKE 'CC BY%'
   ORDER BY w.site_id, w.id
) t;"""


class AttributionError(RuntimeError):
    """The lane cannot continue from what it was given. Never downgraded to a skip."""


# ------------------------------------------------------------------------------ the records
@dataclass(frozen=True)
class Row:
    """One production row in scope, as the plan read it."""

    id: int
    site_id: str
    author: str | None
    author_url: str | None
    license: str
    original_url: str | None
    commons_page_url: str | None

    @property
    def file_name(self) -> str | None:
        return _commons_file_name(
            {"original_url": self.original_url, "commons_page_url": self.commons_page_url}
        )


@dataclass(frozen=True)
class Page:
    """One Commons file page as the batch answer carried it."""

    title: str
    revid: int
    timestamp: str
    wikitext: str
    extmetadata: dict[str, str]
    retrieved_at: str
    response_sha256: str


@dataclass(frozen=True)
class Found:
    """An author read from one span of one page, by one route."""

    rule: str
    field: str
    span: str
    html: str
    author: str
    author_url: str | None


@dataclass(frozen=True)
class Refused:
    """The route's field is present, but it cannot be read exactly."""

    rule: str
    reason: str
    span: str


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False))


# ----------------------------------------------------------------------------- the routes
def _read(rule: str, field: str, span: str, markup: str) -> Found | Refused:
    """parse_attribution of `markup`, or the reason its author is not exactly the source's."""
    parsed = parse_attribution({"extmetadata": {"Artist": {"value": markup}}})
    author, url = parsed["author"], parsed["author_url"]
    if not author:
        return Refused(rule, "the span names no one once its markup is read", span)
    if "\N{REPLACEMENT CHARACTER}" in author:
        return Refused(rule, "the span carries a replacement character (a broken encoding)", span)
    if len(author) > MAX_AUTHOR:
        return Refused(rule, f"longer than {MAX_AUTHOR} characters - it would be cut", span)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in author):
        return Refused(rule, "the author text carries a control character", span)
    if author.strip().casefold().rstrip(".") in NOT_A_NAME:
        return Refused(rule, f"{author!r} names no one", span)
    # parse_attribution strips tags but decodes no entity: `&amp;` would be stored literally, and
    # a redlink's `...&amp;action=edit` would become a link that is not the page's
    if any(_ENTITY.search(text) for text in (author, url or "")):
        return Refused(rule, "the span carries an HTML entity parse_attribution does not decode", span)
    if url is not None and not re.fullmatch(r"https?://[^\s\"'<>]+", url):
        return Refused(rule, f"the link {url!r} is not a plain web address", span)
    return Found(rule, field, span, markup, author, url)


def route_field(page: Page, field: str, rule: str) -> Found | Refused | None:
    """A1/A2: an extmetadata field, read as `parse_attribution` reads `Artist`."""
    value = page.extmetadata.get(field)
    if value is None or not re.sub(r"<[^>]*>", "", value).strip():
        return None
    return _read(rule, field, value, value)


_ANCHOR = re.compile(r"<a\s[^>]*?href=\"([^\"]+)\"[^>]*>(.*?)</a>", re.S)
_USER_PAGE = re.compile(
    r"(?:https:)?//(?:commons\.wikimedia\.org|[a-z-]{2,12}\.wikipedia\.org)/wiki/User:[^\"/?#&]+"
)


def route_credit_own_work(page: Page) -> Found | None:
    """A3: an own-work Credit with exactly one user-page link - the uploader, named by the link."""
    credit = page.extmetadata.get("Credit") or ""
    if 'class="int-own-work"' not in credit:
        return None
    users = [m for m in _ANCHOR.finditer(credit) if _USER_PAGE.fullmatch(m.group(1))]
    if len(users) != 1:
        return None
    anchor = users[0].group(0)
    found = _read("A3", "Credit", anchor, anchor)
    return found if isinstance(found, Found) else None


def _template_body(text: str, start: int) -> str | None:
    """The text between `{{` at `start` and its matching `}}`, or None if it never closes."""
    depth, i = 0, start
    while i < len(text) - 1:
        pair = text[i : i + 2]
        if pair == "{{":
            depth += 1
            i += 2
            continue
        if pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return text[start + 2 : i - 2]
            continue
        i += 1
    return None


def _parameters(body: str) -> list[str]:
    """The `|`-separated parameters of a template body, ignoring `|` inside [[...]] and {{...}}."""
    out, depth, current, i = [], 0, [], 0
    while i < len(body):
        pair = body[i : i + 2]
        if pair in ("{{", "[["):
            depth += 1
            current.append(pair)
            i += 2
            continue
        if pair in ("}}", "]]"):
            depth -= 1
            current.append(pair)
            i += 2
            continue
        if body[i] == "|" and depth == 0:
            out.append("".join(current))
            current = []
        else:
            current.append(body[i])
        i += 1
    out.append("".join(current))
    return out[1:]  # [0] is the template's name


def information_author(wikitext: str) -> str | None:
    """The raw `author` value of the page's one {{Information}}, or None."""
    starts = [m.start() for m in re.finditer(r"\{\{\s*[Ii]nformation\s*(?=\||\n|\}\})", wikitext)]
    if len(starts) != 1:
        return None
    body = _template_body(wikitext, starts[0])
    if body is None:
        return None
    for parameter in _parameters(body):
        name, sep, value = parameter.partition("=")
        if sep and name.strip().casefold() == "author":
            return value.strip()
    return None


_WIKI_USER = re.compile(
    r"\[\[:?(?:(commons|c|w|[a-z]{2,3}):)?[Uu]ser:([^|\]\[{}<>]+)(?:\|([^\]\[{}<>|]+))?\]\]"
)
_EXTERNAL = re.compile(r"\[(https?://[^\s\]]+) ([^\]\[{}<>|]+)\]")


def route_wikitext(page: Page) -> Found | Refused | None:
    """A4: `{{Information|author=...}}` when it is exactly one link or plain text."""
    value = information_author(page.wikitext)
    if value is None or not value:
        return None
    user = _WIKI_USER.fullmatch(value)
    if user:
        wiki, name, label = user.groups()
        name = name.strip()
        host = (
            "commons.wikimedia.org"
            if wiki in (None, "commons", "c")
            else "en.wikipedia.org"
            if wiki == "w"
            else f"{wiki}.wikipedia.org"
        )
        url = f"https://{host}/wiki/User:{name.replace(' ', '_')}"
        return _read(
            "A4",
            "wikitext author",
            value,
            f'<a href="{url}">{html.escape((label or name).strip(), quote=False)}</a>',
        )
    external = _EXTERNAL.fullmatch(value)
    if external:
        url, label = external.groups()
        return _read(
            "A4",
            "wikitext author",
            value,
            f'<a href="{url}">{html.escape(label.strip(), quote=False)}</a>',
        )
    if re.search(r"[\[\]{}<>|=]|''|~~~|https?://", value):
        return Refused("A4", "the author field is markup this lane does not read exactly", value)
    return _read("A4", "wikitext author", value, html.escape(value, quote=False))


def resolve(page: Page) -> Found | Refused:
    """The first route whose field is present decides: a Found, or the reason it cannot."""
    for route in (
        lambda p: route_field(p, "Artist", "A1"),
        lambda p: route_field(p, "Attribution", "A2"),
        route_credit_own_work,
        route_wikitext,
    ):
        result = route(page)
        if result is not None:
            return result
    return Refused(
        "-",
        "no route applies: no Artist, no Attribution, no own-work user link, "
        "no {{Information}} author",
        "",
    )


# ------------------------------------------------------------------------------- fetching
def batch_params(names: Sequence[str]) -> dict[str, Any]:
    return {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "maxlag": 5,
        "redirects": 1,
        "prop": "imageinfo|revisions",
        "iiprop": "extmetadata",
        "iiextmetadatafilter": "|".join(FIELDS),
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "titles": "|".join(f"File:{n}" for n in names),
    }


def fetch_batch(
    fetcher: Fetcher, names: Sequence[str], *, force: bool = False
) -> dict[str, Page | str]:
    """Every requested name -> its Page, or the status Commons gave instead ('missing' etc.)."""
    payload: dict[str, Any] = {}
    last = ""
    for attempt in range(3):
        payload = fetcher.get_json(
            COMMONS_API, batch_params(names), ns=CACHE_NS, force=force or attempt > 0
        )
        answer = payload.get("json") or {}
        if not answer.get("error"):
            break
        last = str(answer["error"])
        time.sleep(PAUSE_S * 5)
    else:
        raise AttributionError(f"Commons refused a batch three times (first {names[0]!r}): {last}")
    answer = payload["json"]
    if "query" not in answer:
        raise AttributionError(f"a batch answer without 'query' (first {names[0]!r})")
    query = answer["query"]
    pages = {p["title"]: p for p in query.get("pages") or []}
    normalized = {e["from"]: e["to"] for e in query.get("normalized") or []}
    redirects = {e["from"]: e["to"] for e in query.get("redirects") or []}
    retrieved_at = str(payload.get("fetched_at"))
    digest = canonical_sha256(answer)
    out: dict[str, Page | str] = {}
    for name in names:
        title = _dereference(_dereference(f"File:{name}", normalized), redirects)
        page = pages.get(title)
        if page is None:
            out[name] = "unanswered"
            continue
        if page.get("missing"):
            out[name] = "missing"
            continue
        revisions = page.get("revisions") or []
        info = (page.get("imageinfo") or [None])[0]
        if len(revisions) != 1 or info is None:
            out[name] = "no revision or no imageinfo"
            continue
        revision = revisions[0]
        ext = {k: str(v.get("value", "")) for k, v in (info.get("extmetadata") or {}).items()}
        out[name] = Page(
            title=str(page["title"]),
            revid=int(revision["revid"]),
            timestamp=str(revision["timestamp"]),
            wikitext=str(revision["slots"]["main"]["content"]),
            extmetadata=ext,
            retrieved_at=retrieved_at,
            response_sha256=digest,
        )
    return out


def fetch_pages(
    names: Sequence[str], fetcher: Fetcher, *, force: bool = False
) -> dict[str, Page | str]:
    out: dict[str, Page | str] = {}
    ordered = sorted(set(names))
    for start in range(0, len(ordered), BATCH):
        before = fetcher.stats["cache_misses"]
        out.update(fetch_batch(fetcher, ordered[start : start + BATCH], force=force))
        if fetcher.stats["cache_misses"] != before:
            time.sleep(PAUSE_S)
    return out


# --------------------------------------------------------------------------------- the plan
def load_rows(records: Sequence[Mapping[str, Any]]) -> list[Row]:
    rows = []
    for record in records:
        rows.append(
            Row(
                id=pv._as_int(record.get("id"), what="wiki_images.id"),
                site_id=str(record["site_id"]),
                author=record.get("author"),
                author_url=record.get("author_url"),
                license=str(record["license"]),
                original_url=record.get("original_url"),
                commons_page_url=record.get("commons_page_url"),
            )
        )
    return rows


@dataclass
class Plan:
    changes: list[CW.Change]
    evidence: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]
    routes: Counter[str]


def evidence_record(row: Row, page: Page, found: Found) -> dict[str, Any]:
    return {
        "image_id": row.id,
        "site_id": row.site_id,
        "file": page.title,
        "revid": page.revid,
        "revision_timestamp": page.timestamp,
        "rule": found.rule,
        "field": found.field,
        "span": found.span,
        "span_sha256": sha256(found.span),
        "markup": found.html,
        "author": found.author,
        "author_url": found.author_url,
        "retrieved_at": page.retrieved_at,
        "response_sha256": page.response_sha256,
    }


def build_plan(rows: Sequence[Row], pages: Mapping[str, Page | str]) -> Plan:
    """Decide every row: a change set with its evidence line, or a named reason. Pure."""
    changes: list[CW.Change] = []
    evidence: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    routes: Counter[str] = Counter()

    def refuse(row: Row, reason: str, **extra: Any) -> None:
        routes["unresolved"] += 1
        unresolved.append(
            {
                "image_id": row.id,
                "site_id": row.site_id,
                "file": row.file_name,
                "reason": reason,
                **extra,
            }
        )

    for row in rows:
        if row.author not in (None, ""):
            raise AttributionError(f"image {row.id} already has an author - it is not in scope")
        name = row.file_name
        if name is None:
            refuse(row, "the row has no Commons identity")
            continue
        page = pages.get(name)
        if not isinstance(page, Page):
            refuse(row, f"commons: {page or 'not fetched'}")
            continue
        found = resolve(page)
        if isinstance(found, Refused):
            refuse(row, f"{found.rule}: {found.reason}", revid=page.revid, span=found.span)
            continue
        if row.author_url not in (None, "") and row.author_url != found.author_url:
            refuse(
                row,
                f"{found.rule}: the row's author_url {row.author_url!r} is not the span's "
                f"{found.author_url!r} - one credit may not mix two sources",
                revid=page.revid,
                span=found.span,
            )
            continue
        record = evidence_record(row, page, found)
        pointer = [
            {
                "source": f"Commons file page, {found.field} ({found.rule})",
                "url": f"https://commons.wikimedia.org/w/index.php?oldid={page.revid}",
                "revid": page.revid,
                "evidence_file": f"output/remediation/gallery_audit/attribution-{DATE}/EVIDENCE.jsonl",
                "evidence_sha256": canonical_sha256(record),
                "span_sha256": record["span_sha256"],
            }
        ]
        reason = f"{page.title}: {found.field} names the author (revid {page.revid})"
        changes.append(
            CW.Change(
                "wiki_images",
                "author",
                str(row.id),
                row.site_id,
                row.author,
                found.author,
                found.rule,
                reason,
                pointer,
            )
        )
        if found.author_url is not None and row.author_url in (None, ""):
            changes.append(
                CW.Change(
                    "wiki_images",
                    "author_url",
                    str(row.id),
                    row.site_id,
                    row.author_url,
                    found.author_url,
                    found.rule,
                    reason,
                    pointer,
                )
            )
        evidence.append(record)
        routes[found.rule] += 1
    return Plan(changes, evidence, unresolved, routes)


def write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def render_plan_md(plan: Plan, rows: Sequence[Row], chunks: Sequence[CW.Chunk]) -> str:
    lines = [
        f"# Attribution backfill ({LANE.stamp})",
        "",
        f"{len(rows)} curated live CC BY* image(s) without an author, read from production.",
        f"{len(plan.evidence)} resolved ({len(plan.changes)} row change(s) over "
        f"{len({c.site_id for c in plan.changes})} site(s), {len(chunks)} chunk(s)); "
        f"{len(plan.unresolved)} unresolved and listed in UNRESOLVED.jsonl.",
        "",
        "| route | rows |",
        "|---|---|",
        *(f"| {rule} | {plan.routes[rule]} |" for rule in ("A1", "A2", "A3", "A4", "unresolved")),
        "",
        "Unresolved, by reason:",
        "",
        "| reason | rows |",
        "|---|---|",
        *(
            f"| {reason} | {n} |"
            for reason, n in Counter(
                u["reason"].split(" - ")[0] for u in plan.unresolved
            ).most_common()
        ),
        "",
        "## Chunks",
        "",
        "| chunk | run stamp | sites | rows |",
        "|---|---|---|---|",
        *(
            f"| {c.number:03d} | {c.run_stamp} | {len(c.sites)} | {len(c.changes)} |"
            for c in chunks
        ),
        "",
        "Per chunk: `chunk_writer.py <chunk> --check`, `--rehearse`, `--apply` (which reads back),",
        "`--rehearse-rollback`. Before the first apply: `attribution.py --recheck`.",
        "",
    ]
    return "\n".join(lines)


def command_plan(out: Path = OUT) -> int:
    rows = load_rows(pv.read_rows(SCOPE_SQL))
    if not rows:
        raise AttributionError("production holds no curated live CC BY* image without an author")
    names = [n for n in (r.file_name for r in rows) if n]
    with Fetcher(root=CACHE, workers=1) as fetcher:
        pages = fetch_pages(names, fetcher)
    plan = build_plan(rows, pages)
    chunks = CW.chunk_changes(LANE, plan.changes)
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "EVIDENCE.jsonl", plan.evidence)
    write_jsonl(out / "UNRESOLVED.jsonl", plan.unresolved)
    CW.emit_chunks(out, chunks)
    (out / "PLAN.md").write_text(render_plan_md(plan, rows, chunks), encoding="utf-8", newline="\n")
    print(f"rows in scope {len(rows)}; resolved {len(plan.evidence)} {dict(plan.routes)}")
    print(f"{len(plan.changes)} change(s) in {len(chunks)} chunk(s) under {out}")
    return 0


# -------------------------------------------------------------------------------- recheck
def recheck(evidence: Sequence[Mapping[str, Any]], pages: Mapping[str, Page | str]) -> list[str]:
    """Every evidence line against a fresh fetch: same revid, same span, same author. Pure."""
    problems = []
    for record in evidence:
        name = str(record["file"]).removeprefix("File:")
        page = pages.get(name)
        where = f"image {record['image_id']} ({record['file']})"
        if not isinstance(page, Page):
            problems.append(f"{where}: Commons now answers {page!r}")
            continue
        if page.revid != record["revid"]:
            problems.append(f"{where}: the page moved from revid {record['revid']} to {page.revid}")
            continue
        found = resolve(page)
        if not isinstance(found, Found) or found.span != record["span"]:
            problems.append(f"{where}: the cited span no longer reads the same")
            continue
        again = parse_attribution({"extmetadata": {"Artist": {"value": record["markup"]}}})
        if (again["author"], again["author_url"]) != (record["author"], record["author_url"]):
            problems.append(
                f"{where}: parse_attribution of the stored span is not the planned author"
            )
        if sha256(str(record["span"])) != record["span_sha256"]:
            problems.append(f"{where}: the stored span does not hash to its span_sha256")
    return problems


def command_recheck(out: Path = OUT) -> int:
    path = out / "EVIDENCE.jsonl"
    evidence = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    names = [str(r["file"]).removeprefix("File:") for r in evidence]
    with Fetcher(root=CACHE, workers=1) as fetcher:
        pages = fetch_pages(names, fetcher, force=True)
    problems = recheck(evidence, pages)
    for problem in problems:
        print(f"  {problem}")
    print(
        f"RECHECK {'FAILED' if problems else 'OK'}: {len(evidence)} evidence line(s), {len(problems)} problem(s)"
    )
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true")
    group.add_argument("--recheck", action="store_true")
    args = parser.parse_args(argv)
    try:
        return command_plan() if args.plan else command_recheck()
    except (AttributionError, pv.PersistError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
