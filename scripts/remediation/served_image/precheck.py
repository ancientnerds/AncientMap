"""The deterministic pre-check: a served image the site's own Wikidata item vouches for.

A served image is **CONFIRMED** when its Commons file is the site's Wikidata image (P18) or lies in
the site's Commons category (P373). Everything else goes to the Opus vision check (`vision.py`);
a site that serves nothing is `no-image` and has nothing to check.

**Membership is direct.** The file's own categories must hold the P373 category. The project's
downloader also takes files one subcategory deep (`pipeline/wiki_image_downloader.py`,
`fetch_commons_category_images`), and T10 counts that hop as membership; a pre-check that skips
the vision check must not, because a subcategory is where a site's category keeps its maps,
museum objects from elsewhere and neighbouring monuments.

**The harvest is WD1's** - `output/remediation/fields/harvest/SITES.jsonl` (one line per curated
site: `site_id, name, country, lat, lon, qid, enwiki_title, source_url`, `qid` null when the site
has no item) and `entities/<QID>.json` (the raw `wbgetentities` entity). This module reads it and
harvests nothing. A site whose item is wrong (FINISH_PLAN, WE: the L5 link pass fixes up to 120
generic or wrong items first) would confirm a wrong image, so the pre-check runs after L5.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
for _path in (ROOT, ROOT / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from mechanical.plan import UUID_RE  # noqa: E402
from mechanical.plan import _claim_strings as claim_strings  # noqa: E402 - one claim reader

from served_image.commons import OK, Commons, FileInfo, canonical_category  # noqa: E402
from served_image.state import (  # noqa: E402
    NONE,
    Served,
    State,
    StateError,
    canonical_file,
    jsonl_text,
    served_of,
    write_text_once,
)

DEFAULT_HARVEST = ROOT / "output" / "remediation" / "fields" / "harvest"
#: The run directory's pre-check and its summary, each written once: the check stage's export
#: pins the pre-check's sha256, and every later stage refuses another one.
PRECHECK_FILE = "PRECHECK.jsonl"
PRECHECK_SUMMARY = "PRECHECK.json"
HARVEST_KEYS = frozenset(
    {"site_id", "name", "country", "lat", "lon", "qid", "enwiki_title", "source_url"}
)

CONFIRMED_P18 = "confirmed-p18"
CONFIRMED_P373 = "confirmed-p373"
UNCONFIRMED = "unconfirmed"
NO_IMAGE = "no-image"
STATUSES = (CONFIRMED_P18, CONFIRMED_P373, UNCONFIRMED, NO_IMAGE)
CONFIRMED = frozenset({CONFIRMED_P18, CONFIRMED_P373})


class HarvestError(StateError):
    """The harvest is not in WD1's layout, or does not cover what the pre-check reads."""


# ------------------------------------------------------------------------------ the harvest
@dataclass(frozen=True)
class Harvest:
    root: Path
    qids: Mapping[str, str | None]

    def entity(self, qid: str) -> Mapping[str, Any]:
        path = self.root / "entities" / f"{qid}.json"
        if not path.is_file():
            raise HarvestError(f"{path} is missing - the harvest names {qid} but holds no entity")
        entity = json.loads(path.read_text(encoding="utf-8"))
        merged = (entity.get("redirects") or {}).get("from") == qid
        if entity.get("id") != qid and not merged:
            raise HarvestError(f"{path} holds {entity.get('id')!r}, not {qid}")
        return entity


def load_harvest(root: Path) -> Harvest:
    path = root / "SITES.jsonl"
    if not path.is_file():
        raise HarvestError(f"{path} does not exist - WD1's harvest is the pre-check's input")
    qids: dict[str, str | None] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if set(row) != HARVEST_KEYS:
            raise HarvestError(f"{path}:{number}: keys {sorted(row)}, not {sorted(HARVEST_KEYS)}")
        sid = str(row["site_id"])
        if not UUID_RE.match(sid) or sid in qids:
            raise HarvestError(f"{path}:{number}: {sid!r} is no site id or is listed twice")
        qid = row["qid"]
        if qid is not None and not (isinstance(qid, str) and qid[:1] == "Q" and qid[1:].isdigit()):
            raise HarvestError(f"{path}:{number}: {qid!r} is no Wikidata item id")
        qids[sid] = qid
    return Harvest(root, qids)


def p18_files(entity: Mapping[str, Any]) -> list[str]:
    """The item's images (P18, not deprecated), in title form."""
    return [canonical_file(f) for f in claim_strings(entity, "P18")]


def p373_categories(entity: Mapping[str, Any]) -> list[str]:
    """The item's Commons categories (P373, not deprecated), in title form."""
    return [canonical_category(c) for c in claim_strings(entity, "P373")]


