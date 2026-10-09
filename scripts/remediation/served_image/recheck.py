"""D15 (owner decision of 2026-10-08): the heroes a Claude check called `other_site`, looked at again.

The served-image run of 2026-09-30 judged every served image and every gallery candidate. 47 of the
live heroes carry an `other_site` verdict from it - 41 from Sonnet, 6 from Opus - and the owner's
2025 hand-link made most of them heroes in the first place. Decision D15 is "re-check, then swap":
a second Claude checker (the adversarial role, Opus high) looks at each of them with more context
than the first one had, and only a *confirmed* `other_site` moves the hero:

* confirmed `other_site` with a gallery row that depicts the site: the row is excluded and the hero
  flag and the thumbnail move to the pick (`plan.py`, `wd2-exclude`/`wd2-hero`/`wd2-align`);
* confirmed `other_site` and nothing that depicts the site: the site is cleared and joins the D17
  pool, and the excluded file is recorded so it is not offered again;
* `depicts` or `region_or_type`: the hero stays - the picture is the owner's link and a region view
  of the right place is not a picture of another site.

This module derives the population from the records (no list of ids is typed in), builds the context
a checker gets beyond the picture, and names the files a swap must not offer again.

    run.py read          --run-dir R
    run.py precheck      --run-dir R --harvest H --sites R/SITES.txt   (see run.py)
    run.py derive-sites  --run-dir R --verdicts-run served-image-2026-09-30
    run.py context       --run-dir R --verdicts-run served-image-2026-09-30 --import FILE
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from served_image import state as ST

HEROES_FILE = "OTHER_SITE_HEROES.jsonl"
SITES_FILE = "SITES.txt"
CONTEXT_FILE = "CONTEXT.jsonl"
OTHER_SITE = "other_site"
#: At most this many characters of the description go to the checker: enough for the type, the
#: place and the first claims; the picture decides, the text only tells what to look for.
DESCRIPTION_CHARS = 900
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_PACE_SECONDS = 1.0

#: Context keys a recheck prompt reads; `CONTEXT_KEYS` is also what an import refuses to miss.
CONTEXT_KEYS = frozenset(
    {
        "site_id",
        "description",
        "wikipedia_title",
        "wikipedia_cache_file",
        "wikipedia_lead_image",
        "owner_link_url",
        "owner_link_file",
        "earlier_stage",
        "earlier_verdict",
        "earlier_shows",
        "earlier_answered_by",
    }
)


class RecheckError(ST.StateError):
    """The derivation or the context cannot be made from what was given. Nothing is guessed."""


def judged_gallery_rows(
    checks: Iterable[Mapping[str, Any]], replaces: Iterable[Mapping[str, Any]]
) -> dict[int, dict[str, Any]]:
    """`image id -> its latest verdict` over the two stages of a served-image run.

    The check stage judges the served image of a site (`served.image_id`); the replacement stage
    judges every gallery row it offered (`candidates_shown`, `kind == "gallery"`). An image judged
    in both keeps the replacement stage's verdict - the later one, made with the whole gallery in
    view. The record carries the stage, the answer's `shows`/`basis`, who answered and the site."""
    out: dict[int, dict[str, Any]] = {}
    for row in checks:
        image_id = (row.get("served") or {}).get("image_id")
        if image_id:
            out[int(image_id)] = {
                "stage": "served-check",
                "verdict": row["verdict"],
                "shows": row.get("shows"),
                "basis": row.get("basis"),
                "answered_by": row.get("answered_by"),
                "model": row.get("model"),
                "site_id": str(row["site_id"]),
                "file": row["served"].get("file"),
            }
    for row in replaces:
        for shown in row["candidates_shown"]:
            if shown.get("kind") == "gallery" and shown.get("image_id"):
                out[int(shown["image_id"])] = {
                    "stage": "served-replace",
                    "verdict": row["candidates"][shown["label"]],
                    "shows": None,
                    "basis": row.get("basis"),
                    "answered_by": row.get("answered_by"),
                    "model": row.get("model"),
                    "site_id": str(row["site_id"]),
                    "file": shown.get("file"),
                }
    return out


