"""The reviewed repair of mis-resolved `site_external_ids` rows: rendered here, applied by nobody here.

`site_external_ids` is filled by `pipeline/lyra/prospector/external_ids.py` from each curated site's
`source_url`: the enwiki title in the URL is resolved (redirects followed) and its title and Wikidata
item are stored. Twenty curated sites carry an id that names something other than the site. For the
thirteen generic ids the `source_url` itself names the generic article
(`https://en.wikipedia.org/wiki/History`, `.../Archaeology`, `.../Theatre`, `.../Temples_(band)`); for two
of them the stored name redirects to exactly that section of another article (`Estipeon` -> `Štip#History`,
`Castellum Onagrinum` -> `Begeč#Archaeology`), which looks like a section fragment taken as a title - for
the other eleven how the URL was made is not established. The Tomb of Artaxerxes III's URL is its own
title, which redirects to `Persepolis#Tombs`, so the redirect gave it Persepolis' item. So seven sites
are routed to Q309 ("history", the discipline), two to Q23498 ("archaeology"), three to Q11635
("theatre"), Stabiae to an English rock band, and five Gyeongju belts to their shared World Heritage
parent. Every later pass that asks Wikidata about these sites asks about the wrong thing.

Each site was re-resolved **one at a time** on 2026-09-22 (read-only: `wbsearchentities` by name and
variants, `wbgetentities` for every candidate, a WDQS `wikibase:around` search of 0.6 km for the three
theatres, the enwiki page for the stored name), under two rules and nothing else:

* **A - the stored name is an existing enwiki article's exact title**: the article's own item, the
  identity `external_ids.py` would have stored had the `source_url` been right (confidence
  `two_source`: the article and the item agree);
* **B - otherwise, one item whose label names the site, of the site's kind, at the site's place**
  (confidence `authoritative`).

A site neither rule settles is **unresolved**: the plan leaves its row exactly as it is and lists it.
`enwiki_title` is changed only where the new item links a real English article (not a redirect); a
generic title with no replacement stays and is listed, because replacing it would take a `DELETE`.

What this renders into `output/remediation/qid_repair/` (nothing is applied):

* `PLAN.jsonl` - one row per change, with its evidence and change key;
* `APPLY.sql` - one transaction: guards, a conditional `UPDATE ... WHERE site_id, kind, value = old`
  per row, one journal row each, invariants, `COMMIT`;
* `REHEARSAL.sql` - the same statement ending in `ROLLBACK` (not versioned: it keeps nothing);
* `ROLLBACK.sql` - the inverse, conditional on the new value, journalled under its own stamp;
* `PLAN.md` - the per-site evidence and the unresolved list.

**Why not `apply_remediation_change`.** The primitive addresses a row by one key column
(`WHERE <pk_col>::text = $pk`) and re-reads it by that column for its round-trip check. The key of
`site_external_ids` is `(site_id, kind, value)` and every one of these sites has two rows (its
`enwiki_title` and its `wikidata_qid`), so no single column names the row: by `site_id` the re-read
returns two rows and compares whichever comes first. The statements here therefore do what the
primitive does, spelled for a composite key - the conditional `UPDATE` must match exactly one row,
the row is re-read by its full key, and the journal row is written in the same transaction - and the
plan digest pins both statements to `PLAN.jsonl` (`-- plan digest sha256:`), as `write_stage` does.

**Fixed point.** The boot path (`refresh_site_external_ids(only_missing=True)`, `prospector/__init__.py`)
only reads sites that have no row at all, so a repaired row stays repaired. The manual
`--all` path would insert the `source_url`'s id again beside the repaired one (the key includes the
value, `ON CONFLICT DO NOTHING` does not collide) - that stays true until the twenty `source_url`
values are corrected, which is a separate change to a column many producers read and is listed in
`PLAN.md`, not made here.

    ./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py render
    ./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py check    # read-only pre-flight
    ./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py verify   # read-only, after apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from dataclasses import asdict, dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - paths, the JSON-lines reader and the read-only psql seam

OUT = lanes.REMEDIATION / "qid_repair"
RUN_STAMP = "2026-09-22_external-id-repair"
ROLLBACK_STAMP = RUN_STAMP + "-rollback"
TABLE = "site_external_ids"
DIGEST_HEADER = "-- plan digest sha256:"
KINDS = ("wikidata_qid", "enwiki_title")


@dataclass(frozen=True)
class Site:
    """One site's re-resolution, as researched on 2026-09-22."""

    site_id: str
    name: str
    rule: str  #: "A", "B" or "unresolved"
    old_qid: str
    new_qid: str | None
    old_title: str
    new_title: str | None
    evidence: tuple[str, ...]


