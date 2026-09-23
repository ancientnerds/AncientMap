"""The acceptance of the Phase-4/5 writes (WB-C3): the journal, production and the verifier agree.

Design entry [6] of `output/remediation/logs/design_texts_images_2026-09-22.json`, section
verification, "WRITE ACCEPTANCE". A writer's own read-back is not an acceptance, so this asks
production directly, read-only, after every step of 100 sites and once more at the end:

1. **The journal chain** (`verify_writes.Link` and `check_chain`, the Phase-3 reader, imported):
   every journal row of the lane is a planned row's, with the planned old and new value, written
   once, and the last link of a continuous chain that ends in the live value. A planned row without
   a lane row still holds its old value (a later step) - or, with `--complete`, is a deviation. A
   planned row that holds neither is a deviation too: that is how a `matched_0` shows here.
   `raw_data` is jsonb, so its old, new and live values are compared as JSON, not as text:
   Postgres prints the keys in its own order.
2. **V1-V15 again** (`--run`, lanes `p4` and `p5`): every written site's description and
   `raw_data` read back from production, its card from production (`p5`) or from the run's
   `assembly.jsonl` (`p4`, before the cards are written), the pinned texts from the run's store,
   and the quotes from the journal's evidence (`evidence.sentences[i].quote`, which must name the
   provenance's own offsets), through `verify4.verify_site`. Any hold is a deviation.
3. **The in-database hash invariants**: Postgres' own `sha256` of the description equals
   `_description_provenance.desc_sha256` (`p4`, `p4l`), and of the card equals its `card.
   text_sha256` (`p5`).
4. **T08** (`census t08_citation_markers.run`) over the written sites (`p4`): 0 findings.
5. **The card file** (`--card-check`, `p5`): `phase4/card_json.py --check` is run and its own
   `*_EXIT=` line must read 0.
6. **The boot logs** (`--boot-logs --since <StartedAt>`, after Push #2): 0 `[STARTUP] Card
   description overwritten` lines in `ancient_nerds_api` and `ancient_nerds_api2`.

Every deviation is printed by name; the last line is `ACCEPT_EXIT=0` (none) or `ACCEPT_EXIT=1`,
and that line - not the process status of a wrapper - is what is read. The five sampled SSR pages
of the design are a Playwright check against production and not part of this tool.

    verify_writes4.py --lane p4 --plan <PLAN.jsonl> --run <runs/<run>>
    verify_writes4.py --lane p4l --plan <PLAN.jsonl>
    verify_writes4.py --lane p5 --plan <PLAN.jsonl> --run <runs/<run>> --card-check
    verify_writes4.py --boot-logs --since 2026-09-24T10:00:00Z

The lanes' journal stamps come from `lanes.py` (`p4`, `p4l`, `p5`: `phase4:`, `phase4l:`,
`phase5:`, WB-D1); `--stamp-like` overrides one.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import lanes  # noqa: E402 - paths, the JSON-lines reader and the database seam
import verify_writes as VW  # noqa: E402 - the Phase-3 journal-chain reader (Link, check_chain)
from census.tests import t08_citation_markers as T08  # noqa: E402 - on sys.path via lanes
from journal_chain import ROLLBACK_SUFFIX  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import verify4 as V4  # noqa: E402

REPO = lanes.REPO
CARD_JSON = REPO / "scripts" / "remediation" / "phase4" / "card_json.py"

#: The (table, column) pairs each lane may write (production_write, ROW GROUPS).
LANE_COLUMNS: dict[str, frozenset[tuple[str, str]]] = {
    "p4": frozenset({("unified_sites", "description"), ("unified_sites", "raw_data")}),
    "p4l": frozenset({("unified_sites", "raw_data")}),
    "p5": frozenset({("card_stats", "card_description")}),
}
#: The jsonb column: compared as JSON.
JSON_COLUMNS = frozenset({("unified_sites", "raw_data")})
#: The keys a planned row must carry (`write_stage.WriteRow`'s, which the P4/P5 plans reuse).
PLAN_KEYS = ("site_id", "table", "column", "pk", "old_value", "new_value", "change_key")
WINDOW = 200

#: production_write, step 3i: the line `api/services/card_descriptions.py` logs for every card the
#: boot import overwrote.
OVERWRITE_LINE = "[STARTUP] Card description overwritten"
API_CONTAINERS = ("ancient_nerds_api", "ancient_nerds_api2")
#: An RFC 3339 instant, as `docker inspect -f '{{.State.StartedAt}}'` prints it. Checked because it
#: travels through ssh into a remote shell.
_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})")
_EXIT_LINE = re.compile(r"^[A-Z][A-Z0-9_]*_EXIT=(\d+)$")

Key = tuple[str, str, str]  #: (table, column, row_pk)


def canonical(table: str, column: str, value: Any) -> str | None:
    """A value as the chain compares it: text as it is, jsonb as sorted JSON (`None` stays)."""
    if value is None:
        return None
    if (table, column) in JSON_COLUMNS:
        parsed = M.parse_json(value) if isinstance(value, str) else value
        return json.dumps(parsed, ensure_ascii=False, sort_keys=True)
    return str(value)


def _canonical_link(link: VW.Link) -> VW.Link:
    return VW.Link(
        id=link.id,
        table=link.table,
        column=link.column,
        pk=link.pk,
        old=canonical(link.table, link.column, link.old),
        new=canonical(link.table, link.column, link.new),
        stamp=link.stamp,
    )


# ------------------------------------------------------------------------------------------------
# 1. The journal chain
# ------------------------------------------------------------------------------------------------


@dataclass
class Acceptance4:
    """What production says about one lane's rows, counted and named."""

    carried: set[Key] = field(default_factory=set)  #: lane rows that hold their new value
    untouched: int = 0  #: planned rows not yet written that still hold their old value
    deviations: list[str] = field(default_factory=list)