# ------------------------------------------------------------------------------ the check
@dataclass(frozen=True)
class Precheck:
    site_id: str
    status: str
    reason: str
    served: Mapping[str, Any]
    qid: str | None
    p18: tuple[str, ...] = ()
    p373: tuple[str, ...] = ()
    file_title: str | None = None
    file_categories: tuple[str, ...] | None = None

    def as_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["served"] = dict(self.served)
        return out


def decide(
    served: Served,
    qid: str | None,
    entity: Mapping[str, Any] | None,
    info: FileInfo | None,
) -> Precheck:
    """One site's pre-check. `info` is Commons' answer about the served file (None when the image
    names no Commons file)."""
    base: dict[str, Any] = {"site_id": served.site_id, "served": served.as_json(), "qid": qid}
    if served.kind == NONE:
        return Precheck(status=NO_IMAGE, reason="the site serves no image", **base)
    if qid is None or entity is None:
        return Precheck(status=UNCONFIRMED, reason="the site has no Wikidata item", **base)
    if "missing" in entity:
        return Precheck(status=UNCONFIRMED, reason=f"Wikidata holds no item {qid}", **base)
    p18, p373 = tuple(p18_files(entity)), tuple(p373_categories(entity))
    base.update(p18=p18, p373=p373)
    if served.file is None or info is None:
        return Precheck(status=UNCONFIRMED, reason="the served image names no Commons file", **base)
    names = {served.file} | ({info.title} if info.title else set())
    if names & set(p18):
        return Precheck(status=CONFIRMED_P18, reason="the file is the item's image (P18)", **base)
    if info.status != OK:
        return Precheck(
            status=UNCONFIRMED, reason=f"Commons answers {info.status} for the file", **base
        )
    base.update(file_title=info.title, file_categories=info.categories)
    hit = sorted(set(p373) & set(info.categories))
    if hit:
        return Precheck(
            status=CONFIRMED_P373,
            reason=f"the file is in the item's Commons category {hit[0]!r} (P373)",
            **base,
        )
    reason = (
        "the file is neither the item's image (P18) nor in its Commons category (P373)"
        if p18 or p373
        else "the item names no image (P18) and no Commons category (P373)"
    )
    return Precheck(status=UNCONFIRMED, reason=reason, **base)


@dataclass
class Result:
    checks: list[Precheck] = field(default_factory=list)
    not_in_harvest: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        out = dict.fromkeys(STATUSES, 0)
        for check in self.checks:
            out[check.status] += 1
        out["sites"] = len(self.checks)
        out["not_in_harvest"] = len(self.not_in_harvest)
        return out


def run_precheck(
    state: State, harvest: Harvest, commons: Commons, *, subset: bool = False
) -> Result:
    """The pre-check of every site of the read. A shown site the harvest does not list is
    refused, unless `subset` - a measured sample - names the harvest's sites as the population; a
    harvest site the read neither shows nor knows as retired (WD1's harvest lists every curated
    site, the retired ones too) is refused as well."""
    missing = [sid for sid in state.site_ids() if sid not in harvest.qids]
    stray = [sid for sid in harvest.qids if sid not in state.sites and sid not in state.retired]
    if missing and not subset:
        raise HarvestError(
            f"{len(missing)} site(s) of the read are not in the harvest (first {missing[0]}) - "
            "the harvest must cover every curated site, or pass --subset for a sample"
        )
    if stray and not subset:
        raise HarvestError(
            f"the harvest lists {len(stray)} site(s) the read neither shows nor knows as retired "
            f"(first {stray[0]}): not curated, or curated since the harvest"
        )
    population = [sid for sid in state.site_ids() if sid in harvest.qids]
    served = {sid: served_of(state.sites[sid], state.rows.get(sid, ())) for sid in population}
    files = [s.file for s in served.values() if s.file is not None]
    infos = commons.categories(files)
    result = Result(not_in_harvest=missing)
    for sid in population:
        qid = harvest.qids[sid]
        entity = harvest.entity(qid) if qid else None
        s = served[sid]
        info = infos.get(s.file) if s.file else None
        result.checks.append(decide(s, qid, entity, info))
    return result


def write_prechecks(path: Path, result: Result) -> str:
    """PRECHECK.jsonl, written once per run directory. Returns its sha256."""
    return write_text_once(path, jsonl_text(c.as_json() for c in result.checks))


def load_prechecks(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise HarvestError(f"{path} does not exist - run `run.py precheck` first")
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["status"] not in STATUSES or row["site_id"] in out:
                raise HarvestError(f"{path}: a line that is no pre-check: {line[:120]}")
            out[row["site_id"]] = row
    return out