WD = "https://www.wikidata.org/wiki/"
WP = "https://en.wikipedia.org/wiki/"

SITES: tuple[Site, ...] = (
    Site(
        "e8e302a0-70b2-4346-ac75-340a4d6499a2",
        "Argos, Peloponnese",
        "A",
        "Q309",
        "Q189901",
        "History",
        "Argos, Peloponnese",
        (
            f"{WP}Argos,_Peloponnese: the stored name is this article's exact title; its item is "
            "Q189901 'city in Argolis, Peloponnese, Greece' (P31 city, polis), P625 2.14 km from "
            "the stored point",
            f"{WD}Q13533353 'ancient Greek city-state' lies 0.02 km from the stored point but has "
            "no English article; rule A names the article the record is titled after",
        ),
    ),
    Site(
        "1c4ac177-bcca-4044-8e2d-4d15fe0606ab",
        "City of Enns",
        "B",
        "Q309",
        "Q260089",
        "History",
        "Enns (town)",
        (
            "no enwiki article 'City of Enns'",
            f"{WD}Q260089 'Enns' - 'municipality in Linz-Land District, Upper Austria', P625 0.02 km, "
            "enwiki 'Enns (town)': the item the stored name names",
            f"{WD}Q388745 'Lauriacum' (0.02 km) is the Roman city the description is about; the "
            "name is the town, so rule B takes the town and the owner may prefer Lauriacum",
        ),
    ),
    Site(
        "f31b4aea-5e0d-42f8-80f0-60fcf2f3c37f",
        "Clare, Suffolk",
        "A",
        "Q309",
        "Q2559341",
        "History",
        "Clare, Suffolk",
        (
            f"{WP}Clare,_Suffolk: the stored name is this article's exact title; its item is "
            "Q2559341 'town in West Suffolk, England', P625 0.02 km",
        ),
    ),
    Site(
        "7279cb69-c5d2-4b9b-b307-96ef43164e7f",
        "Crantit Chambered Cairn",
        "B",
        "Q309",
        "Q1138920",
        "History",
        None,
        (
            f"{WD}Q1138920 'Crantit' - 'chambered cairn on Mainland, Orkney Islands', P31 chambered "
            "cairn, P625 1.31 km; the record: a Neolithic chambered cairn found 1998 near Kirkwall",
            "no English article (enwiki 'Crantit', 'Crantit tomb', 'Crantit Tomb' missing; the item "
            "links only dewiki 'Crantit Cairn'): the title 'History' has no replacement",
        ),
    ),
    Site(
        "5fffbfc9-f83c-4cd3-9b8d-d2570ce63dbd",
        "Estipeon",
        "B",
        "Q309",
        "Q4810863",
        "History",
        None,
        (
            f"{WD}Q4810863 'Astibo' - 'archaeological site in Macedonia', P31 archaeological site, "
            "P625 0.02 km; the record calls the site 'Estipeon (ancient Astibus)'",
            f"{WD}Q5401395 'Estipeon' carries no statement at all, only a sitelink to a redirect",
            f"{WP}Estipeon and {WP}Astibo both redirect to 'Štip#History' - the section fragment "
            "that became the stored 'History'; no article of its own, so no title replacement",
        ),
    ),
    Site(
        "935c0e07-0e4c-4bf9-a2ea-0113c70a3e3c",
        "Gog Magog Hills",
        "A",
        "Q309",
        "Q369156",
        "History",
        "Gog Magog Hills",
        (
            f"{WP}Gog_Magog_Hills: the stored name is this article's exact title; its item is "
            "Q369156 'range of hills in Cambridgeshire', P625 0.06 km",
        ),
    ),
    Site(
        "52827c54-91cb-4902-99fb-7b0860a71e36",
        "Tlalpan",
        "A",
        "Q309",
        "Q408187",
        "History",
        "Tlalpan",
        (
            f"{WP}Tlalpan: the stored name is this article's exact title; its item is Q408187 "
            "'territorial demarcation of Mexico City' (the borough the record describes), P625 "
            "7.94 km - the borough's centroid, the record's point is the burial find inside it",
        ),
    ),
    Site(
        "4fb5bdfa-4ff6-4897-a54c-7533e2bd2308",
        "Calleva Atrebatum",
        "A",
        "Q23498",
        "Q1027253",
        "Archaeology",
        "Calleva Atrebatum",
        (
            f"{WP}Calleva_Atrebatum: the stored name is this article's exact title; its item is "
            "Q1027253 'Romano-British town at Silchester', P625 0.02 km",
        ),
    ),
    Site(
        "3cde520c-1af6-47b0-84e0-00ec2db63478",
        "Castellum Onagrinum Archaeological Site, Begeč",
        "B",
        "Q23498",
        "Q12756529",
        "Archaeology",
        None,
        (
            f"{WD}Q12756529 labelled 'Castellum Onagrinum' / sr 'Онагринум', srwiki article "
            "'Онагринум', P625 1.14 km from the stored point on the Danube at Begeč",
            f"{WP}Castellum_Onagrinum redirects to 'Begeč#Archaeology' - the fragment that became "
            "the stored 'Archaeology'; no article of its own, so no title replacement",
        ),
    ),
    Site(
        "0f7ccb2e-da01-425e-9a4b-c50f4a785065",
        "Amfiteatar Salona",
        "B",
        "Q11635",
        "Q2844418",
        "Theatre",
        None,
        (
            f"{WD}Q2844418 'Roman amphitheatre of Salona' - 'amphitheatre in Salona, Croatia', P31 "
            "Roman amphitheatre, 0.04 km (WDQS around-search, 0.6 km radius)",
            "no English article: the title 'Theatre' has no replacement",
        ),
    ),
    Site(
        "1f34f490-a5ef-462d-961e-e4bbd8eb5422",
        "Hellenistic-Roman Theatre",
        "B",
        "Q11635",
        "Q70772384",
        "Theatre",
        None,
        (
            f"{WD}Q70772384 'Ancient theatre in Paphos', P31 Roman theatre, 0.05 km (WDQS "
            "around-search, 0.6 km radius); the record: the theatre of Nea Paphos",
            "no English article: the title 'Theatre' has no replacement",
        ),
    ),
    Site(
        "0c00d8bd-d6b3-4237-b4c9-9a86748ee5ab",
        "Κourion Ancient Amphitheatre",
        "B",
        "Q11635",
        "Q4453457",
        "Theatre",
        None,
        (
            f"{WD}Q4453457 'Roman Theatre of Kourion', P31 Roman theatre, 0.02 km (WDQS "
            "around-search, 0.6 km radius); the record: the Greco-Roman theatre of Kourion",
            "no English article: the title 'Theatre' has no replacement",
        ),
    ),
    Site(
        "0e7825f5-26f0-483e-8cd0-687a9228a894",
        "Stabiae",
        "A",
        "Q14832136",
        "Q547910",
        "Temples (band)",
        "Stabiae",
        (
            f"{WP}Stabiae: the stored name is this article's exact title; its item is Q547910 "
            "'ancient city, located near the current Castellammare di Stabia', P625 0.02 km",
            f"{WD}Q14832136 is an English rock band ('Temples (band)')",
        ),
    ),
    Site(
        "30d3fb78-6b80-42f9-87f8-7616e63bec4f",
        "Tikal",
        "unresolved",
        "Q6935864",
        None,
        "Mundo Perdido, Tikal",
        None,
        (
            "the record contradicts itself: its name is Tikal (enwiki 'Tikal' -> Q181172, 0.38 km) "
            "but its description and its source_url are Mundo Perdido, the complex inside Tikal "
            "(Q6935864, 0.14 km) that it is linked to now",
            "which one the record is, is the owner's decision (HUMAN_ONLY B1); nothing is changed",
        ),
    ),
    Site(
        "90e808a1-7ea7-44ce-a1c9-05cf10c133be",
        "Tomb of Artaxerxes III",
        "B",
        "Q129072",
        "Q9630189",
        "Persepolis",
        None,
        (
            f"{WD}Q9630189 'Tomb of Artaxerxes III' - 'tomb in Persepolis, Iran', P31 rock-cut tomb, "
            "0.10 km; Q129072 is Persepolis, the whole site",
            f"{WP}Tomb_of_Artaxerxes_III redirects to 'Persepolis#Tombs'; the item has no English "
            "article, and 'Persepolis' - the article the tomb is described in - stays as the title",
        ),
    ),
    Site(
        "62c8bf00-3a7e-46e6-81ac-2c6fc92af03f",
        "Mount Namsan Belt",
        "B",
        "Q495241",
        "Q66197428",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197428 'Namsam Belt' (sic), P361 part of Q495241 Gyeongju Historic Areas, "
            "P625 1.27 km; the record is that belt, not the whole World Heritage site",
        ),
    ),
    Site(
        "2b0f2420-5602-471f-b4be-eb03e7d33151",
        "The Hwangnyongsa Belt",
        "B",
        "Q495241",
        "Q66197439",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197439 'Hwangnyongsa Belt', P361 part of Q495241, P625 5.33 km: all six "
            "Gyeongju records store the parent's own point (Q495241 is 0.05 km from it), so the "
            "distance is the record's coordinate defect, not the item's",
        ),
    ),
    Site(
        "2dcdec07-a26e-42bc-9490-b277628835f5",
        "The Sanseong Belt",
        "B",
        "Q495241",
        "Q66197443",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197443 'Sanseong Belt', P361 part of Q495241, P625 6.49 km (the record stores "
            "the parent's point)",
        ),
    ),
    Site(
        "44d6f27b-3a9f-49d3-99fa-b1a65380776a",
        "The Tumuli Park Belt",
        "B",
        "Q495241",
        "Q66197435",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197435 'Tumuli Park Belt', P361 part of Q495241, P625 5.12 km (the record "
            "stores the parent's point)",
        ),
    ),
    Site(
        "e8bc112c-9e95-4728-b181-e78d7de1fa26",
        "The Wolseong Belt",
        "B",
        "Q495241",
        "Q66197431",
        "Gyeongju Historic Areas",
        None,
        (
            f"{WD}Q66197431 'Wolseong Belt', P361 part of Q495241, P625 4.57 km (the record stores "
            "the parent's point)",
        ),
    ),
)