def other_site_heroes(
    state: ST.State,
    checks: Sequence[Mapping[str, Any]],
    replaces: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The live hero rows of the read that the earlier run judged `other_site`, in image-id order.

    A row counts when it is its site's hero, is not excluded and belongs to a shown site of the
    read: a retired site is not in the read, an excluded row is no longer served. The verdict is
    the earlier run's (`judged_gallery_rows`), the row's own state is the read's."""
    verdicts = judged_gallery_rows(checks, replaces)
    out = []
    for sid in state.site_ids():
        for row in state.rows.get(sid, ()):
            judged = verdicts.get(int(row["id"]))
            if (
                judged is not None
                and judged["verdict"] == OTHER_SITE
                and row.get("is_hero")
                and not row.get("is_excluded")
            ):
                out.append({"image_id": int(row["id"]), "site_id": sid, **judged})
    return sorted(out, key=lambda r: r["image_id"])


def write_derivation(run: Path, heroes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """`OTHER_SITE_HEROES.jsonl` (the evidence per row) and `SITES.txt` (one site id per line), each
    written once. A site with two such heroes is impossible (one hero per site) and refused."""
    sites = [str(h["site_id"]) for h in heroes]
    if len(set(sites)) != len(sites):
        raise RecheckError("two hero rows of one site were judged other_site - a site has one hero")
    if not heroes:
        raise RecheckError("no live hero was judged other_site - there is nothing to re-check")
    digest = ST.write_text_once(run / HEROES_FILE, ST.jsonl_text(heroes))
    ST.write_text_once(run / SITES_FILE, "".join(f"{s}\n" for s in sites))
    return {"heroes": len(heroes), "sites": len(sites), "sha256": digest}


def read_sites(path: Path) -> list[str]:
    """The site ids of a `--sites` file: one per line, blank lines and `#` comments skipped. A file
    that names no site, or a site twice, is refused."""
    if not path.is_file():
        raise RecheckError(f"{path} does not exist - it is the list of sites to examine")
    sites = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not sites:
        raise RecheckError(f"{path} names no site")
    if len(set(sites)) != len(sites):
        raise RecheckError(f"{path} names a site twice")
    return sites


# ------------------------------------------------------------------------------ the context
def context_sql(site_ids: Sequence[str]) -> str:
    """The read-only statement of the context: the description's head and the enwiki title of each
    site (`site_external_ids`, the one place a Wikipedia title is stored)."""
    ids = ", ".join(f"'{sid}'::uuid" for sid in site_ids)
    return f"""SELECT row_to_json(t) FROM (
  SELECT u.id::text AS site_id, left(coalesce(u.description, ''), {DESCRIPTION_CHARS}) AS description,
         (SELECT min(e.value) FROM site_external_ids e
           WHERE e.site_id = u.id AND e.kind = 'enwiki_title') AS wikipedia_title
    FROM unified_sites u WHERE u.id IN ({ids}) ORDER BY u.id
) t;"""


def lead_image(client: Any, title: str) -> str | None:
    """The English Wikipedia article's lead image (its file name, `pageimages`), or None for an
    article without one. A failed request raises - it is never read as "no image"."""
    response = client.get(
        WIKIPEDIA_API,
        params={
            "action": "query",
            "format": "json",
            "formatversion": 2,
            "prop": "pageimages",
            "piprop": "name",
            "redirects": 1,
            "titles": title,
        },
    )
    if response.status_code != 200:
        raise RecheckError(f"{WIKIPEDIA_API} answered HTTP {response.status_code} for {title!r}")
    pages = response.json().get("query", {}).get("pages") or []
    if len(pages) != 1:
        raise RecheckError(f"Wikipedia answered {len(pages)} pages for {title!r}")
    name = pages[0].get("pageimage")
    return ST.canonical_file(name) if name else None


def build_context(
    heroes: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    owner_links: Mapping[str, Mapping[str, Any]],
    client: Any,
    *,
    cache_file: Callable[[str], str | None],
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """One context record per hero: the description, the Wikipedia article and its lead image, the
    owner's 2025 link and what the earlier checker said.

    `rows` is the answer of `context_sql`; `owner_links` the import's join (`import_hero.plan.
    join_import`, site id -> `{"image": url | None, ...}`); `cache_file(site_id)` is the path of the
    site's page in the shared Wikipedia cache (None when it has none), which the agent reads first.
    A hero whose site `rows` do not answer is refused - the context is part of the question."""
    by_site = {str(r["site_id"]): r for r in rows}
    out = []
    for hero in heroes:
        sid = str(hero["site_id"])
        row = by_site.get(sid)
        if row is None:
            raise RecheckError(f"{sid}: the context read answered nothing for this site")
        title = row.get("wikipedia_title")
        lead = None
        if title:
            lead = lead_image(client, str(title))
            sleep(WIKIPEDIA_PACE_SECONDS)
        owner = (owner_links.get(sid) or {}).get("image")
        out.append(
            {
                "site_id": sid,
                "description": str(row.get("description") or "").strip() or None,
                "wikipedia_title": title,
                "wikipedia_cache_file": cache_file(sid),
                "wikipedia_lead_image": lead,
                "owner_link_url": owner,
                "owner_link_file": ST.file_of_url(owner) if owner else None,
                "earlier_stage": hero["stage"],
                "earlier_verdict": hero["verdict"],
                "earlier_shows": hero.get("shows") or hero.get("basis"),
                "earlier_answered_by": hero.get("answered_by"),
            }
        )
    return out


def write_context(run: Path, records: Sequence[Mapping[str, Any]]) -> str:
    """`CONTEXT.jsonl`, written once; every record carries exactly `CONTEXT_KEYS`."""
    for record in records:
        if set(record) != CONTEXT_KEYS:
            raise RecheckError(
                f"a context record carries {sorted(record)}, not {sorted(CONTEXT_KEYS)}"
            )
    return ST.write_text_once(run / CONTEXT_FILE, ST.jsonl_text(records))


def load_context(path: Path) -> dict[str, dict[str, Any]]:
    """The run's context by site id; a record out of shape or a site twice is refused."""
    if not path.is_file():
        raise RecheckError(f"{path} does not exist - run `run.py context` first")
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if set(record) != CONTEXT_KEYS or record["site_id"] in out:
            raise RecheckError(f"{path}: a record out of shape or a site twice: {line[:120]}")
        out[record["site_id"]] = record
    return out
