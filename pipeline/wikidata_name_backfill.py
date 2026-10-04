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

Wikidata carries a label in up to 140 languages for such a site (Q676203: 140
languages, 7 of them with aliases), so the names are one read-only API call per
50 sites away.

WHAT IT WRITES, AND WHY IT IS SAFE TO RUN TWICE
Every row goes in with ``name_type = 'wikidata_alias'`` and the match key
computed by the INSERT itself, ``site_key_sql(':name')`` - the one definition of
the key (pipeline/lyra/site_key.py), the same expression the search compares
against. The (site_id, name_normalized) constraint ``uq_usn`` decides what
already exists, so ``ON CONFLICT DO NOTHING`` makes a rerun a no-op. Nothing
already in the table is read, changed or deleted.

The rows are only what Wikidata calls a label or an alias of that one item, so
they are evidence about the same site rather than a guess: a wrong QID would
carry wrong names, which is why the QIDs come from ``site_external_ids``
(resolved 2026-09-22, audited) and never from a name search.

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

#: Names that are only punctuation, or that repeat the site in a script no reader
#: would type. Kept deliberately blunt: Wikidata's own label is the evidence.
_NOISE = {".", "..", "...", "-", "–", "—", "?", "!", "/", "\\"}

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
#: parameter has no type Postgres can infer in that position, so both columns are
#: cast. CAST(...) and not ``:n0::text``: SQLAlchemy's text() does not read a
#: bind that is immediately followed by a colon, and the statement then fails
#: with "syntax error at or near ':'" (measured 2026-10-04 on production).
def _insert_sql(count: int) -> str:
    values = ",".join(f"(CAST(:n{i} AS text), CAST(:l{i} AS text))" for i in range(count))
    return f"""
    INSERT INTO unified_site_names (site_id, name, name_normalized, language_code, name_type)
    SELECT :site_id, n.name, {site_key_sql("n.name")}, n.language_code, 'wikidata_alias'
    FROM (VALUES {values}) AS n(name, language_code)
    WHERE {site_key_sql("n.name")} <> {site_key_sql(":canonical")}
      AND char_length(n.name) >= :min_chars
    ON CONFLICT ON CONSTRAINT uq_usn DO NOTHING
    """


@dataclass
class SiteNames:
    """What one site would gain."""

    site_id: str
    name: str
    qid: str
    rows: list[tuple[str, str]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)


def _http_json(params: dict[str, str], timeout: int = 45) -> dict:
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_names(qids: list[str]) -> tuple[dict[str, list[tuple[str, str]]], int]:
    """({qid: [(name, language_code), ...]}, requests_made) for labels and aliases.

    50 items and 50 languages per call, one second apart. A call that fails is
    logged and skipped: a site whose names are missing stays findable by its own
    name, which is where it was before.
    """
    found: dict[str, dict[str, str]] = {qid: {} for qid in qids}
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
                        "props": "labels|aliases",
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
                        names.setdefault(value, lang)
                for lang, aliases in (entity.get("aliases") or {}).items():
                    for alias in aliases:
                        value = alias.get("value", "").strip()
                        if value and value not in _NOISE:
                            names.setdefault(value, lang)
            time.sleep(PACE_SECONDS)
    # One name, one row: 30 language codes spell "Machu Picchu" alike and the
    # constraint would drop them one by one anyway.
    return {qid: sorted(rows.items()) for qid, rows in found.items() if rows}, requests_made


def plan(
    sites: list[tuple[str, str, str]], found: dict[str, list[tuple[str, str]]]
) -> list[SiteNames]:
    """The rows one site would gain, before the database is asked anything."""
    plans = []
    for site_id, name, qid in sites:
        rows = [(value, lang) for value, lang in found.get(qid, []) if value != name]
        if rows:
            plans.append(SiteNames(site_id=site_id, name=name, qid=qid, rows=rows))
    return plans


def report(plans: list[SiteNames], sites: list[tuple[str, str, str]], requests_made: int) -> dict:
    """The yield, so a dry run says what an --apply would write."""
    languages = Counter(lang for p in plans for _name, lang in p.rows)
    return {
        "sites_considered": len(sites),
        "sites_with_names": len(plans),
        "sites_without_a_label": len(sites) - len(plans),
        "rows": sum(len(p) for p in plans),
        "rows_per_site": round(sum(len(p) for p in plans) / len(plans), 1) if plans else 0,
        "languages": dict(languages.most_common()),
        "api_requests": requests_made,
        "examples": [
            {"site": p.name, "qid": p.qid, "names": [n for n, _lang in p.rows[:6]]}
            for p in plans[:5]
        ],
    }


def store(session: Session, plan_row: SiteNames) -> int:
    """Write one site's names. The key comes from the INSERT, the constraint decides."""
    params: dict[str, object] = {
        "site_id": plan_row.site_id,
        "canonical": plan_row.name,
        "min_chars": MIN_NAME_CHARS,
    }
    for i, (name, lang) in enumerate(plan_row.rows):
        params[f"n{i}"] = name
        params[f"l{i}"] = lang
    result = session.execute(text(_insert_sql(len(plan_row.rows))), params)
    session.commit()
    return result.rowcount


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

    journal = args.journal.open("a", encoding="utf-8") if args.journal else None
    written = 0
    try:
        for i, plan_row in enumerate(plans, 1):
            count = store(session, plan_row)
            written += count
            if journal:
                journal.write(
                    json.dumps(
                        {
                            "site_id": plan_row.site_id,
                            "name": plan_row.name,
                            "qid": plan_row.qid,
                            "rows": count,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
