"""D13: the write chain of a confirmed re-target, wave by wave (at most 100 sites).

A site is re-targeted when the web verifier said `RETARGET`, every machine gate held and the
adversarial re-check said `CONFIRM` (`retarget.final_state`). Its chain, in order, with one site
finishing a stage before the next dependent lane starts (`CHAIN`):

1. **links** - `site_external_ids` (the Wikidata item and the English Wikipedia title) and
   `unified_sites.source_url` in the **same step**: the daily `refresh_site_external_ids` derives the
   ids from `source_url`, so a link change without it is undone. The step is L5's: rows by their full
   key through `qid_repair.render_split(removals=True)`, steps run by `l5.links` with this lane's
   `step_wave`; the journal identity is `<wave>_d13-links-001`.
2. **name** - `retarget-name-<wave>` (`mechanical/identity_lanes.py`): the name and its key, the
   key computed by Postgres. It is planned **after the link step landed** (`plan-names` refuses a
   site whose links have not): its premise is the external ids as the database prints them, so the
   order is a guard, not a convention.
3. **alias** - `name-alias-<wave>`: the old name's `label` row becomes an `alias` row (the old name
   stays searchable, D13).
4. the **hand-offs** to the lanes that own the rest, each a list of sites that finished the stage
   before: `point_type` (the sourced coordinates and the item's classes: lane wd5, with the relaxed
   coast guard of D19), `description` (lane W reads the new `enwiki_title`; the pinned scope
   `SCOPE4.v3.json` must admit the site again or the site goes to WN), `gallery` (the town's
   pictures are excluded and the new item's Commons category is searched: the image lanes),
   `period` (re-research, D12, only after the referent is settled), `card` (the description's hash
   changed, so every earlier card is stale).

`chain-done` records that a stage landed (with its run stamp); `chain-ready` lists the sites a stage
may start on. The links, name and alias stages are also read back from production (`landed`).

Nothing here writes to production.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[3]
for _root in (str(REPO), str(_HERE.parents[1]), str(REPO / "output" / "remediation" / "tools")):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import qid_repair as QR  # noqa: E402
from l5 import links as L5K  # noqa: E402
from l5 import plan as L5P  # noqa: E402
from l5.decide import DECIDED  # noqa: E402
from mechanical import plan as MP  # noqa: E402
from mechanical.identity_lanes import name_lane  # noqa: E402
from mechanical.lane import NAME_FIX_PREMISE_SQL, sql_literal  # noqa: E402

from identity import common, name_write, retarget, waves  # noqa: E402
from identity.rounds import now_utc  # noqa: E402

RESEARCH = "D13 re-target 2026-10-08 (web verifier Sonnet, adversarial re-check Opus, quotes machine-checked)"
CONFIDENCE = "authoritative"
LINK_STEP = 1
LINK_KINDS = ("wikidata_qid", "enwiki_title")
RULE_NAME = "d13-retarget-name"
FINDING_TEST_ID = "D13/retarget-name"
#: The skips that leave a site's stored links as the question found them.
SKIP_LINKS = (
    "gone",
    "not-curated",
    "retired",
    "changed-since-the-question",
    "links-not-one-each",
    "item-carried-by-another-site",
    "item-planned-for-another-site",
)

#: The chain, in order. A stage may start on a site only when every stage before it is done.
CHAIN = ("links", "name", "alias", "point_type", "description", "gallery", "period", "card")
HANDOFF_FILES = {
    "point_type": "HANDOFF_POINT_TYPE.jsonl",
    "description": "HANDOFF_DESCRIPTION.jsonl",
    "gallery": "HANDOFF_GALLERY.jsonl",
    "period": "HANDOFF_PERIOD.jsonl",
    "card": "HANDOFF_CARD.jsonl",
}
CHAIN_FILE = "CHAIN.jsonl"
DIR = "retarget"


ChainError = waves.WaveError


def lane_dir(run: Path) -> Path:
    return run / DIR


def wave_dir(run: Path, wave: str) -> Path:
    return waves.wave_dir(lane_dir(run), wave)


def step_wave(wave: str) -> Callable[[int], QR.Wave]:
    """The journal identity of a wave's link step: qid_repair's `Wave`, one per step number."""

    def make(number: int) -> QR.Wave:
        if not 1 <= number <= 999:
            raise MP.PlanError(f"step {number} is not a step number")
        return QR.Wave(
            5,
            (),
            f"{wave}_d13-links-{number:03d}",
            QR.OUT / "d13" / wave / f"step-{number:03d}",
            RESEARCH,
            None,
        )

    return make


def confirmed(
    web: Mapping[str, Mapping[str, Any]], recheck: Mapping[str, Mapping[str, Any]]
) -> dict[str, Mapping[str, Any]]:
    """The confirmed re-targets: the web decision of every site whose final state is `confirmed`
    with the verdict `RETARGET`, by site."""
    final = {r["site_id"]: r for r in retarget.final_state(web, recheck)}
    return {
        sid: web[sid]
        for sid, r in sorted(final.items())
        if r["state"] == retarget.FINAL_CONFIRMED and r["verdict"] == retarget.RETARGET
    }


def select_wave(
    run: Path, wave: str, decisions: Mapping[str, Mapping[str, Any]], *, limit: int, built_at: str
) -> dict[str, Any]:
    """The next wave: the first `limit` confirmed re-targets no earlier wave took."""
    return waves.select_wave(lane_dir(run), wave, list(decisions), limit=limit, built_at=built_at)


def load_wave(run: Path, wave: str) -> dict[str, Any]:
    return waves.load_wave(lane_dir(run), wave)


# ------------------------------------------------------------------------------------ the live read
def live_sites_sql(site_ids: Sequence[str], premise_sql: str = NAME_FIX_PREMISE_SQL) -> str:
    """The wave's rows as production holds them now, with the external ids as the lane prints them
    (its premise). Read-only."""
    ids = ", ".join(f"{sql_literal(s)}::uuid" for s in sorted(site_ids))
    return (
        "SELECT u.id::text AS site_id, u.source_id, u.name, u.name_normalized, u.country, "
        "u.lat::text AS lat, u.lon::text AS lon, u.source_url, u.scope_status, "
        "coalesce((SELECT json_agg(json_build_object('kind', e.kind, 'value', e.value) "
        "ORDER BY e.kind, e.value) FROM site_external_ids e WHERE e.site_id = u.id), '[]'::json) "
        f"AS ext, {premise_sql} AS premise FROM unified_sites u WHERE u.id IN ({ids}) "
        "ORDER BY u.id"
    )


def key_holders_sql(keys: Sequence[str]) -> str:
    """The visible curated rows whose match key already is one of `keys`."""
    listed = ", ".join(sql_literal(k) for k in sorted(set(keys)))
    return (
        "SELECT u.id::text AS site_id, u.name, u.name_normalized FROM unified_sites u WHERE "
        "u.source_id = 'ancient_nerds' AND u.scope_status IS DISTINCT FROM 'retired' AND "
        f"u.name_normalized IN ({listed}) ORDER BY u.id"
    )


@dataclass(frozen=True)
class Live:
    """What production holds now for a wave's sites, read-only."""

    sites: Mapping[str, Mapping[str, Any]]
    item_holders: Mapping[str, list[Mapping[str, Any]]]
    keys: Mapping[str, str]
    key_holders: Mapping[str, list[Mapping[str, Any]]]
    name_rows: Mapping[str, list[Mapping[str, Any]]]


