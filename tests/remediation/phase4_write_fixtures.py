"""Shared fixtures for the Phase-4/5 writer tests: one pinned source, one plan batch on disk, and a
fake psql that parses what it is given.

Not a test module (no `test_` prefix): `test_phase4_write.py`, `test_phase4_legacy.py` and
`test_phase4_card_json.py` import it. Nothing here opens a socket, calls a model or touches a
database.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import write_stage as W  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import write4 as W4  # noqa: E402

SITE_A = "4a5a324f-0000-4000-8000-000000000001"
SITE_B = "318414bc-0000-4000-8000-000000000002"
SITE_C = "72980dbd-0000-4000-8000-000000000003"
BATCH = "p4-0003"
REVID = 1234567
TITLE = "Tarxien Temples"
PERMALINK = f"https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid={REVID}"
#: The pinned text: three sentences, the offsets below index into it.
TEXT = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta.\n"
    "They date to approximately 3150 BC, and they were excavated in 1915.\n"
    "The site is part of a World Heritage Site."
)
S1 = (0, TEXT.index("\n"))
S2 = (TEXT.index("They"), TEXT.index("\nThe site"))
DESCRIPTION = (
    "The Tarxien Temples are an archaeological complex in Tarxien, Malta [1]. "
    "They date to approximately 3150 BC, and they were excavated in 1915 [1]."
)
CARD = "The Tarxien Temples date to approximately 3150 BC and were excavated in 1915."
OLD_DESCRIPTION = "An LLM wrote this in March about the Tarxien Temples."
OLD_CARD = "A card the March chain wrote."
OLD_RAW = {"description_citations": [{"n": 1, "url": "https://grokipedia.com/page/Tarxien"}]}


def plan_site(
    site_id: str = SITE_A,
    *,
    description: str | None = OLD_DESCRIPTION,
    card: str | None = OLD_CARD,
    raw_data: dict[str, Any] | None = None,
    snapshot: str | None = "The pre-March text.",
    in_snapshot: bool = True,
    flags: Iterable[M.SiteFlag] = (),
) -> M.PlanSite:
    raw = copy.deepcopy(OLD_RAW) if raw_data is None else raw_data
    return M.PlanSite(
        site_id=site_id,
        name=TITLE,
        aliases=("Templos de Tarxien",),
        country="Malta",
        site_type="Temple",
        period_start=-3150,
        period_end=None,
        lat=35.8692,
        lon=14.5122,
        description=description,
        description_sha256=None if description is None else M.text_sha256(description),
        raw_data=raw,
        raw_data_sha256=M.text_sha256(json.dumps(raw)),
        card=card,
        card_sha256=None if card is None else M.text_sha256(card),
        source_url="https://en.wikipedia.org/wiki/Tarxien_Temples",
        wikidata_qid="Q1195938",
        enwiki_title=TITLE,
        in_snapshot=in_snapshot,
        snapshot_description=snapshot,
        flags=frozenset(flags),
    )


def assembly(
    site_id: str = SITE_A,
    *,
    lane: M.Lane = M.Lane.W,
    description: str = DESCRIPTION,
    card: str | None = CARD,
) -> M.Assembly:
    """A well-formed lane-W (or S) assembly over `TEXT`; what verify4 would say is the fake's."""
    card_record = (
        None
        if card is None
        else M.Card(items=(M.CardItem(sentence=1, drop=()),), text_sha256=M.text_sha256(card))
    )
    provenance = M.Provenance(
        run="pilot-20260923",
        lane=lane,
        ai=M.LANE_AI[lane],
        ai_system=M.AI_SYSTEM,
        licence=M.PUBLISHED_LICENCE,
        attribution=M.Attribution(
            title=TITLE,
            url=PERMALINK,
            licence_url=M.PUBLISHED_LICENCE_URL,
            changes=M.LANE_CHANGES[lane],
        ),
        sources=(
            M.SourceRef(
                id="W",
                url=PERMALINK,
                revid=REVID,
                rev_timestamp="2026-09-01T10:00:00Z",
                text_sha256=M.text_sha256(TEXT),
                licence=M.Licence.CC_BY_SA_4,
            ),
        ),
        sentences=(
            M.PublishedSentence(n=1, src="W", start=S1[0], end=S1[1], drop=()),
            M.PublishedSentence(n=1, src="W", start=S2[0], end=S2[1], drop=()),
        ),
        card=card_record,
        desc_sha256=M.text_sha256(description),
    )
    return M.Assembly(
        site_id=site_id,
        description=description,
        citations=(
            M.Citation(
                n=1,
                url=PERMALINK,
                title=f"Wikipedia: {TITLE}",
                domain="en.wikipedia.org",
                license=M.Licence.CC_BY_SA_4,
            ),
        ),
        card=card,
        provenance=provenance,
    )