#: The `source_url` each settled site should carry for the fix to be a fixed point under the
#: prospector's `--all` path. Listed, not written (module docstring).
GENERIC_SOURCE_URL = {
    "Q309": f"{WP}History",
    "Q23498": f"{WP}Archaeology",
    "Q11635": f"{WP}Theatre",
    "Q14832136": f"{WP}Temples_(band)",
}


@dataclass(frozen=True)
class Change:
    """One conditional update of one `site_external_ids` row, and what the journal records."""

    site_id: str
    name: str
    kind: str
    old_value: str
    new_value: str
    test_id: str
    confidence: str
    evidence: tuple[str, ...]
    change_key: str

    @property
    def row_pk(self) -> str:
        """The journal's `row_pk`: the site and the kind, which name the row across the change."""
        return f"{self.site_id}/{self.kind}"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)


def change_key(site_id: str, kind: str, old: str, new: str, test_id: str) -> str:
    parts = json.dumps([site_id, TABLE, kind, old, new, test_id], ensure_ascii=False)
    return "external-id:" + hashlib.sha256(parts.encode("utf-8")).hexdigest()


def changes(sites: tuple[Site, ...] = SITES) -> list[Change]:
    """Every row the plan changes, in site order then kind order. An unresolved site has none."""
    out: list[Change] = []
    seen: set[str] = set()
    for site in sites:
        if site.site_id in seen:
            raise SystemExit(f"{site.site_id} is planned twice")
        seen.add(site.site_id)
        if site.rule == "unresolved":
            if site.new_qid is not None or site.new_title is not None:
                raise SystemExit(f"{site.name}: an unresolved site cannot carry a new value")
            continue
        if site.rule not in ("A", "B") or site.new_qid is None:
            raise SystemExit(f"{site.name}: rule {site.rule!r} with new qid {site.new_qid!r}")
        confidence = "two_source" if site.rule == "A" else "authoritative"
        pairs = [("wikidata_qid", site.old_qid, site.new_qid)]
        if site.new_title is not None:
            pairs.append(("enwiki_title", site.old_title, site.new_title))
        for kind, old, new in pairs:
            if old == new:
                raise SystemExit(f"{site.name}: {kind} {old!r} is not a change")
            test_id = f"EXT/{kind}"
            out.append(
                Change(
                    site_id=site.site_id,
                    name=site.name,
                    kind=kind,
                    old_value=old,
                    new_value=new,
                    test_id=test_id,
                    confidence=confidence,
                    evidence=site.evidence,
                    change_key=change_key(site.site_id, kind, old, new, test_id),
                )
            )
    return out