def accept4(
    *,
    planned: Iterable[Mapping[str, Any]],
    lane_links: Iterable[VW.Link],
    chains: Mapping[Key, list[VW.Link]],
    live: Mapping[Key, str | None],
    present: set[tuple[str, str]],
    columns: frozenset[tuple[str, str]],
    complete: bool,
) -> Acceptance4:
    """The chain acceptance as a pure function of what the database returned.

    `lane_links`, `chains` and `live` carry canonical values (`canonical`); `present` holds the
    `(table, pk)` rows the live read found; `columns` are the lane's; `complete` makes a planned row
    that the lane did not write a deviation rather than a later step.
    """
    result = Acceptance4()
    plan: dict[Key, Mapping[str, Any]] = {}
    for row in planned:
        key = (row["table"], row["column"], row["pk"])
        if (key[0], key[1]) not in columns:
            result.deviations.append(
                f"PLANNED OUTSIDE THE LANE {key[2]} {key[0]}.{key[1]}: the lane writes "
                f"{sorted(f'{t}.{c}' for t, c in columns)} only"
            )
        plan[key] = row
    lane_by_key: dict[Key, list[VW.Link]] = collections.defaultdict(list)
    for link in lane_links:
        if (link.table, link.column) not in columns:
            result.deviations.append(
                f"OUTSIDE THE LANE {link.pk} {link.table}.{link.column}: journal row {link.id} "
                f"({link.stamp}) is a lane write of a column the lane does not write"
            )
            continue
        lane_by_key[link.key].append(link)

    for key, links in sorted(lane_by_key.items()):
        where = f"{key[2]} {key[0]}.{key[1]}"
        chain = chains.get(key, [])
        problems, _ = VW.check_chain(
            key, chain, live.get(key), missing=(key[0], key[2]) not in present
        )
        result.deviations.extend(problems)
        row = plan.get(key)
        if row is None:
            result.deviations.append(f"OUTSIDE THE PLAN {where}: journalled, never planned")
        if len(links) > 1:
            ids = ", ".join(str(link.id) for link in links)
            result.deviations.append(f"WRITTEN TWICE {where}: journal rows {ids}")
        ids_in_chain = [link.id for link in chain]
        sound = not problems and row is not None and len(links) == 1
        for link in links:
            if row is not None:
                want = (
                    canonical(key[0], key[1], row["old_value"]),
                    canonical(key[0], key[1], row["new_value"]),
                )
                if (link.old, link.new) != want:
                    sound = False
                    result.deviations.append(
                        f"OTHER VALUE {where}: journal row {link.id} wrote another transition "
                        "than the plan names"
                    )
            if link.id not in ids_in_chain:
                sound = False
                result.deviations.append(
                    f"CHAIN INCOMPLETE {where}: journal row {link.id} is missing from the chain"
                )
                continue
            later = chain[ids_in_chain.index(link.id) + 1 :]
            if later:
                sound = False
                stamps = list(dict.fromkeys(other.stamp for other in later))
                result.deviations.append(f"CHANGED LATER {where}: {stamps} wrote after {link.id}")
        if sound:
            result.carried.add(key)

    for key, row in sorted(plan.items()):
        if key in lane_by_key:
            continue
        where = f"{key[2]} {key[0]}.{key[1]}"
        if (key[0], key[2]) not in present:
            result.deviations.append(f"MISSING {where}: the row is not in the database")
        elif complete:
            result.deviations.append(f"NOT WRITTEN {where}: the acceptance is --complete")
        elif live.get(key) != canonical(key[0], key[1], row["old_value"]):
            result.deviations.append(
                f"MOVED {where}: not written by the lane, and it no longer holds its planned old "
                "value (a write elsewhere, or a chunk refused as matched_0)"
            )
        else:
            result.untouched += 1
    return result