def source_doc(site_verdict: M.SubjectVerdict = M.SubjectVerdict.OWN) -> M.SourceDoc:
    return M.SourceDoc(
        id="W",
        url="https://en.wikipedia.org/w/api.php?action=query&titles=Tarxien%20Temples",
        permalink=PERMALINK,
        title=TITLE,
        pageid=1843961,
        revid=REVID,
        lastrevid=REVID,
        rev_timestamp="2026-09-01T10:00:00Z",
        retrieved_at="2026-09-23T08:00:00Z",
        sha256_raw=M.text_sha256("raw"),
        sha256_text=M.text_sha256(TEXT),
        licence=M.Licence.CC_BY_SA_4,
        route=M.Route.ENWIKI_TITLE,
        subject_gate=M.SubjectGate(
            qid_match=True,
            shared=False,
            concept=False,
            place_item=False,
            km=0.1,
            name_score=100.0,
            verdict=site_verdict,
        ),
        tdm=None,
        final_url=None,
        truncated=None,
    )


#: A lane-W site's two calls: the ledger stage and the call's feature (`model4`'s names, which
#: Track B's stages store their answers, prompts and ledger labels under).
CALLS = (("selector", M.SELECT_FEATURE), ("reviewer", M.REVIEW_FEATURE))


def ledger_rows(*site_ids: str, batch: str = BATCH) -> list[dict[str, Any]]:
    rows = []
    for site_id in site_ids:
        for stage, feature in CALLS:
            rows.append(
                {
                    "kind": "model_call",
                    "batch_id": batch,
                    "label": f"{site_id}/{feature}",
                    "stage": stage,
                }
            )
    return rows


def write_batch(
    root: Path,
    *,
    sites: Sequence[M.PlanSite],
    assemblies: Sequence[M.Assembly] = (),
    holds: Sequence[M.Hold] = (),
    lanes: Mapping[str, M.Lane] | None = None,
    batch_id: str = BATCH,
    model_folders: Iterable[str] = W4.MODEL_FOLDERS,
) -> Path:
    """A plan batch on disk, in exactly the contract's files."""
    batch_dir = root / batch_id
    batch_dir.mkdir(parents=True)
    (batch_dir / M.INPUT_FILE).write_text(
        json.dumps(
            {"batch_id": batch_id, "ordinal": 3, "sites": [site.to_dict() for site in sites]}
        ),
        encoding="utf-8",
    )
    lane_of = dict(lanes or {})
    lane_sources = {
        M.Lane.W: ("W",),
        M.Lane.S: ("W",),
        M.Lane.T: ("T.fr",),
        M.Lane.R: ("R1",),
        M.Lane.ZERO: (),
    }
    assignments = [
        M.LaneAssignment(
            site_id=site.site_id,
            lane=lane_of.get(site.site_id, M.Lane.W),
            sources=lane_sources[lane_of.get(site.site_id, M.Lane.W)],
            detail="the facts the lane was assigned from",
        )
        for site in sites
    ]
    (batch_dir / M.LANES_FILE).write_text(M.dump_jsonl(assignments), encoding="utf-8")
    (batch_dir / M.ASSEMBLY_FILE).write_text(M.dump_jsonl(list(assemblies)), encoding="utf-8")
    (batch_dir / M.HOLDS_FILE).write_text(M.dump_jsonl(list(holds)), encoding="utf-8")
    store = F.EvidenceStore(batch_dir / M.EVIDENCE_DIR)
    folders = list(model_folders)
    for site in sites:
        store.write(
            site_id=site.site_id,
            feature=M.source_feature("W", "meta"),
            body=source_doc().to_json().encode("utf-8"),
        )
        store.write(
            site_id=site.site_id, feature=M.source_feature("W", "txt"), body=TEXT.encode("utf-8")
        )
        # One call per stage: its answer (`answers/` or `reviews/`), its prompt (`prompts/`, the
        # same feature) and its ledger line (`ledger_rows`: `<site>/select`, `<site>/review`).
        for folder in folders:
            files = {
                "answers": {M.SELECT_FEATURE: "DESC: W1\n"},
                "reviews": {M.REVIEW_FEATURE: "R1: KEEP\nR2: KEEP\nCARD: KEEP\n"},
                "prompts": {
                    M.SELECT_FEATURE: "the selector prompt\n",
                    M.REVIEW_FEATURE: "the reviewer prompt\n",
                },
            }[folder]
            for feature, body in files.items():
                F.EvidenceStore(batch_dir / folder).write(
                    site_id=site.site_id, feature=feature, body=body.encode("utf-8")
                )
    return batch_dir