def plan_digest(rows: list[Change]) -> str:
    return hashlib.sha256("".join(row.to_json_line() + "\n" for row in rows).encode()).hexdigest()


def _text(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _evidence_json(row: Change) -> str:
    entries = [
        {"source": "qid-repair research 2026-09-22", "quote": line, "url": None}
        for line in row.evidence
    ]
    return _text(json.dumps(entries, ensure_ascii=False)) + "::jsonb"


def render(rows: list[Change], *, reversal: bool, rehearsal: bool = False) -> str:
    """One transaction over every row: guards, one conditional update and one journal row each,
    invariants, then `COMMIT` - or `ROLLBACK` for the rehearsal."""
    if not rows:
        raise SystemExit("refusing to render a statement with no rows")
    stamp = ROLLBACK_STAMP if reversal else RUN_STAMP
    what = "reversal" if reversal else "repair"
    values = []
    for row in rows:
        old, new = (row.new_value, row.old_value) if reversal else (row.old_value, row.new_value)
        key = row.change_key + ("-rollback" if reversal else "")
        values.append(
            f"    ({_text(row.site_id)}::uuid, {_text(row.kind)}, {_text(old)}, {_text(new)}, "
            f"{_text(key)}, {_text(row.test_id)}, {_text(row.confidence)}, {_evidence_json(row)})"
        )
    lines = [
        "-- Generated by output/remediation/tools/qid_repair.py - do not edit by hand.",
        f"{DIGEST_HEADER}{plan_digest(rows)}",
        f"-- the {what} of {len(rows)} site_external_ids row(s); run stamp '{stamp}'.",
        "-- Every row is addressed by its full key (site_id, kind, value = the old value) and must",
        "-- match exactly one row; its journal row is written in the same transaction.",
        "\\set ON_ERROR_STOP on",
        "BEGIN;",
        "",
        "CREATE TEMP TABLE _ext_plan (",
        "    site_id    UUID NOT NULL,",
        "    kind       TEXT NOT NULL,",
        "    old_value  TEXT NOT NULL,",
        "    new_value  TEXT NOT NULL,",
        "    change_key TEXT NOT NULL,",
        "    test_id    TEXT NOT NULL,",
        "    confidence TEXT NOT NULL,",
        "    evidence   JSONB NOT NULL,",
        "    PRIMARY KEY (site_id, kind)",
        ") ON COMMIT DROP;",
        "",
        "INSERT INTO _ext_plan (site_id, kind, old_value, new_value, change_key, test_id,",
        "                       confidence, evidence) VALUES",
        ",\n".join(values) + ";",
        "",
        "DO $$",
        "DECLARE",
        "    bad      INTEGER;",
        "    n        INTEGER;",
        "    moved    INTEGER := 0;",
        f"    expected INTEGER := {len(rows)};",
        "    r        RECORD;",
        "BEGIN",
        "    -- guard 1: every site is a curated site that still exists",
        "    SELECT count(*) INTO bad FROM _ext_plan p LEFT JOIN unified_sites u ON u.id = p.site_id",
        "     WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';",
        "    IF bad > 0 THEN RAISE EXCEPTION 'external-id repair: % row(s) are not curated sites', bad;",
        "    END IF;",
        "    -- guard 2: each site has exactly one row of the kind, and it holds the planned old value",
        "    SELECT count(*) INTO bad FROM _ext_plan p",
        "     WHERE (SELECT count(*) FROM site_external_ids e",
        "             WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1",
        "        OR NOT EXISTS (SELECT 1 FROM site_external_ids e WHERE e.site_id = p.site_id",
        "                          AND e.kind = p.kind AND e.value = p.old_value);",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'external-id repair: % row(s) no longer hold the planned old value', bad;",
        "    END IF;",
        "    -- the writes: one conditional update and one journal row each, exactly one row matched",
        "    FOR r IN SELECT * FROM _ext_plan ORDER BY site_id, kind LOOP",
        f"        UPDATE {TABLE} SET value = r.new_value",
        "         WHERE site_id = r.site_id AND kind = r.kind AND value = r.old_value;",
        "        GET DIAGNOSTICS n = ROW_COUNT;",
        "        IF n <> 1 THEN",
        "            RAISE EXCEPTION 'external-id repair: %/% matched % row(s), not 1',",
        "                r.site_id, r.kind, n;",
        "        END IF;",
        "        INSERT INTO remediation_change_log (run_stamp, test_id, table_name, column_name,",
        "            row_pk, old_value, new_value, change_key, confidence, evidence, site_id_ref)",
        f"        VALUES ({_text(stamp)}, r.test_id, {_text(TABLE)}, 'value',",
        "            r.site_id::text || '/' || r.kind, r.old_value, r.new_value, r.change_key,",
        "            r.confidence, r.evidence, r.site_id);",
        "        moved := moved + n;",
        "    END LOOP;",
        "    IF moved <> expected THEN",
        "        RAISE EXCEPTION 'external-id repair: % row(s) changed, % planned', moved, expected;",
        "    END IF;",
        "    -- invariant 1: every row now holds the new value, read back by its full key",
        "    SELECT count(*) INTO bad FROM _ext_plan p",
        "     WHERE (SELECT count(*) FROM site_external_ids e WHERE e.site_id = p.site_id",
        "             AND e.kind = p.kind AND e.value = p.new_value) <> 1",
        "        OR (SELECT count(*) FROM site_external_ids e",
        "             WHERE e.site_id = p.site_id AND e.kind = p.kind) <> 1;",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'external-id repair: % row(s) do not hold the new value', bad;",
        "    END IF;",
        "    -- invariant 2: the journal and the plan agree in both directions",
        "    SELECT count(*) INTO bad FROM _ext_plan p LEFT JOIN remediation_change_log l",
        f"        ON l.run_stamp = {_text(stamp)} AND l.change_key = p.change_key",
        f"       AND l.table_name = {_text(TABLE)} AND l.row_pk = p.site_id::text || '/' || p.kind",
        "       AND l.old_value = p.old_value AND l.new_value = p.new_value",
        "     WHERE l.id IS NULL;",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'external-id repair: % row(s) have no matching journal row', bad;",
        "    END IF;",
        "    SELECT count(*) INTO bad FROM remediation_change_log l",
        f"     WHERE l.run_stamp = {_text(stamp)}",
        "       AND NOT EXISTS (SELECT 1 FROM _ext_plan p WHERE p.change_key = l.change_key);",
        "    IF bad > 0 THEN",
        "        RAISE EXCEPTION 'external-id repair: this stamp journalled % row(s) outside the plan',",
        "            bad;",
        "    END IF;",
        "    RAISE NOTICE 'external-id repair: % row(s) changed and journalled', moved;",
        "END $$;",
        "",
        "ROLLBACK;" if rehearsal else "COMMIT;",
        "",
        "SELECT 'journal rows for this stamp' AS metric, count(*)::text AS value",
        f"  FROM remediation_change_log WHERE run_stamp = {_text(stamp)};",
        "",
    ]
    return "\n".join(lines)


def pinned(sql: str) -> str:
    for line in sql.splitlines():
        if line.startswith(DIGEST_HEADER):
            return line[len(DIGEST_HEADER) :].strip()
    raise SystemExit(f"the statement carries no {DIGEST_HEADER!r} line")


def plan_markdown(rows: list[Change]) -> str:
    settled = [site for site in SITES if site.rule != "unresolved"]
    lines = [
        "# The repair of mis-resolved `site_external_ids` rows (2026-09-22) - planned, not applied",
        "",
        f"{len(rows)} row changes at {len(settled)} sites (run stamp `{RUN_STAMP}`); "
        f"{len(SITES) - len(settled)} site unresolved. Rendered by "
        "`output/remediation/tools/qid_repair.py` - the module docstring states the two rules, why "
        "the statements do not use `apply_remediation_change`, and the fixed point.",
        "",
        "| site | rule | wikidata_qid | enwiki_title | evidence |",
        "| --- | --- | --- | --- | --- |",
    ]
    for site in SITES:
        qid = (
            f"`{site.old_qid}` -> `{site.new_qid}`"
            if site.new_qid
            else f"`{site.old_qid}` (unchanged)"
        )
        title = (
            f"`{site.old_title}` -> `{site.new_title}`"
            if site.new_title
            else f"`{site.old_title}` (unchanged)"
        )
        lines.append(
            f"| {site.name} (`{site.site_id}`) | {site.rule} | {qid} | {title} | "
            + "<br>".join(site.evidence)
            + " |"
        )
    generic = [
        site
        for site in SITES
        if site.new_title is None and site.old_title in ("History", "Archaeology", "Theatre")
    ]
    lines += [
        "",
        "## Left as they are, and why",
        "",
        f"* **Generic `enwiki_title` with no replacement ({len(generic)})**: "
        + ", ".join(f"{site.name} (`{site.old_title}`)" for site in generic)
        + ". The repaired item has no English article, so the only fix is to delete the row - a "
        "deletion is the owner's call, and the prospector's dedup reads the title as a hard id "
        "(a candidate called 'Theatre' would match three curated sites) until then.",
        "* **Tikal**: unresolved - the record is named Tikal and describes Mundo Perdido (HUMAN_ONLY "
        "B1).",
        "* **`unified_sites.source_url`** of the settled sites still names the generic article "
        "(`" + "`, `".join(sorted(GENERIC_SOURCE_URL.values())) + "`). It is the root cause: "
        "`external_ids.py` resolves ids from it, so `refresh_site_external_ids(only_missing=False)` "
        "would add the generic id back beside the repaired one. The boot path "
        "(`only_missing=True`) does not. Correcting `source_url` is a separate change to a column "
        "many producers read (ingesters, the content linker, the image resolvers) and needs its "
        "own fixed-point analysis.",
        "* The already-judged sites whose phase-3 Wikidata evidence was the wrong item should be "
        "re-judged after the repair: City of Enns, Crantit Chambered Cairn, Castellum Onagrinum, the "
        "three theatres and four of the Gyeongju belts (Mount Namsan, Hwangnyongsa, Sanseong, Tumuli "
        "Park); the gap run (output/remediation/gap/GAP_PLAN.md) re-asks the other ten.",
        "",
        "## How to run it (the orchestrator's job, in this order)",
        "",
        "```bash",
        "./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py check     # read-only",
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/REHEARSAL.sql',
        'ssh ancientnerds "docker exec -i ancient_nerds_db psql -U ancient_map -d ancient_map '
        '-v ON_ERROR_STOP=1" < output/remediation/qid_repair/APPLY.sql',
        "./.venv/Scripts/python.exe output/remediation/tools/qid_repair.py verify    # read-only",
        "```",
        "",
    ]
    return "\n".join(lines)


def write_files(out: pathlib.Path = OUT) -> list[Change]:
    rows = changes()
    out.mkdir(parents=True, exist_ok=True)
    (out / "PLAN.jsonl").write_text(
        "".join(row.to_json_line() + "\n" for row in rows), encoding="utf-8", newline="\n"
    )
    (out / "APPLY.sql").write_text(render(rows, reversal=False), encoding="utf-8", newline="\n")
    (out / "REHEARSAL.sql").write_text(
        render(rows, reversal=False, rehearsal=True), encoding="utf-8", newline="\n"
    )
    (out / "ROLLBACK.sql").write_text(render(rows, reversal=True), encoding="utf-8", newline="\n")
    (out / "PLAN.md").write_text(plan_markdown(rows), encoding="utf-8", newline="\n")
    return rows


def read_rows(rows: list[Change], *, run=lanes.psql) -> dict[tuple[str, str], list[str]]:
    """`{(site_id, kind): [values]}` for the planned rows, read-only."""
    ids = sorted({row.site_id for row in rows})
    found: dict[tuple[str, str], list[str]] = {}
    sql = (
        "SELECT to_jsonb(t)::text FROM (SELECT site_id::text AS site_id, kind, value "
        f"FROM {TABLE} WHERE site_id::text IN ({lanes.sql_literals(ids)}) "
        f"AND kind IN ({lanes.sql_literals(KINDS)})) t;"
    )
    for record in lanes.json_rows(run(sql)):
        found.setdefault((record["site_id"], record["kind"]), []).append(record["value"])
    return found


def compare(rows: list[Change], found: dict[tuple[str, str], list[str]], *, want: str) -> list[str]:
    """What differs from the plan's `old` (pre-flight) or `new` (after the apply) values."""
    problems = []
    for row in rows:
        expected = row.old_value if want == "old" else row.new_value
        values = found.get((row.site_id, row.kind), [])
        if values != [expected]:
            problems.append(f"{row.name} {row.kind}: expected [{expected!r}], found {values!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qid-repair")
    parser.add_argument("command", choices=("render", "check", "verify"))
    args = parser.parse_args(argv)
    if args.command == "render":
        rows = write_files()
        print(f"{len(rows)} changes rendered into {OUT} (digest {plan_digest(rows)[:16]})")
        return 0
    rows = [
        Change(**{**r, "evidence": tuple(r["evidence"])})
        for r in lanes.read_jsonl(OUT / "PLAN.jsonl")
    ]
    if rows != changes():
        raise SystemExit("PLAN.jsonl is not the plan this script renders; run `render` again")
    for name in ("APPLY.sql", "ROLLBACK.sql"):
        if pinned((OUT / name).read_text(encoding="utf-8")) != plan_digest(rows):
            raise SystemExit(f"{name} is pinned to another plan; run `render` again")
    problems = compare(rows, read_rows(rows), want="old" if args.command == "check" else "new")
    for problem in problems:
        print(f"  ABWEICHUNG {problem}")
    if args.command == "verify" and not problems:
        journal = lanes.json_rows(
            lanes.psql(
                "SELECT to_jsonb(t)::text FROM (SELECT change_key FROM remediation_change_log "
                f"WHERE run_stamp = {_text(RUN_STAMP)}) t;"
            )
        )
        keys = {record["change_key"] for record in journal}
        if keys != {row.change_key for row in rows}:
            problems.append(f"journal holds {len(keys)} rows for {RUN_STAMP}, the plan {len(rows)}")
            print(f"  ABWEICHUNG {problems[-1]}")
    print(f"{args.command}: {len(rows)} rows, {len(problems)} Abweichungen")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
