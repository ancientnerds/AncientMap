"""S7 - the three label sets calibration measures the vision stage against.

(i)   The 200 pilot tiles (`output/remediation/vlm_pilot/SAMPLE.jsonl`, seed 20260921, 50 per T10
      tier) with the pilot's kinds (`VLM.jsonl`) and, once W8 has written it, the blinded eye
      labels (`LABELS.jsonl`).
(ii)  The 652-image labelled set of 2026-09-19 (`output/audit_inventory/_labeled_images.json`,
      40 sites). That file is local-only and untracked, so `derive` turns it into the tracked
      fixture `tests/remediation/fixtures/gallery_labels_652.jsonl`: one line per checked row with
      its label classes. "Checked" is measured, not assumed: every site's `checked` count equals
      its non-excluded rows in the snapshot (652 = 672 - 20 excluded), so the population is the
      non-excluded rows and a row without a label was checked and found usable.
(iii) The three gold galleries (`output/remediation/gold_standard/sites.json`): Agri Bavnehoj,
      Langdale Axe Industry, Xcaret - the rows the gold records name as another place and the rows
      they name as correct, each pinned to its image id with the sentence that names it.

Matching labels to rows
-----------------------
The label entries are prose ("fremde_staette: Ollantaytambo_Monolithen.webp - Die 'Wand der sechs
Monolithen' ..."). The matcher is the one `output/remediation/t09_label_measurement.py` measured
(untracked scratch, moved here): an entry names a file by a `File:` reference or by its leading
file name, and a hint matches a row when its normal form equals the row's file name or title, or
- failing that - is the unique prefix of one. One change, measured: a hint without `.webp` used to
end at the first " - ", which cut "Berlín - Pergamon - Porta d'Ishtar - Lleons" to "Berlín"; the
longest " - " prefix that equals a row now wins.

Twenty entries speak about several files at once ("Sechs Bilder aus San Lorenzo Tenochtitlan:
'San Lorenzo Colossal Head 10/2/7/8' sowie ..."). The plan's corrected count of 65 foreign images
(`docs/procedures/SITES_DB_REMEDIATION_2026-09.md` 6.1) resolved them by hand; `COLLECTIONS` makes
that resolution explicit and checkable: every member carries the verbatim span of the entry that
names it, and a member is a hint that must occur in exactly one row's file name.

Usage:
    labels.py derive [--source _labeled_images.json] [--snapshot DIR]   # rewrites the fixture
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_REMEDIATION = ROOT / "scripts" / "remediation"
if str(_REMEDIATION) not in sys.path:
    sys.path.insert(0, str(_REMEDIATION))

from census.snapshot import Snapshot  # noqa: E402
from hero_repair.plan import commons_file_name  # noqa: E402

from gallery_audit import vision  # noqa: E402

LABELS_SOURCE = ROOT / "output" / "audit_inventory" / "_labeled_images.json"
DEFAULT_SNAPSHOT = ROOT / "output" / "remediation" / "snapshot"
FIXTURE = ROOT / "tests" / "remediation" / "fixtures" / "gallery_labels_652.jsonl"
FIXTURE_META = ROOT / "tests" / "remediation" / "fixtures" / "gallery_labels_652.meta.json"
PILOT_DIR = ROOT / "output" / "remediation" / "vlm_pilot"
PILOT_SAMPLE = PILOT_DIR / "SAMPLE.jsonl"
PILOT_VLM = PILOT_DIR / "VLM.jsonl"
B4_LABELS = PILOT_DIR / "LABELS.jsonl"
GOLD_SITES = ROOT / "output" / "remediation" / "gold_standard" / "sites.json"

FOREIGN = "fremde_staette"
NON_PHOTO = ("gemaelde_oder_zeichnung", "karte_oder_plan", "diagramm_oder_text")
#: "Not an image of this site" for X2/X3 (design: pilot_and_thresholds): the foreign and the
#: non-photo classes plus modern surroundings - the plan's 138 content-unusable images. `sonstiges`
#: is left out on purpose: it mixes junk (a banknote, a plant) with notes that are no defect at all
#: ("KEIN Mangel ... das EINZIGE korrekte Bild"), and no rule can tell them apart.
NOT_THIS_SITE = (FOREIGN, *NON_PHOTO, "modernes_umfeld")
LABEL_CLASSES = (
    FOREIGN,
    *NON_PHOTO,
    "modernes_umfeld",
    "zu_klein",
    "duplikat",
    "fehlende_attribution",
    "sonstiges",
)
#: The plan's corrected count of foreign images in the set (6.1) - the reference T-X1's
#: "at least 60 of the 65 resolve to rows" is stated against.
PLAN_FOREIGN = 65

ENTRY_RE = re.compile(r"^(?P<cls>[a-z_äöü]+)(?P<hero> \(HERO\))?\s*:\s*(?P<rest>.*)$", re.S)
FILE_RE = re.compile(r"(?:Commons:\s*)?File:(?P<n>[^)\-]+)")


class LabelError(RuntimeError):
    """A label set that cannot be read without guessing."""


# ------------------------------------------------------------------------------ matching
def norm(text: str) -> str:
    text = re.sub(r"\.(webp|jpe?g|png|gif|tiff?)$", "", str(text).strip(), flags=re.I)
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip().casefold()


def match(
    rows: Sequence[Mapping[str, Any]], hint: str, hero: bool | None = None
) -> Mapping[str, Any] | None:
    """One row for a file-name hint, or None when the match is not unique.

    'Gamzigrad' is both a hero row's title and another row's file name, so a first hit would
    compare the wrong two rows; the entry's HERO mark breaks that tie, and without it the match
    has to be unique to count.
    """
    key = norm(hint)
    if len(key) < 4:
        return None
    exact = [r for r in rows if key in r["_keys"]]
    if exact:
        pool = exact
        if hero is not None:
            marked = [r for r in exact if bool(r["is_hero"]) == hero]
            if marked:
                pool = marked
        return pool[0] if len(pool) == 1 else None
    # An empty key (a row without a title) is a prefix of every hint, so it is no key at all here.
    loose = [
        r for r in rows if any(k and (k.startswith(key) or key.startswith(k)) for k in r["_keys"])
    ]
    return loose[0] if len(loose) == 1 else None


def match_entry(
    rows: Sequence[Mapping[str, Any]], rest: str, hero: bool
) -> Mapping[str, Any] | None:
    """The row one single-file entry names, or None."""
    ref = FILE_RE.search(rest)
    if ref:
        hit = match(rows, ref.group("n"), hero)
        if hit is not None:
            return hit
    webp = re.match(r"^(.+?\.webp)", rest)
    if webp:
        return match(rows, webp.group(1), hero)
    parts = rest.split(" - ")
    for size in range(len(parts), 0, -1):
        candidate = " - ".join(parts[:size]).strip()
        if [r for r in rows if norm(candidate) in r["_keys"]]:
            return match(rows, candidate, hero)
    return match(rows, parts[0].strip(), hero)


@dataclass(frozen=True)
class Member:
    """One file of a collection entry: the span that names it, and how its row is found.

    `how` is "contains" (the hint occurs in exactly one row's normalised file name), "exact" (the
    normalised file name is the hint) or "hero" (the site's hero row at labelling time).
    """

    span: str
    hint: str
    how: str = "contains"


@dataclass(frozen=True)
class Collection:
    site: str
    entry_start: str
    members: tuple[Member, ...]


#: The multi-file entries, resolved member by member. `span` is verbatim entry text; `hint` must
#: occur in exactly one checked row's normalised file name ("hero" names the site's hero row).
COLLECTIONS: tuple[Collection, ...] = (
    Collection(
        "La Cobata",
        "fremde_staette: San_Lorenzo_Colossal_Head_10.webp",
        (
            Member("'San Lorenzo Colossal Head 10/2/7/8'", "san lorenzo colossal head 10"),
            Member("'San Lorenzo Colossal Head 10/2/7/8'", "san lorenzo colossal head 2"),
            Member("'San Lorenzo Colossal Head 10/2/7/8'", "san lorenzo colossal head 7"),
            Member("'San Lorenzo Colossal Head 10/2/7/8'", "san lorenzo colossal head 8"),
            Member("'San Lorenzo Monument 3 crop'", "san lorenzo monument 3 crop"),
            Member("'San Lorenzo Monument 4 crop'", "san lorenzo monument 4 crop"),
        ),
    ),
    Collection(
        "La Cobata",
        "fremde_staette: La_Venta_Colossal_Head_3.webp",
        (
            Member("'La Venta Colossal Head 3'", "la venta colossal head 3"),
            Member("'La Venta Monument 4'", "la venta monument 4"),
            Member("'Olmec2'", "olmec2"),
            Member("'Olmeca head in Villahermosa'", "olmeca head in villahermosa"),
            Member("'Olmec Head, Mexico, c. 1960'", "olmec head, mexico, c. 1960"),
        ),
    ),
    Collection(
        "La Cobata",
        "fremde_staette: Cabeza_olmeca,_museo_de_San_Andrés_Tuxtla.webp",
        (
            Member(
                "Cabeza_olmeca,_museo_de_San_Andrés_Tuxtla.webp",
                "cabeza olmeca, museo de san andrés tuxtla",
            ),
            Member("'Tres Zapotes Monument A.webp'", "tres zapotes monument a"),
        ),
    ),
    Collection(
        "Ishtar Gate",
        "fremde_staette: Istanbul Ancient Orient Museum Ishtar Gate Bull walking right in 2019 08 2184",
        (
            Member("…08 2184", "2019 08 2184"),
            Member("…32 2176", "2019 32 2176"),
            Member("…33 2177", "2019 33 2177"),
            Member("…51 2187", "2019 51 2187"),
            Member("…52 2188", "2019 52 2188"),
        ),
    ),
    Collection(
        "Overton Hill",
        "fremde_staette: Thesanctuary.webp",
        (
            Member("Thesanctuary,", "thesanctuary", "exact"),
            Member("Sanctuary join to West Kennet Avenue", "sanctuary join to west kennet avenue"),
            Member("Sanctuary looking toward hedge", "sanctuary, looking toward hedge"),
            Member("Information Board", "information board"),
            Member("Stukeley-Stich", "stukeley"),
            Member("Hero TheSanctuary2011", "", "hero"),
        ),
    ),
)


def _collection_for(site: str, entry: str) -> Collection | None:
    hits = [c for c in COLLECTIONS if c.site == site and entry.startswith(c.entry_start)]
    if len(hits) > 1:
        raise LabelError(f"{site}: two collections claim one entry")
    return hits[0] if hits else None


def _member_row(rows: Sequence[Mapping[str, Any]], member: Member) -> Mapping[str, Any]:
    if member.how == "hero":
        hits = [r for r in rows if r["is_hero"]]
    elif member.how == "exact":
        hits = [r for r in rows if r["_keys"][0] == member.hint]
    elif member.how == "contains":
        hits = [r for r in rows if member.hint in r["_keys"][0]]
    else:
        raise LabelError(f"unknown member lookup {member.how!r}")
    if len(hits) != 1:
        raise LabelError(f"collection member {member.span!r} matches {len(hits)} rows, not one")
    return hits[0]


def _entry_sha(entry: str) -> str:
    return hashlib.sha256(entry.encode("utf-8")).hexdigest()[:12]


# ------------------------------------------------------------------------------ (ii) derive
def derive(source: Path, snapshot: Snapshot) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The fixture lines (every checked row, with its classes) and the derivation's own record."""
    raw = source.read_bytes()
    labelled = json.loads(raw.decode("utf-8"))
    ids_by_name: dict[str, list[str]] = defaultdict(list)
    for site in snapshot.sites:
        ids_by_name[str(site.get("name"))].append(str(site["id"]))

    lines: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    via: Counter[str] = Counter()
    for block in labelled:
        ids = ids_by_name.get(block["name"], [])
        if len(ids) != 1:
            raise LabelError(f"label site {block['name']!r} names {len(ids)} snapshot sites")
        sid = ids[0]
        rows = []
        for row in snapshot.images(sid):
            if row.get("is_excluded"):
                continue
            rows.append(
                {
                    **row,
                    "_keys": [norm(row["filename"]), norm(row.get("title") or "")],
                    "_labels": set(),
                    "_entries": set(),
                }
            )
        if len(rows) != block["checked"]:
            raise LabelError(
                f"{block['name']}: {block['checked']} checked, {len(rows)} non-excluded rows - the "
                "checked population is not the non-excluded rows any more"
            )
        for entry in block["problems"]:
            parsed = ENTRY_RE.match(entry)
            if parsed is None:
                unresolved.append(
                    {"site": block["name"], "entry": entry[:160], "why": "no class prefix"}
                )
                continue
            cls, hero, rest = parsed.group("cls"), bool(parsed.group("hero")), parsed.group("rest")
            if cls not in LABEL_CLASSES:
                raise LabelError(f"{block['name']}: unknown label class {cls!r}")
            collection = _collection_for(block["name"], entry)
            if collection is not None:
                for member in collection.members:
                    if member.span not in entry:
                        raise LabelError(
                            f"{block['name']}: the span {member.span!r} is not in its entry"
                        )
                    row = _member_row(rows, member)
                    row["_labels"].add(cls)
                    row["_entries"].add(_entry_sha(entry))
                    via["collection"] += 1
                continue
            row = match_entry(rows, rest, hero)
            if row is None:
                unresolved.append(
                    {"site": block["name"], "entry": entry[:160], "why": "no unique row"}
                )
                continue
            row["_labels"].add(cls)
            row["_entries"].add(_entry_sha(entry))
            via["single"] += 1
        for row in sorted(rows, key=lambda r: int(r["id"])):
            lines.append(
                {
                    "site_id": sid,
                    "site_name": block["name"],
                    "image_id": int(row["id"]),
                    "filename": row["filename"],
                    "commons_file": commons_file_name(row),
                    "hero_at_labelling": bool(row["is_hero"]),
                    "labels": sorted(row["_labels"]),
                    "entries": sorted(row["_entries"]),
                }
            )
    per_class = Counter(cls for line in lines for cls in line["labels"])
    meta = {
        "source": "output/audit_inventory/_labeled_images.json",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "snapshot_exported_at": snapshot.exported_at(),
        "sites": len(labelled),
        "rows": len(lines),
        "rows_labelled": sum(1 for line in lines if line["labels"]),
        "rows_per_class": dict(sorted(per_class.items())),
        "matched": dict(sorted(via.items())),
        "unresolved_entries": unresolved,
        "plan_foreign_reference": PLAN_FOREIGN,
    }
    return lines, meta


def write_fixture(
    lines: Sequence[Mapping[str, Any]],
    meta: Mapping[str, Any],
    path: Path = FIXTURE,
    meta_path: Path = FIXTURE_META,
) -> None:
    text = "".join(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n" for line in lines)
    path.write_text(text, encoding="utf-8", newline="\n")
    full = {**meta, "fixture_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    meta_path.write_text(
        json.dumps(full, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


@dataclass(frozen=True)
class LabelledRow:
    site_id: str
    image_id: int
    labels: frozenset[str]

    @property
    def foreign(self) -> bool:
        return FOREIGN in self.labels

    @property
    def non_photo(self) -> bool:
        return bool(self.labels & set(NON_PHOTO))

    @property
    def not_this_site(self) -> bool:
        return bool(self.labels & set(NOT_THIS_SITE))


def load_labelled(path: Path = FIXTURE) -> list[LabelledRow]:
    """The tracked 652-row fixture."""
    out = []
    seen: set[int] = set()
    for lineno, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = json.loads(text)
        labels = frozenset(line["labels"])
        if labels - set(LABEL_CLASSES):
            raise LabelError(
                f"{path}:{lineno}: unknown label class {sorted(labels - set(LABEL_CLASSES))}"
            )
        if line["image_id"] in seen:
            raise LabelError(f"{path}:{lineno}: image {line['image_id']} twice")
        seen.add(line["image_id"])
        out.append(LabelledRow(str(line["site_id"]), int(line["image_id"]), labels))
    return out


# ------------------------------------------------------------------------------ (i) pilot
@dataclass(frozen=True)
class PilotTile:
    image_id: int
    site_id: str
    tier: str
    pilot_kind: str


def pilot_tiles(sample: Path = PILOT_SAMPLE, vlm: Path = PILOT_VLM) -> list[PilotTile]:
    """The 200 pilot tiles and the kind the pilot's model gave each (`VLM.jsonl`)."""
    kinds = {}
    for text in vlm.read_text(encoding="utf-8").splitlines():
        record = json.loads(text)
        if record["kind"] not in vision.KINDS:
            raise LabelError(f"{vlm}: image {record['image_id']} has no pilot kind")
        kinds[int(record["image_id"])] = record["kind"]
    tiles = []
    for text in sample.read_text(encoding="utf-8").splitlines():
        row = json.loads(text)
        image_id = int(row["image_id"])
        if image_id not in kinds:
            raise LabelError(f"{vlm} has no verdict for sampled image {image_id}")
        tiles.append(PilotTile(image_id, str(row["site_id"]), str(row["tier"]), kinds[image_id]))
    if len({t.image_id for t in tiles}) != len(tiles):
        raise LabelError(f"{sample} samples one image twice")
    return tiles


@dataclass(frozen=True)
class EyeLabel:
    """One B4 tile label (W8). `shows_archaeology` is what T-strict needs on the tier-A tiles."""

    image_id: int
    human_kind: str | None
    shows_archaeology: bool | None
    other_site: bool | None


def load_eye_labels(path: Path, tiles: Iterable[PilotTile]) -> dict[int, EyeLabel]:
    """`LABELS.jsonl` - refused when it names an image outside the sample or a kind outside the six."""
    known = {tile.image_id for tile in tiles}
    out: dict[int, EyeLabel] = {}
    for lineno, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not text.strip():
            continue
        record = json.loads(text)
        image_id = record.get("image_id")
        if image_id not in known:
            raise LabelError(f"{path}:{lineno}: image {image_id!r} is not a pilot tile")
        if image_id in out:
            raise LabelError(f"{path}:{lineno}: image {image_id} labelled twice")
        kind = record.get("human_kind")
        if kind is not None and kind not in vision.KINDS:
            raise LabelError(f"{path}:{lineno}: human_kind {kind!r} is not one of the six kinds")
        flags = {}
        for key in ("shows_archaeology", "other_site"):
            value = record.get(key)
            if value is not None and not isinstance(value, bool):
                raise LabelError(f"{path}:{lineno}: {key} is {value!r}, not a boolean or null")
            flags[key] = value
        out[image_id] = EyeLabel(image_id, kind, flags["shows_archaeology"], flags["other_site"])
    return out


# ------------------------------------------------------------------------------ (iii) gold
@dataclass(frozen=True)
class GoldRow:
    site_id: str
    image_id: int
    filename: str
    foreign: bool
    quote: str


AGRI = "94776f9f-ea10-4b05-87bd-fd30c2cbdf6f"
LANGDALE = "c63b0df7-79e5-4734-bb99-b17ccd8f54eb"
XCARET = "cad0ee78-1954-4ca9-b8e4-dde794c99117"
GOLD_SITE_IDS = (AGRI, LANGDALE, XCARET)

#: Every gold row the records name, with the words that name it (verbatim from `sites.json`).
#: Agri's old hero (86284, Commons "Stabelhøi.45118") lost its hero flag in the hero repair and is
#: now a gallery row; its record calls it "the neighbour's mound", so it is gold-foreign too - 12
#: rows, one more than the design's list of 11, which counted Agri's gallery rows before the swap.
GOLD_ROWS: tuple[GoldRow, ...] = (
    GoldRow(
        AGRI,
        86273,
        "Agri (Syddjurs Kommune).Stabelhøje og Stabelhøi.45115.45118.ajb.webp",
        True,
        "'Agri (Syddjurs Kommune).Stabelhoje og Stabelhoi.45115.45118.ajb.jpg'",
    ),
    GoldRow(
        AGRI,
        86274,
        "Agri (Syddjurs Kommune).Stabelhøje.45115.ajb.webp",
        True,
        "'Agri (Syddjurs Kommune).Stabelhoje.45115.ajb.jpg'",
    ),
    GoldRow(AGRI, 86283, "Stabelhøje_udsigt_1.webp", True, "'Stabelhoje udsigt 1.JPG'"),
    GoldRow(AGRI, 86284, "hero.webp", True, "the hero shows the neighbour's mound"),
    GoldRow(AGRI, 86275, "Agri Bavnehøj from west..webp", False, "'Agri Bavnehøj from west..jpg'"),
    GoldRow(AGRI, 86276, "Agri baunehøj12.webp", False, "'Agri baunehoj12.JPG'"),
    GoldRow(
        AGRI, 86277, "Agri baunehøj7.webp", False, "'Agri baunehoj7.JPG' (the protection plate)"
    ),
    GoldRow(AGRI, 86278, "Agri_Bavnehøj,_Udsigt.webp", False, "'Agri Bavnehøj, Udsigt.jpg'"),
    GoldRow(AGRI, 86279, "Agri_Bavnehøj,_vinter.webp", False, "'Agri Bavnehøj, vinter.JPG'"),
    GoldRow(AGRI, 86280, "Agri_Bavnehøj,_vinter_2.webp", False, "'Agri Bavnehøj, vinter 2.JPG'"),
    GoldRow(
        AGRI, 86281, "Postament på Agri Baunehøj.webp", False, "'Postament på Agri Baunehoj.jpg'"
    ),
    GoldRow(
        AGRI,
        86282,
        "Skilt på postament på Agri Baunehøj.webp",
        False,
        "'Skilt på postament på Agri Baunehoj.jpg'",
    ),
    GoldRow(
        LANGDALE, 95876, "Castlerigg.webp", True, "'File:Castlerigg.jpg' - Castlerigg Stone Circle"
    ),
    GoldRow(
        LANGDALE,
        95877,
        "Horsne_dibjars_i.webp",
        True,
        "'File:Horsne dibjars i.jpg' - 'Grooves from Horsne, Gotland, Sweden'",
    ),
    GoldRow(
        LANGDALE, 95879, "MaloneHoard.webp", True, "'File:MaloneHoard.JPG' - a Neolithic axe hoard"
    ),
    GoldRow(
        LANGDALE,
        95880,
        "Mount_William_Aboriginal_stone_axe_quarry.webp",
        True,
        "'File:Mount William Aboriginal stone axe quarry.jpg' - an Aboriginal axe quarry in Victoria, Australia",
    ),
    GoldRow(
        LANGDALE,
        95881,
        "Neolithic_stone_axe_with_handle_ehenside_tarn_british_museum.webp",
        True,
        "is a Neolithic hafted axe from Ehenside Tarn - same period, same object class, different site",
    ),
    GoldRow(
        LANGDALE, 95878, "Langdales,_Westmorland.webp", False, "File:Langdales, Westmorland.jpg"
    ),
    GoldRow(LANGDALE, 95882, "Pike_O'Stickle.webp", False, "File:Pike O'Stickle.jpg"),
    GoldRow(
        LANGDALE,
        95883,
        "Pike_of_Stickle_from_Loft_Crag.webp",
        False,
        "File:Pike of Stickle from Loft Crag.jpg",
    ),
    GoldRow(
        XCARET,
        97034,
        "Bigcats (17892303602).webp",
        True,
        "'File:Bigcats (17892303602).jpg' (zoo animals)",
    ),
    GoldRow(
        XCARET,
        97038,
        "Orchids (17895315075).webp",
        True,
        "'File:Orchids (17895315075).jpg' (flowers)",
    ),
    GoldRow(
        XCARET,
        97051,
        "_ Our Lady of Guadalupe, Xcaret Eco Park _.webp",
        True,
        "'Our Lady of Guadalupe, Xcaret Eco Park' (a chapel in the theme park)",
    ),
    GoldRow(
        XCARET, 97035, "Cabin Ruins - panoramio.webp", False, "'File:Cabin Ruins - panoramio.jpg'"
    ),
    GoldRow(XCARET, 97039, "Parque arqueológico.webp", False, "'File:Parque arqueologico.jpg'"),
)


def gold_notes(path: Path = GOLD_SITES) -> dict[str, str]:
    """site id -> every hero/gallery verdict note of that gold record, joined - what a quote must
    be found in."""
    records = json.loads(path.read_text(encoding="utf-8"))["records"]
    out = {}
    for record in records:
        if record["site_id"] in GOLD_SITE_IDS:
            out[record["site_id"]] = "\n".join(
                str(v.get("note") or "")
                for v in record["verdicts"]
                if v["field"] in ("hero_image", "gallery_images")
            )
    return out


# ------------------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    der = sub.add_parser(
        "derive", help="rebuild the tracked 652-row fixture from the local label file"
    )
    der.add_argument("--source", default=str(LABELS_SOURCE))
    der.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    der.add_argument("--out", default=str(FIXTURE))
    args = parser.parse_args(argv)
    snapshot = Snapshot(args.snapshot)
    snapshot.verify()
    lines, meta = derive(Path(args.source), snapshot)
    out = Path(args.out)
    write_fixture(lines, meta, out, out.with_name(out.stem + ".meta.json"))
    print(
        json.dumps(
            {k: v for k, v in meta.items() if k != "unresolved_entries"},
            indent=1,
            ensure_ascii=False,
        )
    )
    print(f"unresolved entries: {len(meta['unresolved_entries'])}")
    for item in meta["unresolved_entries"]:
        print(f"  [{item['site']}] {item['why']}: {item['entry'][:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