class Verify:
    """A scripted verifier with verify4.verify_site's signature. It records what it was shown and
    answers the holds it was given per site (none = V1-V15 pass)."""

    def __init__(self, holds: Mapping[str, Sequence[M.Hold]] | None = None) -> None:
        self.holds = dict(holds or {})
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        site: M.PlanSite,
        assembly: M.Assembly,
        *,
        metas: Mapping[str, Mapping[str, Any]],
        texts: Mapping[str, str],
        quotes: Sequence[str],
        new_raw_data: Mapping[str, Any],
    ) -> tuple[M.Hold, ...]:
        self.calls.append(
            {
                "site": site,
                "assembly": assembly,
                "metas": metas,
                "texts": texts,
                "quotes": list(quotes),
                "new_raw_data": new_raw_data,
            }
        )
        return tuple(self.holds.get(site.site_id, ()))


# ------------------------------------------------------------------------------------ fake psql
_ROW = re.compile(
    r"^    \('(?P<site>[^']+)'::uuid, '(?P<table>[^']*)', '(?P<column>[^']*)', "
    r"'(?P<pk_column>[^']*)', '(?P<pk>[^']*)', (?P<old>NULL|'(?:[^']|'')*'), "
    r"(?P<new>NULL|'(?:[^']|'')*'), '(?P<key>[^']*)', '(?P<test_id>[^']*)', "
    r"'(?P<evidence>(?:[^']|'')*)'::jsonb\)[,;]$",
    re.MULTILINE,
)
_TUPLE = re.compile(r"\('([^']*)', '([^']*)', '([^']*)', '([^']*)'\)")


def _literal(text: str) -> str | None:
    return None if text == "NULL" else text[1:-1].replace("''", "'")


class PsqlError(W.WriteRefused):
    """What `write_stage.run_sql` raises for a statement psql refused (a non-zero exit)."""


@dataclasses.dataclass
class Site:
    source_id: str = W.CURATED_SOURCE
    description: str | None = OLD_DESCRIPTION
    raw_data: dict[str, Any] | None = None
    card_row: bool = True
    card: str | None = OLD_CARD