# ------------------------------------------------------------------------------------------------
# The reads (read-only; every statement a SELECT through the writer's seam)
# ------------------------------------------------------------------------------------------------

JOURNAL_COLUMNS = "id, table_name, column_name, row_pk, old_value, new_value, run_stamp"


def _uuids(pks: Sequence[str]) -> str:
    """Key literals in the key column's own type, so the primary-key index is used (0022)."""
    return ", ".join(f"{lanes.sql_text(pk)}::uuid" for pk in pks)


def _pairs(columns: Iterable[tuple[str, str]]) -> str:
    return ", ".join(f"({lanes.sql_text(t)}, {lanes.sql_text(c)})" for t, c in sorted(columns))


def lane_journal_sql(stamp_like: str) -> str:
    return (
        f"SELECT to_jsonb(t)::text FROM (SELECT {JOURNAL_COLUMNS} FROM remediation_change_log "
        f"WHERE run_stamp LIKE {lanes.sql_text(stamp_like)} "
        f"AND run_stamp NOT LIKE {lanes.sql_text('%' + ROLLBACK_SUFFIX)} ORDER BY id) t;\n"
    )


def chain_sql(pks: Sequence[str], columns: Iterable[tuple[str, str]]) -> str:
    """Every journal row of these rows and columns, all stamps (a kept reversal is a link)."""
    return (
        f"SELECT to_jsonb(t)::text FROM (SELECT {JOURNAL_COLUMNS} FROM remediation_change_log "
        f"WHERE (table_name, column_name) IN ({_pairs(columns)}) "
        f"AND row_pk IN ({lanes.sql_literals(pks)}) ORDER BY id) t;\n"
    )


def live_sql(pks: Sequence[str]) -> str:
    """The written values and Postgres' own hash invariants, one object per site."""
    return (
        "SELECT to_jsonb(t)::text FROM (SELECT u.id::text AS id, u.description, u.raw_data, "
        "c.site_id IS NOT NULL AS has_card_row, c.card_description, "
        "(u.raw_data->'_description_provenance'->>'desc_sha256') = "
        "encode(sha256(convert_to(u.description, 'UTF8')), 'hex') AS desc_invariant, "
        "(u.raw_data->'_description_provenance'->'card'->>'text_sha256') = "
        "encode(sha256(convert_to(c.card_description, 'UTF8')), 'hex') AS card_invariant "
        "FROM unified_sites u LEFT JOIN card_stats c ON c.site_id = u.id "
        f"WHERE u.id IN ({_uuids(pks)})) t;\n"
    )


def evidence_sql(pks: Sequence[str]) -> str:
    """The description rows' journal evidence (the quotes), all stamps, oldest first."""
    return (
        "SELECT to_jsonb(t)::text FROM (SELECT id, row_pk, run_stamp, evidence "
        "FROM remediation_change_log WHERE table_name = 'unified_sites' "
        f"AND column_name = 'description' AND row_pk IN ({lanes.sql_literals(pks)}) "
        f"AND run_stamp NOT LIKE {lanes.sql_text('%' + ROLLBACK_SUFFIX)} ORDER BY id) t;\n"
    )


@dataclass
class Production:
    """What the reads returned, keyed for the checks."""

    lane_links: list[VW.Link]
    chains: dict[Key, list[VW.Link]]
    live: dict[Key, str | None]
    present: set[tuple[str, str]]
    rows: dict[str, dict[str, Any]]  #: the live row per site id