Reader = Callable[[str], list[dict[str, Any]]]


def read_live(
    site_ids: Sequence[str],
    new_items: Sequence[str],
    new_names: Sequence[str],
    reader: Reader,
    *,
    names: bool,
) -> Live:
    """The live read of a phase: the links phase needs the sites and the holders of the new items;
    the names phase also the keys of the new names, who holds them, and the sites' name rows."""
    sites = {str(r["site_id"]): r for r in reader(live_sites_sql(site_ids))}
    item_holders: dict[str, list[Mapping[str, Any]]] = {}
    for row in reader(L5P.holders_sql(list(new_items))) if new_items else []:
        item_holders.setdefault(str(row["qid"]), []).append(row)
    keys: dict[str, str] = {}
    key_holders: dict[str, list[Mapping[str, Any]]] = {}
    name_rows: dict[str, list[Mapping[str, Any]]] = {}
    if names and new_names:
        keys = {str(r["name"]): str(r["key"]) for r in reader(L5P.keys_sql(list(new_names)))}
        for row in reader(key_holders_sql(list(keys.values()))):
            key_holders.setdefault(str(row["name_normalized"]), []).append(row)
        for row in reader(name_write.name_rows_sql(site_ids)):
            name_rows.setdefault(str(row["site_id"]), []).append(row)
    return Live(sites, item_holders, keys, key_holders, name_rows)


