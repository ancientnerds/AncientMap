# SPDX-License-Identifier: AGPL-3.0-only
"""Fill unified_site_names with every name a site is known by, in every language.

WHAT THIS EXISTS FOR
The search answers a query against ``unified_sites.name_normalized``, the country
and the word tier, plus (migration 0027) the site's other names in
``unified_site_names``. A visitor who typed "Machu Picchu" as マチュ・ピチュ,
Μάτσου Πίτσου or माचू पिच्चू found nothing, because the curated rows hold only
their Latin name: read on production 2026-10-04, 4,537 of the 4,900 curated sites
carry a Wikidata QID in ``site_external_ids`` but zero rows in the names table
beyond that one label.

WHERE THE NAMES COME FROM - TWO PLACES, NOT ONE
Wikidata holds a label and aliases per language (Q676203: 140 languages, 7 with
aliases) and, separately, the title of the item's article in every Wikipedia that
has one (Q676203: 132). **A label is not the article title, and in the scripts that
matter they differ:** for Telugu the label is the Latin transcription
"machu pichu", while the tewiki article is titled మాచు పిచ్చు - which is what the
owner typed on 2026-10-04 and what the search did not find. Both ride in the same
call (``props=labels|aliases|sitelinks``): the ``languages`` filter applies to
labels and aliases, and the sitelinks come back whole, so the article titles cost
no extra requests.

What is written, and why it is safe to run twice
Every row goes in with a ``name_type`` that says where it came from -
``wikidata_alias`` for a label or alias, ``wikipedia_title`` for an article title -
and the match key computed by the INSERT itself, ``site_key_sql(':name')``: the one
definition of the key (pipeline/lyra/site_key.py), the same expression the search
compares against. The (site_id, name_normalized) constraint ``uq_usn`` decides
what already exists, so ``ON CONFLICT DO NOTHING`` makes a rerun a no-op. Nothing
already in the table is read, changed or deleted. A rerun therefore runs over every
site again and lets the constraint drop the names it wrote before - ``--only-
without`` would skip exactly the sites that gained labels first and now have
article titles to gain.

The rows are only what Wikidata asserts about that one item, so they are evidence
about the same site rather than a guess: a wrong QID would carry wrong names, which
is why the QIDs come from ``site_external_ids`` (resolved 2026-09-22, audited) and
never from a name search. An article wiki is the one title that names this site
alone; a Wikivoyage entry, a Wikinews headline or a Commons file page names a
journey, a sentence or a set of places, so those are dropped (``NON_ARTICLE_WIKIS``).

USAGE
Read-only by default, and it prints what it would write::

    # the yield, without a database: a file of "qid<TAB>name" lines
    python -m pipeline.wikidata_name_backfill --qids ids.tsv --sample 300

    # against production, inside the api container (read-only until --apply)
    python -m pipeline.wikidata_name_backfill --limit 50
    python -m pipeline.wikidata_name_backfill --apply

The write is journalled to ``--journal`` (JSONL, one line per site written), the
pattern every other production write in this project follows.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from pipeline.database import SessionLocal
from pipeline.lyra.site_key import site_key_sql

logger = logging.getLogger(__name__)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "ancientnerds-wikidata-names/1.0 (https://ancientnerds.com; read-only backfill)"

#: The API answers 50 items per call for an anonymous client (measured 2026-10-04:
#: a 50-id call returned HTTP 200).
IDS_PER_REQUEST = 50

#: ...and 50 languages per call: 84 asked in one call came back
#: {"error": {"code": "toomanyvalues", "parameter": "languages", "limit": 50}}
#: (measured 2026-10-04 on Q676203). The language list is therefore asked in
#: blocks, and one site costs one call per block.
LANGUAGES_PER_REQUEST = 50

#: Seconds between calls. The remediation fetch stage draws an HTTP 429 from the
#: Wikimedia APIs at the default 0.2 s (output/remediation/tools/sitelink_plan.py),
#: so one second is the pace this project has used since.
PACE_SECONDS = 1.0

#: The languages to ask for. The prospector's identity work asks for eleven
#: (pipeline/lyra/site_identifier.py:1241) - enough to check whether a name is the
#: same name. A search wants the names a visitor would actually type, so this is
#: the Wikipedia set of major languages plus the scripts the archaeological record
#: is written in. Wikidata answers a language it has no label for with nothing,
#: so a wide list costs nothing in rows.
LANGUAGES = (
    # Europe
    "en",
    "de",
    "fr",
    "es",
    "it",
    "pt",
    "nl",
    "sv",
    "no",
    "da",
    "fi",
    "et",
    "lv",
    "lt",
    "pl",
    "cs",
    "sk",
    "hu",
    "ro",
    "hr",
    "sr",
    "sl",
    "bg",
    "ru",
    "uk",
    "be",
    "el",
    "la",
    "tr",
    "sq",
    "bs",
    "mk",
    "ka",
    "hy",
    "az",
    "kk",
    "uz",
    "mn",
    "is",
    "ga",
    "cy",
    "eu",
    "gl",
    "ca",
    "id",
    "ms",
    "tl",
    "vi",
    "th",
    # Middle East and Central Asia
    "ar",
    "fa",
    "ur",
    "he",
    "ku",
    "ps",
    "sd",
    "ug",
    "ky",
    "tg",
    "tk",
    # South and Central Asia
    "hi",
    "bn",
    "pa",
    "gu",
    "mr",
    "or",
    "ta",
    "te",
    "kn",
    "ml",
    "si",
    "ne",
    "my",
    "km",
    "lo",
    # East Asia
    "zh",
    "zh-classical",
    "zh-yue",
    "ja",
    "ko",
    "wuu",
    "nan",
    "bo",
)

#: A name shorter than this cannot drive the trigram index (pg_trgm needs three),
#: and site_identifier has skipped them for the aliases it writes since 2026-09.
MIN_NAME_CHARS = 3

#: What a row says about itself in ``name_type``: the name Wikidata asserts about
#: the item, or the title the Wikipedia of one language gives its article about it.
#: Both are found by the search, which reads ``name_type <> 'label'``, and both sit
#: in the partial trigram index of migration 0027.
NAME_TYPE_WIKIDATA = "wikidata_alias"
NAME_TYPE_ARTICLE = "wikipedia_title"

#: The wikis whose titles are not article titles. A Wikivoyage entry, a Wikinews
#: headline, a quotation or a Commons file page carries a journey, a sentence or a
#: set of places: ruwikinews titles Q676203 "Мачу-Пикчу и другие исторические
#: объекты Перу, фотосъёмка" (measured 2026-10-04). Only the article wikis name
#: the one site, so only those contribute a name.
#:
#: Measured over all 4,537 curated QIDs the run also answered with these project
#: codes, whose titles are a source text or a namespace, not a place: sourceswiki
#: (Wikisource), quotewiki, abstractwiki (the Simple English article namespace).
NON_ARTICLE_WIKIS = (
    "wikivoyage",
    "wikiquote",
    "wikinews",
    "wiktionary",
    "wikisource",
    "wikibooks",
    "wikiversity",
    "wikimedia",
    "wikidata",
    "mediawiki",
    "metawiki",
    "commonswiki",
    "specieswiki",
    "sourceswiki",
    "quotewiki",
    "abstractwiki",
)

#: Names that are only punctuation, or that repeat the site in a script no reader
#: would type. Kept deliberately blunt: Wikidata's own label is the evidence.
_NOISE = {".", "..", "...", "-", "–", "—", "?", "!", "/", "\\"}


def _article_language(site: str) -> str | None:
    """The language code of a sitelink that is an article, or None.

    ``tewiki`` -> ``te``; ``be_x_oldwiki`` -> ``be_x_old``; ``ruwikivoyage`` and
    ``commonswiki`` -> None, because their titles are not the name of this site.
    """
    if not site.endswith("wiki"):
        return None
    if any(site.endswith(other) for other in NON_ARTICLE_WIKIS):
        return None
    return site[: -len("wiki")] or None


_SELECT_SITES = text(
    """
    SELECT us.id::text AS site_id, us.name, e.value AS qid
    FROM unified_sites us
    JOIN site_external_ids e ON e.site_id = us.id AND e.kind = 'wikidata_qid'
    WHERE us.source_id = 'ancient_nerds'
      AND us.scope_status IS DISTINCT FROM 'retired'
      AND e.value ~ '^Q[0-9]+$'
    ORDER BY us.name
    """
)


#: One statement for a whole site: the key is computed in the INSERT from the raw
#: name, exactly as _store_wikidata_aliases does for a single alias, and the
#: constraint decides what exists. The VALUES list is built per call - a
#: parameter has no type Postgres can infer in that position, so all three columns
#: are cast. CAST(...) and not ``:n0::text``: SQLAlchemy's text() does not read a
#: bind that is immediately followed by a colon, and the statement then fails
#: with "syntax error at or near ':'" (measured 2026-10-04 on production).
#:
#: The two widths are binds, not constants, because the columns have limits and a
#: row that ignores them dies the whole run: on production ``name`` is
#: varchar(500) and ``language_code`` varchar(10), and the Wikipedia sitelink codes
#: are longer than the Wikidata language codes (zh_classical has 12). The run died
#: on the first site that had one, with StringDataRightTruncation, after 29 sites.
def _insert_sql(count: int) -> str:
    values = ",".join(
        f"(CAST(:n{i} AS text), CAST(:l{i} AS text), CAST(:t{i} AS text))" for i in range(count)
    )
    return f"""
    INSERT INTO unified_site_names (site_id, name, name_normalized, language_code, name_type)
    SELECT :site_id, left(n.name, CAST(:max_name AS int)),
           {site_key_sql("left(n.name, CAST(:max_name AS int))")},
           n.language_code, n.name_type
    FROM (VALUES {values}) AS n(name, language_code, name_type)
    WHERE {site_key_sql("left(n.name, CAST(:max_name AS int))")} <> {site_key_sql(":canonical")}
      AND char_length(n.name) >= :min_chars
      AND char_length(n.language_code) <= CAST(:max_lang AS int)
    ON CONFLICT ON CONSTRAINT uq_usn DO NOTHING
    """


_WIDTHS_SQL = """
    SELECT column_name, character_maximum_length
    FROM information_schema.columns
    WHERE table_name = 'unified_site_names'
      AND column_name IN ('name', 'language_code')