def read_production(
    pks: Sequence[str],
    *,
    stamp_like: str,
    columns: frozenset[tuple[str, str]],
    run: Callable[[str], str],
) -> Production:
    lane_links = [
        _canonical_link(VW.Link.from_row(row))
        for row in lanes.json_rows(run(lane_journal_sql(stamp_like)))
    ]
    everyone = sorted(set(pks) | {link.pk for link in lane_links})
    chains: dict[Key, list[VW.Link]] = collections.defaultdict(list)
    live: dict[Key, str | None] = {}
    present: set[tuple[str, str]] = set()
    rows: dict[str, dict[str, Any]] = {}
    for start in range(0, len(everyone), WINDOW):
        window = everyone[start : start + WINDOW]
        for row in lanes.json_rows(run(chain_sql(window, columns))):
            link = _canonical_link(VW.Link.from_row(row))
            chains[link.key].append(link)
        for row in lanes.json_rows(run(live_sql(window))):
            site = row["id"]
            rows[site] = row
            present.add(("unified_sites", site))
            live[("unified_sites", "description", site)] = row["description"]
            live[("unified_sites", "raw_data", site)] = canonical(
                "unified_sites", "raw_data", row["raw_data"]
            )
            if row["has_card_row"]:
                present.add(("card_stats", site))
                live[("card_stats", "card_description", site)] = row["card_description"]
    for chain in chains.values():
        chain.sort(key=lambda link: link.id)
    return Production(lane_links, dict(chains), live, present, rows)


# ------------------------------------------------------------------------------------------------
# 2-4. V1-V15 on the read-back, the hash invariants, T08
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RunSite:
    """One site of the run: its batch, its plan record and its assembly (None if it had none)."""

    batch_dir: pathlib.Path
    site: M.PlanSite
    assembly: M.Assembly | None


def index_run(run_dir: pathlib.Path) -> dict[str, RunSite]:
    """Every site of every batch of the run, through `verify4.read_batch`. A batch that cannot be
    read stops the acceptance: its sites would otherwise look like sites that were never run."""
    found: dict[str, RunSite] = {}
    for batch_dir in sorted(p for p in run_dir.iterdir() if (p / M.INPUT_FILE).exists()):
        try:
            inputs = V4.read_batch(batch_dir)
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(f"{batch_dir}: the batch cannot be read: {exc}") from exc
        assemblies = {assembly.site_id: assembly for assembly in inputs.assemblies}
        for site_id, site in inputs.sites.items():
            found[site_id] = RunSite(batch_dir, site, assemblies.get(site_id))
    return found


def journal_quotes(
    evidence_rows: Iterable[Mapping[str, Any]], provenance: M.Provenance, site_id: str
) -> tuple[list[str] | None, str | None]:
    """The quotes of the site's last description write, checked against the provenance offsets.
    (quotes, None) or (None, why not)."""
    rows = [row for row in evidence_rows if row["row_pk"] == site_id]
    if not rows:
        return None, "no journal row of its description"
    evidence = rows[-1]["evidence"]
    sentences = evidence.get("sentences") if isinstance(evidence, Mapping) else None
    if not isinstance(sentences, list) or len(sentences) != len(provenance.sentences):
        return None, "the journal evidence does not list one quote per published sentence"
    quotes: list[str] = []
    for entry, sentence in zip(sentences, provenance.sentences, strict=True):
        if not isinstance(entry, Mapping) or not isinstance(entry.get("quote"), str):
            return None, "a journal evidence sentence carries no quote"
        if (entry.get("start"), entry.get("end")) != (sentence.start, sentence.end):
            return None, "the journal evidence names other offsets than the provenance"
        quotes.append(entry["quote"])
    return quotes, None