class FakeDb:
    """A fake psql over `unified_sites.description/raw_data`, `card_stats.card_description` and the
    journal. It parses what it is given - the plan rows of the INSERT, the run stamp of the loop, the
    allow-list's VALUES, the guards the statement carries and whether it ends in COMMIT or ROLLBACK
    - and refuses what the real transaction refuses: a guard that finds a bad row, a row that no
    longer holds its old value, a no-op, and a statement it does not know. A refused statement
    changes nothing, like a transaction psql aborted."""

    def __init__(self, sites: Mapping[str, Site], *, journal_order: str = "oldest-first") -> None:
        self.sites = {site_id: copy.deepcopy(site) for site_id, site in sites.items()}
        self.journal: list[dict[str, Any]] = []
        self.sent: list[str] = []
        #: The order the journal read returns its rows in. The real statement orders by the JSON
        #: text, which says nothing about write rounds, so a reader must not depend on the order.
        if journal_order not in ("oldest-first", "newest-first"):
            raise ValueError(journal_order)
        self.journal_order = journal_order
        #: Sabotage, for the checks around a chunk: a writer that moves a row right after a commit
        #: (`after_commit`), and a statement ending in ROLLBACK whose journal rows survive while its
        #: values are rolled back (`leak_rolled_back_journal`) - what those checks must catch.
        self.after_commit: Callable[[FakeDb], None] | None = None
        self.leak_rolled_back_journal = False

    # -- helpers
    def value(self, site_id: str, column: str) -> Any:
        site = self.sites[site_id]
        return {
            "description": site.description,
            "raw_data": site.raw_data,
            "card_description": site.card,
        }[column]

    def _holds(self, site_id: str, column: str, planned: str | None) -> bool:
        stored = self.value(site_id, column)
        if column == "raw_data":
            return stored == (None if planned is None else json.loads(planned))
        return stored == planned

    def _set(self, site_id: str, column: str, value: str | None) -> None:
        site = self.sites[site_id]
        if column == "description":
            site.description = value
        elif column == "raw_data":
            site.raw_data = None if value is None else json.loads(value)
        else:
            site.card = value

    # -- the seam
    def __call__(self, sql: str, *, host: str) -> str:
        self.sent.append(sql)
        if sql.startswith(W4.STORED_READ):
            ids = re.findall(r"'([0-9a-f-]{36})'::uuid", sql)
            out = []
            for site_id in sorted(ids):
                if site_id not in self.sites:
                    continue
                site = self.sites[site_id]
                out.append(
                    json.dumps(
                        {
                            "id": site_id,
                            "source_id": site.source_id,
                            "description": site.description,
                            "raw_data": site.raw_data,
                            "card_row": site.card_row,
                            "card_description": site.card if site.card_row else None,
                        }
                    )
                )
            return "\n".join(out) + "\n"
        if sql.startswith("-- how many journal rows"):
            stamp = _literal(re.search(r"WHERE run_stamp = ('(?:[^']|'')*')", sql)[1])
            return f"{sum(1 for entry in self.journal if entry['run_stamp'] == stamp)}\n"
        if sql.startswith("-- the journal rows of this chunk's changes"):
            listed = sql.split("IN (", 1)[1].split(")", 1)[0]
            keys = {_literal(k) for k in re.findall(r"'(?:[^']|'')*'", listed)}
            stamp = re.search(r"l\.run_stamp = ('(?:[^']|'')*')", sql)
            entries = [
                entry
                for entry in self.journal
                if entry["change_key"] in keys
                and (stamp is None or entry["run_stamp"] == _literal(stamp[1]))
            ]
            if self.journal_order == "newest-first":
                entries.reverse()
            return "".join(
                json.dumps({k: entry[k] for k in entry if k != "id"}) + "\n" for entry in entries
            )
        if "INSERT INTO _phase4_plan" in sql:
            return self._transaction(sql)
        raise AssertionError(f"the fake psql does not know this statement: {sql[:80]!r}")

    def _transaction(self, sql: str) -> str:
        rows = [
            {
                "site": m["site"],
                "table": m["table"],
                "column": m["column"],
                "pk_column": m["pk_column"],
                "pk": m["pk"],
                "old": _literal(m["old"]),
                "new": _literal(m["new"]),
                "key": m["key"],
                "test_id": m["test_id"],
            }
            for m in _ROW.finditer(sql)
        ]
        if not rows:
            raise AssertionError("a transaction with no plan rows the fake can read")
        expected = int(re.search(r"expected\s+INTEGER := (\d+);", sql)[1])
        stamp = _literal(re.search(r"r\.test_id, ('(?:[^']|'')*'), r\.change_key", sql)[1])
        commit = "\nCOMMIT;\n" in sql
        if not commit and "\nROLLBACK;\n" not in sql:
            raise AssertionError("a transaction that ends in neither COMMIT nor ROLLBACK")
        saved = (copy.deepcopy(self.sites), copy.deepcopy(self.journal))
        try:
            self._guards(sql, rows)
            for row in sorted(rows, key=lambda r: (r["site"], r["table"], r["column"])):
                if row["old"] == row["new"]:
                    raise PsqlError("apply_remediation_change: the same old and new value")
                if not self._holds(row["site"], row["column"], row["old"]):
                    raise PsqlError("apply_remediation_change: expected 1 row, matched 0")
                self._set(row["site"], row["column"], row["new"])
                self.journal.append(
                    {
                        "id": len(self.journal) + 1,
                        "run_stamp": stamp,
                        "change_key": row["key"],
                        "table_name": row["table"],
                        "column_name": row["column"],
                        "row_pk": row["pk"],
                        "old_value": row["old"],
                        "new_value": row["new"],
                        "test_id": row["test_id"],
                        "site_id_ref": row["site"],
                    }
                )
            if len(rows) != expected:
                raise PsqlError(f"{len(rows)} row(s) changed, {expected} planned")
            for row in rows:
                if not self._holds(row["site"], row["column"], row["new"]):
                    raise PsqlError("a planned row does not hold the new value")
            self._invariants(sql, rows)
        except PsqlError:
            self.sites, self.journal = saved
            raise
        if not commit:
            self.sites = saved[0]
            if not self.leak_rolled_back_journal:
                self.journal = saved[1]
        elif self.after_commit is not None:
            self.after_commit(self)
        return "NOTICE\n"

    def _guards(self, sql: str, rows: list[dict[str, Any]]) -> None:
        if "-- guard 1:" in sql:
            for row in rows:
                site = self.sites.get(row["site"])
                if site is None or site.source_id != W.CURATED_SOURCE:
                    raise PsqlError("guard 1: not a curated site")
                if row["table"] == "card_stats" and not site.card_row:
                    raise PsqlError("guard 1: no card_stats row")
        if "-- guard 2:" in sql:
            values = sql.split("NOT IN (VALUES ", 1)[1].split(")\n", 1)[0] + ")"
            allowed = set(_TUPLE.findall(values))
            for row in rows:
                if (row["table"], row["column"], row["pk_column"], row["test_id"]) not in allowed:
                    raise PsqlError("guard 2: outside the allow-list")
                if row["pk"] != row["site"]:
                    raise PsqlError("guard 2: the key is not the site")
        if "-- guard 3:" in sql:
            for row in rows:
                if row["new"] == row["old"] or row["new"] == "":
                    raise PsqlError("guard 3: not a change")
                if row["new"] is None and row["test_id"] != W4.TEST_CARD_CLEAR:
                    raise PsqlError("guard 3: NULL outside a card clear")
                if row["column"] == "raw_data" and row["old"] is not None:
                    if json.loads(row["new"]) == json.loads(row["old"]):
                        raise PsqlError("guard 3: the same jsonb")
        for row in rows:
            if not self._holds(row["site"], row["column"], row["old"]):
                raise PsqlError("guard 4: a row no longer holds its old value")

    def _invariants(self, sql: str, rows: list[dict[str, Any]]) -> None:
        if "-- invariant 3" in sql:
            for row in rows:
                if row["column"] != "raw_data":
                    continue
                site = self.sites[row["site"]]
                provenance = (site.raw_data or {}).get(M.PROVENANCE_KEY) or {}
                if site.description is None or provenance.get("desc_sha256") != M.text_sha256(
                    site.description
                ):
                    raise PsqlError("invariant 3: desc_sha256")
        if "-- invariant 4" in sql:
            for row in rows:
                if row["column"] != "card_description" or row["new"] is None:
                    continue
                site = self.sites[row["site"]]
                provenance = (site.raw_data or {}).get(M.PROVENANCE_KEY) or {}
                card = provenance.get("card") or {}
                if site.card is None or card.get("text_sha256") != M.text_sha256(site.card):
                    raise PsqlError("invariant 4: card sha256")