def stored_links(ext: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {k: [] for k in LINK_KINDS}
    for e in ext:
        if e["kind"] in out:
            out[e["kind"]].append(str(e["value"]))
    return out


# ------------------------------------------------------------------------------------ the links
@dataclass
class LinkPlan:
    links: list[QR.Change] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def _evidence(decision: Mapping[str, Any], key: str, recheck: Mapping[str, Any]) -> tuple[str, ...]:
    data = decision["data"]
    cell = data["target"][key]
    lines = [
        f"D13 reading ({decision['round']}, {decision['answered_by']}): {key} -> {cell['value']}"
        f" - {data['why']}"
    ]
    lines += [f'{q["url"]}: "{q["quote"]}"' for q in cell["quotes"]]
    if cell["note"]:
        lines.append(f"machine check: {cell['note']}")
    lines.append(
        f"adversarial re-check ({recheck['round']}, {recheck['answered_by']}): "
        f"{recheck['data']['verdict']} - {recheck['data']['why']}"
    )
    return tuple(lines)


def _change(
    decision: Mapping[str, Any],
    recheck: Mapping[str, Any],
    table: str,
    kind: str,
    cell: str,
    old: str | None,
    new: str,
) -> QR.Change:
    sid, test_id = str(decision["site_id"]), f"D13/{kind}"
    return QR.Change(
        site_id=sid,
        name=str(decision["data"]["target"]["name"]["value"]),
        kind=kind,
        old_value=old,
        new_value=new,
        test_id=test_id,
        confidence=CONFIDENCE,
        evidence=_evidence(decision, cell, recheck),
        change_key=QR.change_key(sid, kind, old, new, test_id, table=table),
        table=table,
    )


def build_links(
    decisions: Mapping[str, Mapping[str, Any]],
    rechecks: Mapping[str, Mapping[str, Any]],
    asked: Mapping[str, Mapping[str, Any]],
    live: Live,
) -> LinkPlan:
    """A pure function of the decisions, the question's contexts and the live read. A site whose
    state moved since it was asked, whose links are not one row of each kind, or whose new item
    another visible record carries (or another site of the wave is given) is skipped with its reason."""
    plan = LinkPlan()

    def skip(sid: str, reason: str, note: str) -> None:
        plan.skipped.append(
            {
                "site_id": sid,
                "name": decisions[sid]["data"]["target"]["name"]["value"],
                "reason": reason,
                "note": note,
            }
        )

    planned: dict[str, list[str]] = {}
    for sid, decision in decisions.items():
        planned.setdefault(decision["data"]["target"]["qid"]["value"], []).append(sid)
    for sid in sorted(decisions):
        decision = decisions[sid]
        if decision["status"] != DECIDED:
            raise MP.PlanError(f"{sid} is not decided - DECISIONS.jsonl is stale")
        now = live.sites.get(sid)
        if now is None:
            skip(sid, "gone", "the site is no longer in unified_sites")
            continue
        if now["source_id"] != "ancient_nerds":
            skip(sid, "not-curated", f"a {now['source_id']} row")
            continue
        if now["scope_status"] == "retired":
            skip(sid, "retired", "hidden everywhere: nothing of it is written")
            continue
        links = stored_links(now["ext"])
        ctx = asked[sid]
        moved = [
            f"{what}: {was!r} -> {is_!r}"
            for what, was, is_ in (
                ("wikidata_qid", sorted(ctx["qids"]), sorted(links["wikidata_qid"])),
                ("enwiki_title", sorted(ctx["enwiki"]), sorted(links["enwiki_title"])),
                ("source_url", ctx["source_url"], now["source_url"]),
                ("name", ctx["name"], now["name"]),
                ("scope_status", ctx["scope_status"], now["scope_status"]),
            )
            if was != is_
        ]
        if moved:
            skip(sid, "changed-since-the-question", "; ".join(moved))
            continue
        if any(len(v) > 1 for v in links.values()):
            skip(sid, "links-not-one-each", f"stored links {links}: one row of a kind at most")
            continue
        target = decision["data"]["target"]
        item = target["qid"]["value"]
        others = [h for h in live.item_holders.get(item, []) if str(h["site_id"]) != sid]
        if others:
            named = ", ".join(f"{h['name']} ({h['site_id']})" for h in others)
            skip(sid, "item-carried-by-another-site", f"{item} is {named}'s")
            continue
        twins = [t for t in planned[item] if t != sid]
        if twins:
            skip(
                sid,
                "item-planned-for-another-site",
                f"{item} is decided for {', '.join(sorted(twins))} too - one site or two is D14's",
            )
            continue
        second = rechecks[sid]
        for kind, cell in (("wikidata_qid", "qid"), ("enwiki_title", "enwiki_title")):
            old = links[kind][0] if links[kind] else None
            new = target[cell]["value"]
            if new != old:
                plan.links.append(_change(decision, second, QR.TABLE, kind, cell, old, new))
        url = target["source_url"]["value"]
        if url != now["source_url"]:
            plan.links.append(
                _change(
                    decision, second, QR.SITES_TABLE, QR.URL_COLUMN, "source_url",
                    now["source_url"], url,
                )
            )  # fmt: skip
    return plan


def write_links(run: Path, wave: str, plan: LinkPlan) -> Path | None:
    """The wave's one link step (at most 100 sites) and its skips; the step directory is never
    replaced (`l5.plan.write_step`)."""
    out = wave_dir(run, wave)
    out.mkdir(parents=True, exist_ok=True)
    (out / "LINKS_SKIPPED.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n" for s in plan.skipped),
        encoding="utf-8",
        newline="\n",
    )
    if not plan.links:
        return None
    step = step_wave(wave)(LINK_STEP)
    L5P.write_step(step, plan.links)
    return step.out