"""


def _column_widths(session: Session) -> dict[str, int]:
    """How much room the two columns have, asked of the database once per run.

    Read from information_schema rather than written down, because a guess that is
    too small silently costs rows and a guess that is too large dies on the first
    long name with StringDataRightTruncation. An empty answer stops the run rather
    than falling back to a number: a guessed width is how rows go missing silently.
    """
    rows = session.execute(text(_WIDTHS_SQL)).fetchall()
    widths = {name: width for name, width in rows if width is not None}
    if not widths:
        raise RuntimeError(
            f"could not read the column widths of unified_site_names: {_WIDTHS_SQL.strip()}"
        )
    return widths


@dataclass
class SiteNames:
    """What one site would gain."""

    site_id: str
    name: str
    qid: str
    rows: list[tuple[str, str, str]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)


def _http_json(params: dict[str, str], timeout: int = 45) -> dict:
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_names(qids: list[str]) -> tuple[dict[str, list[tuple[str, str, str]]], int]:
    """({qid: [(name, language_code, name_type), ...]}, requests_made).

    Labels, aliases and the titles of the articles about the item, 50 items and 50
    languages per call, one second apart. A call that fails is logged and skipped: a
    site whose names are missing stays findable by its own name, which is where it
    was before.

    The article titles ride along in the same call rather than in a second one: the
    ``languages`` filter applies to labels and aliases, and ``props=sitelinks`` comes
    back in full whatever was asked for (measured 2026-10-04 on Q676203 with
    ``languages=te|en|kn``: three labels, every sitelink).
    """
    found: dict[str, dict[str, tuple[str, str]]] = {qid: {} for qid in qids}
    language_blocks = [
        LANGUAGES[i : i + LANGUAGES_PER_REQUEST]
        for i in range(0, len(LANGUAGES), LANGUAGES_PER_REQUEST)
    ]
    requests_made = 0
    for start in range(0, len(qids), IDS_PER_REQUEST):
        batch = qids[start : start + IDS_PER_REQUEST]
        for block in language_blocks:
            try:
                data = _http_json(
                    {
                        "action": "wbgetentities",
                        "ids": "|".join(batch),
                        "props": "labels|aliases|sitelinks",
                        "languages": "|".join(block),
                        "format": "json",
                    }
                )
                requests_made += 1
            except Exception as exc:  # noqa: BLE001 - one lost block must not end the run
                logger.warning("wbgetentities %s..%s failed: %s", batch[0], batch[-1], exc)
                time.sleep(PACE_SECONDS * 3)
                continue

            if data.get("error"):
                logger.warning("wbgetentities %s..%s: %s", batch[0], batch[-1], data["error"])
                time.sleep(PACE_SECONDS)
                continue

            for qid, entity in (data.get("entities") or {}).items():
                names = found.setdefault(qid, {})
                for lang, label in (entity.get("labels") or {}).items():
                    value = label.get("value", "").strip()
                    if value and value not in _NOISE:
                        names.setdefault(value, (lang, NAME_TYPE_WIKIDATA))
                for lang, aliases in (entity.get("aliases") or {}).items():
                    for alias in aliases:
                        value = alias.get("value", "").strip()
                        if value and value not in _NOISE:
                            names.setdefault(value, (lang, NAME_TYPE_WIKIDATA))
                for site, link in (entity.get("sitelinks") or {}).items():
                    lang = _article_language(site)
                    value = (link.get("title") or "").strip()
                    if lang and value and value not in _NOISE:
                        names.setdefault(value, (lang, NAME_TYPE_ARTICLE))
            time.sleep(PACE_SECONDS)
    # One name, one row: 30 language codes spell "Machu Picchu" alike and the
    # constraint would drop them one by one anyway. A name Wikidata labels and an
    # article that titles alike keeps the label - it is the assertion about the item
    # itself, the article title only its rendering in one Wikipedia.
    return {
        qid: sorted((value, lang, kind) for value, (lang, kind) in rows.items())
        for qid, rows in found.items()
        if rows
    }, requests_made


def plan(
    sites: list[tuple[str, str, str]], found: dict[str, list[tuple[str, str, str]]]
) -> list[SiteNames]:
    """The rows one site would gain, before the database is asked anything."""
    plans = []
    for site_id, name, qid in sites:
        rows = [row for row in found.get(qid, []) if row[0] != name]
        if rows:
            plans.append(SiteNames(site_id=site_id, name=name, qid=qid, rows=rows))
    return plans


def report(plans: list[SiteNames], sites: list[tuple[str, str, str]], requests_made: int) -> dict:
    """The yield, so a dry run says what an --apply would write."""
    languages = Counter(lang for p in plans for _name, lang, _kind in p.rows)
    kinds = Counter(kind for p in plans for _name, _lang, kind in p.rows)
    return {
        "sites_considered": len(sites),
        "sites_with_names": len(plans),
        "sites_without_a_label": len(sites) - len(plans),
        "rows": sum(len(p) for p in plans),
        "rows_per_site": round(sum(len(p) for p in plans) / len(plans), 1) if plans else 0,
        "name_types": dict(kinds.most_common()),
        "languages": dict(languages.most_common()),
        "api_requests": requests_made,
        "examples": [
            {"site": p.name, "qid": p.qid, "names": [n for n, _lang, _kind in p.rows[:6]]}
            for p in plans[:5]
        ],
    }


def store(session: Session, plan_row: SiteNames, widths: dict[str, int]) -> int:
    """Write one site's names. The key comes from the INSERT, the constraint decides.

    The widths are the ones :func:`_column_widths` read, so a widened column takes
    the rows it was widened for. The rows whose language_code does not fit are left
    out by the statement rather than clipped: a shortened 'zh_classist' would name a
    language that does not exist. plan_row.rows is unchanged, so the journal still
    lists what was offered and :func:`skipped_codes` says what the column refused.
    """
    params: dict[str, object] = {
        "site_id": plan_row.site_id,
        "canonical": plan_row.name,
        "min_chars": MIN_NAME_CHARS,
        "max_name": widths["name"],
        "max_lang": widths["language_code"],
    }
    for i, (name, lang, kind) in enumerate(plan_row.rows):
        params[f"n{i}"] = name
        params[f"l{i}"] = lang
        params[f"t{i}"] = kind
    result = session.execute(text(_insert_sql(len(plan_row.rows))), params)
    session.commit()
    return result.rowcount


def skipped_codes(plan_row: SiteNames, max_lang: int) -> list[dict[str, str]]:
    """The rows the column width left out, so a run says what it could not write."""
    return [
        {"name": name, "language_code": lang}
        for name, lang, _kind in plan_row.rows
        if len(lang) > max_lang
    ]


def load_sites(
    session: Session, limit: int | None, only_without: bool
) -> list[tuple[str, str, str]]:
    sql = str(_SELECT_SITES)
    if only_without:
        sql += """
          AND NOT EXISTS (
            SELECT 1 FROM unified_site_names n
            WHERE n.site_id = us.id AND n.name_type <> 'label'
          )
        """
    sql += " LIMIT :limit"
    rows = session.execute(text(sql), {"limit": limit or 100_000}).fetchall()
    return [(r.site_id, r.name, r.qid) for r in rows]


def read_qid_file(path: Path) -> list[tuple[str, str, str]]:
    """A "qid<TAB>name" file, so the yield can be measured without a database."""
    sites = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        qid, _, name = line.partition("\t")
        sites.append(("", name, qid.strip()))
    return sites


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--apply", action="store_true", help="write the rows (default: report only)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="how many curated sites to consider"
    )
    parser.add_argument(
        "--qids", type=Path, default=None, help="a qid<TAB>name file instead of the database"
    )
    parser.add_argument(
        "--sample", type=int, default=None, help="with --qids, use only the first N sites"
    )
    parser.add_argument(
        "--only-without",
        action="store_true",
        help="skip sites that already have a non-label name (a rerun's cheap path)",
    )
    parser.add_argument("--journal", type=Path, default=None, help="JSONL of what was written")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = None
    if args.qids:
        sites = read_qid_file(args.qids)
        if args.sample:
            sites = sites[: args.sample]
    else:
        session = SessionLocal()
        sites = load_sites(session, args.limit, args.only_without)
    if not sites:
        print("no sites to consider")
        return 0

    print(f"considering {len(sites)} curated sites ...", file=sys.stderr)
    found, requests_made = fetch_names([qid for _sid, _name, qid in sites])
    plans = plan(sites, found)
    print(json.dumps(report(plans, sites, requests_made), indent=2, ensure_ascii=False))

    if not args.apply:
        print("dry run: nothing written. Pass --apply to write.", file=sys.stderr)
        if session:
            session.close()
        return 0
    if not session:
        print("--apply needs the database; drop --qids", file=sys.stderr)
        return 2

    if args.journal:
        # The run on production failed on this line with FileNotFoundError: the
        # caller made the directory on the host, and only public/data, logs and
        # frontend are mounted into the container, so output/ did not exist in
        # there. Nothing had been written - this runs before the first store().
        args.journal.parent.mkdir(parents=True, exist_ok=True)
    journal = args.journal.open("a", encoding="utf-8") if args.journal else None
    widths = _column_widths(session)
    written = 0
    refused = 0
    try:
        for i, plan_row in enumerate(plans, 1):
            skipped = skipped_codes(plan_row, widths["language_code"])
            count = store(session, plan_row, widths)
            written += count
            refused += len(skipped)
            if journal:
                journal.write(
                    json.dumps(
                        {
                            "site_id": plan_row.site_id,
                            "name": plan_row.name,
                            "qid": plan_row.qid,
                            "rows": count,
                            # What the statement was given; "rows" is what the
                            # constraint let through, so it can be the smaller
                            # number when a name is already in the table.
                            "names": [
                                {"name": n, "language_code": lang, "name_type": kind}
                                for n, lang, kind in plan_row.rows
                            ],
                            # Left out because language_code is varchar(10) and
                            # zh_classical is 12 characters. Clipping the code
                            # would name a language that does not exist.
                            "skipped_language_codes": skipped,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                journal.flush()
            if i % 100 == 0:
                print(f"  {i}/{len(plans)} sites, {written} rows", file=sys.stderr)
    finally:
        if journal:
            journal.close()
        session.close()
    print(f"wrote {written} rows for {len(plans)} sites")
    if refused:
        print(
            f"left out {refused} rows: language_code is "
            f"varchar({widths['language_code']}) and their code is longer "
            "(zh_classical is 12 characters). Widening the column is a migration; "
            "the names are in the journal under skipped_language_codes.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