def reverify(
    *,
    site_ids: Iterable[str],
    lane: str,
    production: Production,
    evidence_rows: Sequence[Mapping[str, Any]],
    run: Mapping[str, RunSite],
) -> list[str]:
    """`verify4.verify_site` on each written site as production holds it, with the journal's
    quotes and the run's pinned texts."""
    deviations: list[str] = []
    for site_id in sorted(site_ids):
        row = production.rows.get(site_id)
        entry = run.get(site_id)
        if row is None or entry is None:
            deviations.append(f"REVERIFY {site_id}: not in the database read or not in the run")
            continue
        raw = row["raw_data"]
        try:
            provenance = M.Provenance.from_dict(raw[M.PROVENANCE_KEY])
            citations = tuple(M.Citation.from_dict(c) for c in raw[M.CITATIONS_KEY])
        except (KeyError, TypeError, ValueError) as exc:
            deviations.append(f"REVERIFY {site_id}: the written provenance does not read: {exc}")
            continue
        if lane == "p5":
            card = row["card_description"]
        else:
            card = entry.assembly.card if entry.assembly is not None else None
        quotes, why = journal_quotes(evidence_rows, provenance, site_id)
        if quotes is None:
            deviations.append(f"REVERIFY {site_id}: {why}")
            continue
        try:
            assembly = M.Assembly(
                site_id=site_id,
                description=row["description"],
                citations=citations,
                card=card,
                provenance=provenance,
            )
        except ValueError as exc:
            deviations.append(f"REVERIFY {site_id}: production does not form an assembly: {exc}")
            continue
        store = F.EvidenceStore(entry.batch_dir / M.EVIDENCE_DIR)
        metas: dict[str, Any] = {}
        texts: dict[str, str] = {}
        for ref in provenance.sources:
            meta, text = V4.read_store(store, site_id, ref.id)
            if meta is not None:
                metas[ref.id] = meta
            if text is not None:
                texts[ref.id] = text
        for hold in V4.verify_site(
            entry.site, assembly, metas=metas, texts=texts, quotes=quotes, new_raw_data=raw
        ):
            deviations.append(
                f"REVERIFY {site_id} {hold.reason.value} ({hold.scope.value}): {hold.detail}"
            )
    return deviations


def invariant_deviations(*, lane: str, carried: Iterable[Key], production: Production) -> list[str]:
    """The design's in-database invariants, as Postgres computed them in `live_sql`."""
    deviations: list[str] = []
    sites = sorted({key[2] for key in carried})
    for site_id in sites:
        row = production.rows[site_id]
        if lane in ("p4", "p4l") and row["desc_invariant"] is not True:
            deviations.append(
                f"INVARIANT {site_id}: desc_sha256 is not Postgres' sha256 of the description"
            )
        if lane == "p4l":
            try:
                M.LegacyProvenance.from_dict(row["raw_data"][M.PROVENANCE_KEY])
            except (KeyError, TypeError, ValueError) as exc:
                deviations.append(
                    f"INVARIANT {site_id}: the legacy provenance does not read: {exc}"
                )
        if (
            lane == "p5"
            and row["card_description"] is not None
            and row["card_invariant"] is not True
        ):
            deviations.append(
                f"INVARIANT {site_id}: card.text_sha256 is not Postgres' sha256 of the card"
            )
    return deviations


@dataclass(frozen=True)
class _Sites:
    """The one thing `T08.run` reads of a census context."""

    sites: list[dict[str, Any]]


def t08_deviations(site_ids: Iterable[str], production: Production) -> list[str]:
    sites = [
        {
            "id": site_id,
            "description": production.rows[site_id]["description"],
            "raw_data": production.rows[site_id]["raw_data"],
        }
        for site_id in sorted(site_ids)
    ]
    return [
        f"T08 {finding.site_id} {finding.test_id}: {finding.note}"
        for finding in T08.run(_Sites(sites))
    ]


# ------------------------------------------------------------------------------------------------
# 5-6. The card file and the boot logs (commands, through one seam)
# ------------------------------------------------------------------------------------------------