def link_commands(wave: str) -> dict[str, Callable[[int], int]]:
    """The link step's production commands (`l5/links.py`), bound to this wave's step identity."""
    make = step_wave(wave)
    return {
        name: (lambda number, _cmd=cmd: _cmd(number, step_wave=make))
        for name, cmd in L5K.COMMANDS.items()
    }


# ------------------------------------------------------------------------------------ the names
def build_names(
    decisions: Mapping[str, Mapping[str, Any]],
    rechecks: Mapping[str, Mapping[str, Any]],
    live: Live,
    wave: str,
) -> name_write.NamePlan:
    """The rename and alias of every site of the wave whose links landed. A site whose links have
    not landed is skipped (`links-not-landed`): the name's premise is the new external ids."""
    plan = name_write.NamePlan(name_lane("retarget-name", wave))
    for sid in sorted(decisions):
        target = decisions[sid]["data"]["target"]
        now = live.sites.get(sid)
        name = target["name"]["value"]
        if now is None:
            plan.skipped.append(
                {"site_id": sid, "name": name, "reason": "gone", "note": "not in unified_sites"}
            )
            continue
        links = stored_links(now["ext"])
        landed = (
            links["wikidata_qid"] == [target["qid"]["value"]]
            and links["enwiki_title"] == [target["enwiki_title"]["value"]]
            and now["source_url"] == target["source_url"]["value"]
        )
        if not landed:
            plan.skipped.append(
                {
                    "site_id": sid,
                    "name": now["name"],
                    "reason": "links-not-landed",
                    "note": f"production holds {links} and source_url {now['source_url']!r}: "
                    "the name waits for its link step",
                }
            )
            continue
        evidence = [
            {"source": q["url"], "url": q["url"], "quote": q["quote"]}
            for q in target["name"]["quotes"]
        ]
        decision, second = decisions[sid], rechecks[sid]
        name_write.plan_rename(
            plan,
            site_id=sid,
            live=now,
            new_name=name,
            new_key=live.keys[name],
            holders=live.key_holders.get(live.keys[name], []),
            name_rows=live.name_rows.get(sid, []),
            evidence=evidence,
            note=(
                f"D13 reading ({decision['round']}, {decision['answered_by']}): "
                f"{decision['data']['why']} Re-check ({second['round']}, "
                f"{second['answered_by']}): {second['data']['verdict']}."
            ),
            wave=wave,
            rule=RULE_NAME,
            finding_test_id=FINDING_TEST_ID,
        )
    return plan


# ------------------------------------------------------------------------------------ the hand-offs
def handoff_records(
    decisions: Mapping[str, Mapping[str, Any]],
    asked: Mapping[str, Mapping[str, Any]],
    sites: Sequence[str],
    wave: str,
) -> dict[str, list[dict[str, Any]]]:
    """The lists the downstream lanes read, for `sites`: one record per site per list."""
    out: dict[str, list[dict[str, Any]]] = {stage: [] for stage in HANDOFF_FILES}
    for sid in sorted(sites):
        data, ctx = decisions[sid]["data"], asked[sid]
        target = data["target"]
        base = {
            "site_id": sid,
            "wave": wave,
            "name": target["name"]["value"],
            "old_name": ctx["name"],
            "qid": target["qid"]["value"],
            "enwiki_title": target["enwiki_title"]["value"],
            "old_qids": ctx["qids"],
            "old_enwiki": ctx["enwiki"],
        }
        out["point_type"].append(
            {
                **base,
                "lat": target["coordinates"]["lat"],
                "lon": target["coordinates"]["lon"],
                "old_lat": ctx["lat"],
                "old_lon": ctx["lon"],
                "moved_m": data["facts"]["moved_m"],
                "quotes": target["coordinates"]["quotes"],
                "item_label": data["facts"]["label"],
                "item_description": data["facts"]["description"],
                "ask": "lane wd5 (relaxed coast guard, D19): the sourced point and the item's site type",
            }
        )
        out["description"].append(
            {
                **base,
                "old_description_lane": ctx["description_lane"],
                "ask": "lane W reads enwiki_title; the pinned scope SCOPE4.v3.json must admit the "
                "site again, else lane WN (the stored text has the town as its basis)",
            }
        )
        out["gallery"].append(
            {
                **base,
                "ask": "exclude the pictures of the town (chunk_writer) and search the new item's "
                "Commons category (candidate_search, INSERT lane)",
            }
        )
        out["period"].append(
            {**base, "ask": "re-research the period (D12) now that the referent is settled"}
        )
        out["card"].append(
            {**base, "ask": "the description's hash changed: the earlier card is stale (lane WB)"}
        )
    return out