def run_command(argv: Sequence[str]) -> tuple[int, str]:
    """(exit status, stdout and stderr) of one command. The seam the tests replace."""
    proc = subprocess.run(
        list(argv), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def exit_line(output: str) -> int | None:
    """The command's own last `*_EXIT=<n>` line; `None` when it printed none."""
    codes = [
        int(m.group(1))
        for m in (_EXIT_LINE.match(line.strip()) for line in output.splitlines())
        if m
    ]
    return codes[-1] if codes else None


def card_file_deviations(command: Callable[[Sequence[str]], tuple[int, str]]) -> list[str]:
    """production_write: `card_json.py --check` - the file equals the database for every entry."""
    if not CARD_JSON.exists():
        return [f"CARD FILE: {CARD_JSON} is not on this tree (WB-D3)"]
    _, output = command([sys.executable, str(CARD_JSON), "--check"])
    code = exit_line(output)
    if code != 0:
        return [f"CARD FILE: card_json.py --check ended with its exit line {code!r}"]
    return []


def boot_log_deviations(
    since: str, *, host: str, command: Callable[[Sequence[str]], tuple[int, str]]
) -> list[str]:
    """production_write 3i: no card overwrite since the deploy, in either API container."""
    if not _INSTANT.fullmatch(since):
        raise SystemExit(f"--since {since!r} is not an RFC 3339 instant (docker inspect StartedAt)")
    deviations: list[str] = []
    for container in API_CONTAINERS:
        status, output = command(["ssh", host, "docker", "logs", "--since", since, container])
        if status != 0:
            deviations.append(f"BOOT LOG {container}: docker logs exited {status}")
            continue
        count = sum(OVERWRITE_LINE in line for line in output.splitlines())
        if count:
            deviations.append(f"BOOT LOG {container}: {count} '{OVERWRITE_LINE}' line(s)")
    return deviations


# ------------------------------------------------------------------------------------------------
# The command
# ------------------------------------------------------------------------------------------------


def read_plan(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = lanes.read_jsonl(path)
    for number, row in enumerate(rows, 1):
        missing = [key for key in PLAN_KEYS if key not in row]
        if missing:
            raise SystemExit(f"{path}:{number}: a planned row without {missing}")
    return rows


def accept_lane(args: argparse.Namespace, run: Callable[[str], str]) -> list[str]:
    lane = args.lane
    columns = LANE_COLUMNS[lane]
    stamp_like = args.stamp_like or lanes.lane(lane).stamp_like
    planned = read_plan(pathlib.Path(args.plan))
    pks = sorted({row["pk"] for row in planned})
    production = read_production(pks, stamp_like=stamp_like, columns=columns, run=run)
    result = accept4(
        planned=planned,
        lane_links=production.lane_links,
        chains=production.chains,
        live=production.live,
        present=production.present,
        columns=columns,
        complete=args.complete,
    )
    print(
        f"lane {lane} | stamps {stamp_like} | planned rows {len(planned)} | lane journal rows "
        f"{len(production.lane_links)} | carried {len(result.carried)} | not yet written "
        f"{result.untouched}"
    )
    deviations = list(result.deviations)
    deviations += invariant_deviations(lane=lane, carried=result.carried, production=production)
    written = {key[2] for key in result.carried}
    if lane == "p4":
        written = {
            site
            for site in written
            if {("unified_sites", "description", site), ("unified_sites", "raw_data", site)}
            <= result.carried
        }
        deviations += t08_deviations(written, production)
    if lane == "p5":
        written = {
            site
            for site in written
            if production.live.get(("card_stats", "card_description", site)) is not None
        }
    if lane in ("p4", "p5"):
        if args.run is None:
            raise SystemExit(f"lane {lane} re-runs V1-V15 on the written sites: --run is required")
        evidence_rows: list[dict[str, Any]] = []
        ordered = sorted(written)
        for start in range(0, len(ordered), WINDOW):
            evidence_rows += lanes.json_rows(run(evidence_sql(ordered[start : start + WINDOW])))
        deviations += reverify(
            site_ids=written,
            lane=lane,
            production=production,
            evidence_rows=evidence_rows,
            run=index_run(pathlib.Path(args.run)),
        )
        print(f"re-verified {len(written)} written site(s) with V1-V15")
    return deviations


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(prog="verify-writes4")
    parser.add_argument("--lane", choices=sorted(LANE_COLUMNS))
    parser.add_argument("--plan", help="the lane's PLAN.jsonl (write4)")
    parser.add_argument("--run", help="the Phase-4 run directory (runs/<run>)")
    parser.add_argument("--stamp-like", default=None, help="override the lane's stamp pattern")
    parser.add_argument("--complete", action="store_true", help="every planned row is written")
    parser.add_argument("--card-check", action="store_true", help="run card_json.py --check")
    parser.add_argument("--boot-logs", action="store_true", help="read both API boot logs")
    parser.add_argument("--since", help="the containers' StartedAt (with --boot-logs)")
    parser.add_argument("--host", default=lanes.HOST)
    args = parser.parse_args(argv)
    if args.boot_logs == bool(args.lane):
        parser.error("name exactly one of --lane and --boot-logs")

    deviations: list[str] = []
    if args.boot_logs:
        if args.since is None:
            parser.error("--boot-logs needs --since (the StartedAt recorded after the deploy)")
        deviations += boot_log_deviations(args.since, host=args.host, command=run_command)
    else:
        if args.plan is None:
            parser.error("--lane needs --plan")
        deviations += accept_lane(args, run=lambda sql: lanes.psql(sql, host=args.host))
        if args.card_check:
            deviations += card_file_deviations(run_command)
    for line in deviations:
        print(f"  {line}")
    print(f"RESULT: {len(deviations)} deviation(s)")
    code = 1 if deviations else 0
    print(f"ACCEPT_EXIT={code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