def write_handoffs(
    run: Path, wave: str, records: Mapping[str, Sequence[Mapping[str, Any]]]
) -> dict[str, int]:
    out = wave_dir(run, wave)
    counts = {}
    for stage, rows in records.items():
        counts[stage] = common.write_jsonl(out / HANDOFF_FILES[stage], rows)
    return counts


# ------------------------------------------------------------------------------------ the chain
def chain_path(run: Path) -> Path:
    return run / DIR / CHAIN_FILE


def chain_state(run: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """`site -> stage -> {stamp, at}` of every stage recorded done."""
    path = chain_path(run)
    state: dict[str, dict[str, dict[str, Any]]] = {}
    if path.exists():
        for row in common.read_jsonl(path):
            state.setdefault(row["site_id"], {})[row["stage"]] = {
                "stamp": row["stamp"],
                "at": row["at"],
            }
    return state


def chain_done(
    run: Path, wave: str, stage: str, stamp: str, sites: Sequence[str] | None = None,
    *, at: str | None = None,
) -> list[str]:  # fmt: skip
    """Record that `stage` landed for the wave's sites (or the listed ones). Refused for a stage
    that is not in the chain, for a site of no wave, for a stage already done, and for a site whose
    earlier stages are not all done: one site finishes the chain in order."""
    if stage not in CHAIN:
        raise ChainError(f"{stage!r} is not a stage of the chain {CHAIN}")
    if not stamp.strip():
        raise ChainError("a stage is recorded with the run stamp that wrote it")
    wave_sites = load_wave(run, wave)["sites"]
    chosen = list(wave_sites if sites is None else sites)
    stranger = [s for s in chosen if s not in wave_sites]
    if stranger:
        raise ChainError(f"{stranger[:3]} are not sites of wave {wave}")
    state = chain_state(run)
    before = CHAIN[: CHAIN.index(stage)]
    for sid in chosen:
        done = state.get(sid, {})
        if stage in done:
            raise ChainError(f"{sid}: {stage} is recorded already ({done[stage]['stamp']})")
        missing = [s for s in before if s not in done]
        if missing:
            raise ChainError(f"{sid}: {stage} waits for {', '.join(missing)}")
    when = at or now_utc()
    path = chain_path(run)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for sid in chosen:
            fh.write(
                json.dumps(
                    {"site_id": sid, "wave": wave, "stage": stage, "stamp": stamp, "at": when},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return chosen


def chain_ready(run: Path, stage: str) -> list[str]:
    """The sites `stage` may start on: every earlier stage done, `stage` not."""
    if stage not in CHAIN:
        raise ChainError(f"{stage!r} is not a stage of the chain {CHAIN}")
    before = CHAIN[: CHAIN.index(stage)]
    state = chain_state(run)
    sites = sorted({s for path in (run / DIR / "waves").glob(f"*/{waves.WAVE_FILE}")
                    for s in json.loads(path.read_text(encoding="utf-8"))["sites"]})  # fmt: skip
    return [
        s
        for s in sites
        if stage not in state.get(s, {}) and all(b in state.get(s, {}) for b in before)
    ]


def chain_table(run: Path) -> list[dict[str, Any]]:
    """Every site of every wave with the stages done, for the status line."""
    state = chain_state(run)
    rows = []
    for path in sorted((run / DIR / "waves").glob(f"*/{waves.WAVE_FILE}")):
        record = json.loads(path.read_text(encoding="utf-8"))
        for sid in record["sites"]:
            done = state.get(sid, {})
            rows.append(
                {
                    "site_id": sid,
                    "wave": record["wave"],
                    "done": [s for s in CHAIN if s in done],
                    "next": next((s for s in CHAIN if s not in done), None),
                }
            )
    return rows
