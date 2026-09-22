"""Does the writer change exactly the rows the reviewer cleared, and nothing else?

Piece 6 of the Phase-3 runner. Everything before this stage proposes; this is the first part of the
pipeline that changes a record, so the mistakes that matter are the quiet ones:

* a field the reviewer did **not** clear reaching the database - the file's own `applies` boolean is a
  copy of `asked and refuted is False and not problems`, and a copy can disagree with its source;
* a report-only field written anyway: `card_stats.card_description` is re-derived on every API boot,
  so the write would be gone at the next start while the journal kept claiming it;
* a value a start-up producer would rewrite - `site_type` through `normalize_site_type`, `country`
  and `period_start` through `pipeline/lyra/data_patches.py`'s two patches. Those two are guarded on
  `source_id = 'lyra'`, which is why a curated row is safe; the test reads the guards out of that file
  rather than trusting this paragraph;
* a statement run for a plan it was not generated from. `APPLY.sql` carries
  `-- plan digest sha256:<hex>` over the rows it was rendered from, and the apply path refuses a file
  pinned to another plan - the defect the mechanical lane's `--apply` has
  (`[H] SECURITY 3 / BACKEND B7`);
* a chunk whose rows moved since the snapshot being written anyway, or a write checked with a count
  instead of row for row;
* a reversal that is kept, or one that reuses the write's own change key - the journal would then read
  as if the write had happened twice.

Each guard below has a test that fails when the guard is removed; the mutation evidence (the mutation,
the failing assertion and the restored file's sha256) is in
`output/remediation/phase3_runner/PIECE6.md`. No test here opens a socket or starts a process: the one
seam this module has is a fake psql, which remembers what it was sent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402
from phase3 import write_stage as W  # noqa: E402
from phase3.run import InputError  # noqa: E402

SITE_A = "11111111-1111-4111-8111-111111111111"
SITE_B = "22222222-2222-4222-8222-222222222222"
BATCH = "batch-0001"
#: The sentence every fixture page carries, and the one a fixture answer quotes by default.
QUOTE = "the page states the corrected value"


def _name(site_id: str) -> str:
    return f"Site {site_id[:8]}"


def _page(site_id: str) -> str:
    """The one page a fixture site's record buys (`fetch_stage.targets_for_site`: enwiki by name).

    A citation must name a page the batch fetched, so the fixture's answers cite the site's own
    target URL rather than an invented one - the writer checks exactly that since 2026-09-22.
    """
    return F.wikipedia_extract_url(_name(site_id))


PAGE = _page(SITE_A)

#: The stored values the fixture batches carry, one per planned field.
STORED: dict[str, Any] = {
    "description": "a stored description",
    "site_type": "Cave",
    "country": "Georgia",
    "period_start": 1500,
    "card_description": "a stored card",
}

#: The comment lines that introduce this stage's three reads. The fake psql tells them apart by their
#: prefix rather than by parsing SQL, so a read that lost its identifying comment comes back empty and
#: the test that needed it says so.
VALUE_READ = "-- the value each named row holds now"
JOURNAL_READ = "-- the journal rows of this chunk's changes"
COUNT_READ = "-- how many journal rows this stamp has"

#: One rendered row of the `INSERT INTO _phase3_plan ... VALUES` block.
ROW_RE = re.compile(
    r"^    \('(?P<site>[^']+)'::uuid, '(?P<column>[^']*)', '(?P<pk_column>[^']*)', "
    r"'(?P<pk>[^']*)', (?P<old>NULL|'(?:[^']|'')*'), (?P<new>NULL|'(?:[^']|'')*'), "
    r"'(?P<key>[^']*)', '(?P<test_id>[^']*)', ",
    re.MULTILINE,
)


# ── helpers ──────────────────────────────────────────────────────────────────────────────────


def _unquote(text: str) -> str | None:
    """A rendered SQL literal back to its value. `NULL` is `None`, and `''` is an empty string."""
    if text == "NULL":
        return None
    return text[1:-1].replace("''", "'")


def _answer(
    *,
    proposed: str | None,
    verdict: str = "WRONG",
    url: str = PAGE,
    quote: str = QUOTE,
) -> str:
    """One finder answer, in the shape `discover_stage.parse_answer` reads."""
    lines = [
        "The page states a value other than the one this site stores.",
        "EVIDENCE: the page gives the value this site does not store",
    ]
    if proposed is not None:
        lines.append(f"PROPOSED: {proposed}")
    if url:
        lines.append(f'SOURCE: {url} - "{quote}"')
    lines.append(f"VERDICT: {verdict}")
    return "\n".join(lines) + "\n"


def _verdict_row(
    site_id: str,
    field: str,
    *,
    refuted: bool | None = True,
    reason: str = "checked against the page the finder cited",
    asked: bool = True,
    problems: tuple[str, ...] = (),
    applies: bool | None = None,
) -> dict[str, Any]:
    """One `review.json` verdict. `applies` defaults to the rule and can be lied about."""
    computed = asked and refuted is False and not problems
    return {
        "site_id": site_id,
        "field": field,
        "asked": asked,
        "applies": computed if applies is None else applies,
        "refuted": refuted,
        "reason": reason,
        "sources": [{"url": PAGE, "quote": QUOTE}]
        if refuted is False
        else [],
        "problems": list(problems),
        "unreviewable": None if asked else "the question did not fit in the evidence budget",
    }


def _cleared(site_id: str, field: str, **kwargs: Any) -> dict[str, Any]:
    """The verdict that lets the writer act: asked, not refuted, nothing wrong with the answer."""
    return _verdict_row(site_id, field, refuted=False, **kwargs)


def _enwiki_page(text: str) -> str:
    """An enwiki evidence file the way the fetch stage stores it: the API's JSON, escapes and all."""
    return json.dumps(
        {"query": {"pages": {"1": {"title": "Site", "extract": text}}}}, ensure_ascii=True
    )


def _batch(
    tmp_path: Path,
    *,
    sites: tuple[str, ...] = (SITE_A,),
    cleared: dict[tuple[str, str], dict[str, Any]] | None = None,
    answers: dict[tuple[str, str], str] | None = None,
    pages: dict[str, str] | None = None,
) -> Path:
    """One batch directory: `input.json`, `review.json`, the answers and the evidence they cite.

    Every field of every site gets a verdict, by default a refuting one, so a test that clears one
    field is not also testing the "no verdict" path. `cleared` names the verdicts a test replaces and
    `answers` the answer texts it writes. Every site's one evidence target (`_page`) is on disk and,
    unless `pages` gives its stored text, carries `QUOTE` - the page a real batch's finder was shown.
    """
    cleared = dict(cleared or {})
    answers = dict(answers or {})
    pages = dict(pages or {})
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / W.INPUT_FILE).write_text(
        json.dumps(
            {
                "batch_id": BATCH,
                "ordinal": 1,
                "pass": "discover",
                "sites": [
                    {
                        "site_id": site_id,
                        "name": _name(site_id),
                        "findings": [
                            SP.finding_row(field, STORED[field]) for field in SP.DISCOVER_FIELDS
                        ],
                    }
                    for site_id in sites
                ],
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    verdicts = [
        cleared.get((site_id, field), _verdict_row(site_id, field))
        for site_id in sites
        for field in SP.DISCOVER_FIELDS
    ]
    (batch_dir / W.REVIEW_FILE).write_text(
        json.dumps(
            {
                "batch_id": BATCH,
                "stage": "reviewer",
                "verdicts": verdicts,
                "applies": sum(1 for verdict in verdicts if verdict["applies"]),
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    store = F.EvidenceStore(batch_dir / W.ANSWERS_DIR)
    for (site_id, field), text in answers.items():
        store.write(site_id=site_id, feature=field, body=text.encode("utf-8"))
    evidence = F.EvidenceStore(batch_dir / W.EVIDENCE_DIR)
    for site_id in sites:
        stored = pages.get(site_id, _enwiki_page(f"Some context. {QUOTE.capitalize()}. More."))
        evidence.write(site_id=site_id, feature=F.FEATURE_ENWIKI, body=stored.encode("utf-8"))
    return batch_dir


def _cleared_batch(
    tmp_path: Path, *, field: str = "country", proposed: str = "United States", **kwargs: Any
) -> Path:
    """A batch whose one cleared field is `field` and whose answer proposes `proposed`."""
    return _batch(
        tmp_path,
        cleared={(SITE_A, field): _cleared(SITE_A, field)},
        answers={(SITE_A, field): _answer(proposed=proposed)},
        **kwargs,
    )


def _plan(tmp_path: Path, **kwargs: Any) -> W.WritePlan:
    return W.load_plan(_cleared_batch(tmp_path, **kwargs))


def _rendered(tmp_path: Path, *, field: str = "country", proposed: str = "United States") -> Any:
    """The one-chunk case, rendered to disk: the chunk, `APPLY.sql`, `ROLLBACK.sql`."""
    plan, out = _one_row(tmp_path, field=field, proposed=proposed)
    chunks = W.chunks_for(plan)
    W.write_plan_files(out, plan, chunks=chunks)
    directory = out / W.CHUNKS_DIR / chunks[0].label
    return (
        chunks[0],
        (directory / W.APPLY_FILE).read_text(encoding="utf-8"),
        (directory / W.ROLLBACK_FILE).read_text(encoding="utf-8"),
    )


def _one_row(tmp_path: Path, *, field: str = "country", proposed: str = "United States") -> Any:
    """A plan with exactly one writable row, and the directory its statements go to."""
    return (
        W.load_plan(_cleared_batch(tmp_path, field=field, proposed=proposed)),
        tmp_path / "writes",
    )


def _ready(tmp_path: Path, **kwargs: Any) -> Any:
    """`_one_row` plus the rendered chunk, which is what the apply path needs on disk."""
    plan, out = _one_row(tmp_path, **kwargs)
    chunks = W.chunks_for(plan)
    W.write_plan_files(out, plan, chunks=chunks)
    return plan, out, chunks[0]


def _row(site_id: str, column: str, new_value: str, *, old_value: str = "Georgia") -> W.WriteRow:
    """One hand-built row, for the tests that are about chunking rather than about planning."""
    table = SP.FIELD_STORED_IN[column]
    return W.WriteRow(
        site_id=site_id,
        site_name=f"Site {site_id[:8]}",
        table=table,
        pk_column=W.PK_COLUMN[table],
        pk=site_id,
        column=column,
        old_value=old_value,
        new_value=new_value,
        test_id=f"{SP.TEST_ID_PREFIX}{column}",
        evidence=(
            {"source": "finder-answer", "url": PAGE, "quote": "q", "host": "en.wikipedia.org"},
        ),
        verdict=_cleared(site_id, column),
        change_key=W.change_key(
            site_id=site_id,
            table=table,
            column=column,
            old_value=old_value,
            new_value=new_value,
            test_id=f"{SP.TEST_ID_PREFIX}{column}",
        ),
    )


def _current(plan: W.WritePlan) -> dict[tuple[str, str], Any]:
    """What the rows hold before the write: the old values the plan names."""
    return {(row.site_id, row.column): row.old_value for row in plan.rows}


class FakePsql:
    """A psql that remembers. This module's one seam, and the only thing the tests replace.

    It answers the three reads this stage sends and, for a transaction, applies the plan `INSERT`'s
    rows unless the statement ends in `ROLLBACK;` - so a reversal that commits shows up as data that
    moved back. The `DO` block's guards are **not** re-implemented here: a fake that simulated the
    guards would only test itself, so the guards are asserted on the rendered text instead.
    """

    def __init__(
        self,
        rows: dict[tuple[str, str], Any],
        *,
        sources: dict[str, str] | None = None,
        journal: list[dict[str, Any]] | None = None,
        sabotage: dict[tuple[str, str], Any] | None = None,
        extra_journal: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self.rows = dict(rows)
        self.sources = {site_id: "ancient_nerds" for site_id, _ in self.rows}
        self.sources.update(sources or {})
        self.journal: list[dict[str, Any]] = list(journal or ())
        #: What the database keeps even though the statement wrote something else.
        self.sabotage = dict(sabotage or {})
        #: Journal rows this run's stamp carries that no planned row accounts for.
        self.extra_journal = extra_journal
        self.sent: list[str] = []
        self.hosts: list[str] = []

    def __call__(self, sql: str, *, host: str) -> str:
        self.sent.append(sql)
        self.hosts.append(host)
        if sql.startswith(VALUE_READ):
            return self._values(sql)
        if sql.startswith(JOURNAL_READ):
            return self._journal(sql)
        if sql.startswith(COUNT_READ):
            return self._count(sql)
        self._transaction(sql)
        return ""

    @property
    def transactions(self) -> list[str]:
        return [sql for sql in self.sent if not sql.startswith("--")]

    def _values(self, sql: str) -> str:
        column = re.search(r"u\.(\w+) AS value", sql)
        assert column is not None, "the read statement does not name its column"
        name = column.group(1)
        out = []
        for site_id in re.findall(r"'(?P<id>[0-9a-f-]{36})'::uuid", sql):
            if (site_id, name) in self.rows:
                out.append(
                    json.dumps(
                        {
                            "id": site_id,
                            "value": self.rows[(site_id, name)],
                            "source_id": self.sources.get(site_id, "ancient_nerds"),
                        }
                    )
                )
        return "\n".join(out) + ("\n" if out else "")

    def _journal(self, sql: str) -> str:
        wanted = set(re.findall(r"'(phase3:[^']*)'", sql))
        rows = [json.dumps(entry) for entry in self.journal if entry["change_key"] in wanted]
        return "\n".join(rows) + ("\n" if rows else "")

    def _count(self, sql: str) -> str:
        stamp = re.search(r"run_stamp = '([^']*)'", sql)
        assert stamp is not None, "the count statement does not name its stamp"
        return str(sum(1 for entry in self.journal if entry["run_stamp"] == stamp.group(1)))

    def _transaction(self, sql: str) -> None:
        rows = [match.groupdict() for match in ROW_RE.finditer(sql)]
        if "\nROLLBACK;" in sql or not rows:
            return
        stamp = re.search(r"r\.test_id, '([^']*)', r\.change_key", sql)
        for row in rows:
            site_id, column = row["site"], row["column"]
            new = _unquote(row["new"])
            self.rows[(site_id, column)] = self.sabotage.get((site_id, column), new)
            self.journal.append(
                {
                    "row_pk": row["pk"],
                    "table_name": "unified_sites",
                    "column_name": column,
                    "change_key": row["key"],
                    "old_value": _unquote(row["old"]),
                    "new_value": new,
                    "test_id": row["test_id"],
                    "run_stamp": stamp.group(1) if stamp else "",
                }
            )
        self.journal.extend(self.extra_journal)


# ── the plan ─────────────────────────────────────────────────────────────────────────────────


def test_the_plan_takes_the_new_value_from_the_answer_and_the_old_one_from_the_batch(
    tmp_path: Path,
) -> None:
    """One row: the value out of the finder's text, the old value and test id out of the batch."""
    plan = _plan(tmp_path)
    assert len(plan.rows) == 1
    row = plan.rows[0]
    assert (row.site_id, row.column, row.old_value, row.new_value) == (
        SITE_A,
        "country",
        "Georgia",
        "United States",
    )
    assert (row.table, row.pk_column, row.pk, row.test_id) == (
        "unified_sites",
        "id",
        SITE_A,
        "P3/country",
    )
    assert (plan.batch_id, plan.pass_name) == (BATCH, "discover")


def test_a_refuted_verdict_is_refused_and_counted_as_not_cleared(tmp_path: Path) -> None:
    """A refuted finding stays visible as a refusal naming the refutation, and is not a row."""
    plan = W.load_plan(
        _batch(
            tmp_path,
            cleared={(SITE_A, "country"): _verdict_row(SITE_A, "country")},
            answers={(SITE_A, "country"): _answer(proposed="United States")},
        )
    )
    assert plan.rows == []
    refusals = {refusal.field: refusal for refusal in plan.refused_fields(W.RULE_REVIEWER)}
    assert set(refusals) == set(SP.DISCOVER_FIELDS)
    assert "refuted" in refusals["country"].detail


def test_a_verdict_whose_parts_refute_it_is_not_cleared_by_its_own_applies_flag(
    tmp_path: Path,
) -> None:
    """The writer recomputes `applies` from the parts; the file's boolean cannot clear a finding.

    `review.json` carries `applies` as a convenience for its readers, and it is a *copy* of `asked and
    refuted is False and not problems` (`review_stage.ReviewVerdict.applies`). A copy can disagree
    with its source - an older revision wrote it, or a line was edited - and the rule for "a writer
    may act here" belongs to the stage that owns it.
    """
    plan = W.load_plan(
        _batch(
            tmp_path,
            cleared={
                (SITE_A, "country"): _verdict_row(SITE_A, "country", refuted=True, applies=True)
            },
            answers={(SITE_A, "country"): _answer(proposed="United States")},
        )
    )
    assert plan.rows == []
    refusals = {refusal.field: refusal for refusal in plan.refused_fields(W.RULE_REVIEWER)}
    assert set(refusals) == set(SP.DISCOVER_FIELDS)
    assert "refuted" in refusals["country"].detail


def test_a_field_without_a_verdict_is_refused_rather_than_forgotten(tmp_path: Path) -> None:
    """A field nobody judged is recorded with its rule, so an empty plan is not a clean batch."""
    batch_dir = _batch(tmp_path)
    review = json.loads((batch_dir / W.REVIEW_FILE).read_text(encoding="utf-8"))
    review["verdicts"] = [
        verdict for verdict in review["verdicts"] if verdict["field"] != "period_start"
    ]
    (batch_dir / W.REVIEW_FILE).write_text(json.dumps(review), encoding="utf-8", newline="\n")
    plan = W.load_plan(batch_dir)
    assert [refusal.field for refusal in plan.refused_fields(W.RULE_NO_VERDICT)] == ["period_start"]
    assert plan.refusals_by_rule()[W.RULE_NO_VERDICT] == 1


def test_the_report_only_fields_are_refused_though_the_reviewer_cleared_them(
    tmp_path: Path,
) -> None:
    """Both report-only fields are refused even though the reviewer said yes to them."""
    plan = W.load_plan(
        _batch(
            tmp_path,
            cleared={
                (SITE_A, "description"): _cleared(SITE_A, "description"),
                (SITE_A, "card_description"): _cleared(SITE_A, "card_description"),
            },
            answers={
                (SITE_A, "description"): _answer(proposed="a better description"),
                (SITE_A, "card_description"): _answer(proposed="a better card"),
            },
        )
    )
    assert plan.rows == []
    refusals = plan.refused_fields(W.RULE_REPORT_ONLY)
    assert sorted(refusal.field for refusal in refusals) == ["card_description", "description"]


def test_the_two_report_only_reasons_stay_apart(tmp_path: Path) -> None:
    """The boot overwriter is named as such, the phase split as such - not one shared text."""
    plan = W.load_plan(
        _batch(
            tmp_path,
            cleared={
                (SITE_A, "description"): _cleared(SITE_A, "description"),
                (SITE_A, "card_description"): _cleared(SITE_A, "card_description"),
            },
            answers={
                (SITE_A, "description"): _answer(proposed="a better description"),
                (SITE_A, "card_description"): _answer(proposed="a better card"),
            },
        )
    )
    detail = {refusal.field: refusal.detail for refusal in plan.refused_fields(W.RULE_REPORT_ONLY)}
    assert "api/main.py:506" in detail["card_description"]
    assert "Phase 5" in detail["description"]
    assert detail["description"] != detail["card_description"]


def test_a_site_type_the_normaliser_would_rewrite_is_refused(tmp_path: Path) -> None:
    """`settlement` is not a fixed point of the boot normaliser, so it is refused by that name."""
    plan = _plan(tmp_path, field="site_type", proposed="settlement")
    assert plan.rows == []
    refusal = plan.refused_fields(W.RULE_FIXED_POINT)[0]
    assert refusal.field == "site_type" and "normalize_site_type" in refusal.detail


def test_a_site_type_that_is_a_fixed_point_is_planned(tmp_path: Path) -> None:
    """`Settlement` survives the normaliser, so that row is a row - the guard is not a blanket."""
    plan = _plan(tmp_path, field="site_type", proposed="Settlement")
    assert [row.column for row in plan.rows] == ["site_type"]
    assert plan.rows[0].new_value == "Settlement"


def test_a_country_is_writable_because_its_patcher_guards_on_the_source(tmp_path: Path) -> None:
    """A column some start-up patch touches is not refused for that reason alone."""
    plan = _plan(tmp_path)
    assert [row.column for row in plan.rows] == ["country"]
    assert W.CURATED_SOURCE == "ancient_nerds"
    assert plan.refused_fields(W.RULE_FIXED_POINT) == []


def test_the_two_startup_patchers_really_guard_their_updates_on_the_lyra_source() -> None:
    """The writability of `country` and `period_start` is read out of the file, not assumed.

    `pipeline/lyra/data_patches.py` is the whole reason both columns are writable: its two `UPDATE`s
    carry `source_id = 'lyra'` in their own `WHERE`, so no `ancient_nerds` row is re-derived. If that
    guard is dropped, both columns become write-and-revert and the writer's fixed-point table is wrong
    - so the guard is the subject of a test rather than a sentence in this one.
    """
    source = (REPO / "pipeline" / "lyra" / "data_patches.py").read_text(encoding="utf-8")
    assert "AND source_id = 'lyra' AND country IS NULL" in source, "fix_countries lost its guard"
    assert "WHERE source_id = 'lyra' AND period_start IS NULL" in source, (
        "backfill_periods lost its guard"
    )


def test_a_period_start_that_is_not_a_year_is_refused_before_the_transaction(
    tmp_path: Path,
) -> None:
    """The column is an integer; a phrase would be cast by the primitive inside a 100-row chunk."""
    plan = _plan(tmp_path, field="period_start", proposed="around 1500 BC")
    assert plan.rows == []
    refusal = plan.refused_fields(W.RULE_SHAPE)[0]
    assert "integer" in refusal.detail


def test_a_country_longer_than_the_column_is_refused_before_the_transaction(tmp_path: Path) -> None:
    """A value the varchar cannot hold is refused in the plan, not by the database mid-chunk."""
    plan = _plan(tmp_path, proposed="U" * 101)
    assert plan.rows == []
    refusal = plan.refused_fields(W.RULE_SHAPE)[0]
    assert "101 characters" in refusal.detail and "100" in refusal.detail


def test_a_value_the_row_already_holds_is_not_a_change(tmp_path: Path) -> None:
    """Writing the stored value would journal a change that is not one."""
    plan = _plan(tmp_path, proposed="Georgia")
    assert plan.rows == []
    refusal = plan.refused_fields(W.RULE_NOT_A_CHANGE)[0]
    assert "Georgia" in refusal.detail


def test_an_answer_the_parser_calls_incomplete_is_refused_with_what_was_missing(
    tmp_path: Path,
) -> None:
    """A `WRONG` without a `PROPOSED:` line is refused by the parser's own reason, not read around."""
    plan = W.load_plan(
        _batch(
            tmp_path,
            cleared={(SITE_A, "country"): _cleared(SITE_A, "country")},
            answers={(SITE_A, "country"): _answer(proposed=None)},
        )
    )
    assert plan.rows == []
    refusal = plan.refused_fields(W.RULE_ANSWER_PROBLEMS)[0]
    assert "PROPOSED" in refusal.detail


def test_a_finder_answer_that_is_not_wrong_has_nothing_to_write(tmp_path: Path) -> None:
    """`CORRECT` with no proposal is a finding, not a value: refused without touching the column."""
    plan = W.load_plan(
        _batch(
            tmp_path,
            cleared={(SITE_A, "country"): _cleared(SITE_A, "country")},
            answers={(SITE_A, "country"): _answer(proposed=None, verdict="CORRECT", url="")},
        )
    )
    assert plan.rows == []
    assert [refusal.field for refusal in plan.refused_fields(W.RULE_NO_PROPOSAL)] == ["country"]


def test_the_evidence_carries_the_finders_citations_and_the_reviewers_reason(
    tmp_path: Path,
) -> None:
    """The journal's evidence names the cited page's host and the reviewer's own sentence."""
    plan = W.build_plan(
        batch={
            "batch_id": BATCH,
            "pass": "discover",
            "sites": [
                {
                    "site_id": SITE_A,
                    "name": _name(SITE_A),
                    "findings": [SP.finding_row("country", "Georgia")],
                }
            ],
        },
        review={
            "batch_id": BATCH,
            "verdicts": [
                _verdict_row(SITE_A, "country", refuted=False, reason="the page is about this site")
            ],
        },
        answers=_texts(tmp_path, {(SITE_A, "country"): _answer(proposed="United States")}),
        evidence=_texts(
            tmp_path / "evidence", {(SITE_A, F.FEATURE_ENWIKI): _enwiki_page(QUOTE)}
        ),
        fetch_failures={},
    )
    evidence = plan.rows[0].evidence
    assert evidence[0]["url"] == PAGE and evidence[0]["host"] == "en.wikipedia.org"
    assert evidence[0]["quote"] == QUOTE
    assert evidence[-1]["source"] == "reviewer"
    assert evidence[-1]["quote"] == "the page is about this site"


# ── the citation check (W7, 2026-09-22) ────────────────────────────────────────────────────────
#
# Before this check the writer never ran the finder's own citation rule, and 44 of the 994 rows in
# production carry a quote their batch's evidence does not contain (AUDIT_LOG.md, 2026-09-22). Each
# test below fails when `_row_for` stops calling `discover_stage.source_problems`.


def test_a_quote_the_cited_page_does_not_carry_is_refused_as_a_citation_failure(
    tmp_path: Path,
) -> None:
    """The reviewer cleared it, but the sentence is not on the page the finder was shown."""
    plan = W.load_plan(
        _cleared_batch(tmp_path, pages={SITE_A: _enwiki_page("A page about something else.")})
    )
    assert plan.rows == []
    refusal = plan.refused_fields(W.RULE_CITATION)[0]
    assert refusal.field == "country"
    assert "quote does not occur" in refusal.detail and QUOTE in refusal.detail


def test_an_honest_quote_passes_through_the_json_escapes_of_the_stored_page(
    tmp_path: Path,
) -> None:
    """The stored enwiki page is API JSON (`\\u00c1`, `\\n`); a quote of what it says still passes."""
    page = _enwiki_page("The fort at Ávila\nwas built in 1500 BC. It stands.")
    assert "\\u00c1vila\\nwas" in page  # the file really carries the escapes the model reads through
    batch_dir = _batch(
        tmp_path,
        cleared={(SITE_A, "country"): _cleared(SITE_A, "country")},
        answers={
            (SITE_A, "country"): _answer(
                proposed="Spain", quote="The fort at Ávila was built in 1500 BC."
            )
        },
        pages={SITE_A: page},
    )
    plan = W.load_plan(batch_dir)
    assert [(row.column, row.new_value) for row in plan.rows] == [("country", "Spain")]
    assert plan.refused_fields(W.RULE_CITATION) == []


def test_a_citation_of_a_page_the_batch_never_fetched_is_refused(tmp_path: Path) -> None:
    """A URL that is not one of the site's targets cannot be checked, so it cannot be written."""
    plan = W.load_plan(
        _batch(
            tmp_path,
            cleared={(SITE_A, "country"): _cleared(SITE_A, "country")},
            answers={
                (SITE_A, "country"): _answer(
                    proposed="United States", url="https://example.org/elsewhere"
                )
            },
        )
    )
    assert plan.rows == []
    detail = plan.refused_fields(W.RULE_CITATION)[0].detail
    assert "not fetched by this run: https://example.org/elsewhere" in detail


def test_a_citation_is_checked_against_its_own_sites_pages_not_a_neighbours(
    tmp_path: Path,
) -> None:
    """Site A quoting site B's page is refused: the pages are read per site, not per batch."""
    batch_dir = _batch(
        tmp_path,
        sites=(SITE_A, SITE_B),
        cleared={
            (SITE_A, "country"): _cleared(SITE_A, "country"),
            (SITE_B, "country"): _cleared(SITE_B, "country"),
        },
        answers={
            (SITE_A, "country"): _answer(proposed="United States", url=_page(SITE_B)),
            (SITE_B, "country"): _answer(proposed="United States", url=_page(SITE_B)),
        },
    )
    plan = W.load_plan(batch_dir)
    assert [row.site_id for row in plan.rows] == [SITE_B]
    assert [refusal.site_id for refusal in plan.refused_fields(W.RULE_CITATION)] == [SITE_A]


def test_a_cited_page_whose_fetch_failed_is_not_a_page_a_quote_can_come_from(
    tmp_path: Path,
) -> None:
    """The fetch report says the page was never read: a quote from it is refused, not trusted."""
    batch_dir = _cleared_batch(tmp_path)
    F.EvidenceStore(batch_dir / W.EVIDENCE_DIR).path_for(SITE_A, F.FEATURE_ENWIKI).unlink()
    (batch_dir / W.FETCH_REPORT_FILE).write_text(
        json.dumps(
            {
                "sites": [
                    {
                        "site_id": SITE_A,
                        "outcomes": [
                            {"feature": F.FEATURE_ENWIKI, "failure": "HTTP 404 (1 request(s))"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    plan = W.load_plan(batch_dir)
    assert plan.rows == []
    assert "was not fetched by this run" in plan.refused_fields(W.RULE_CITATION)[0].detail


def test_evidence_missing_with_nothing_recorded_about_it_stops_the_plan(tmp_path: Path) -> None:
    """A hole in the record is not one row's property: the batch is refused whole, loudly."""
    batch_dir = _cleared_batch(tmp_path)
    F.EvidenceStore(batch_dir / W.EVIDENCE_DIR).path_for(SITE_A, F.FEATURE_ENWIKI).unlink()
    with pytest.raises(W.MS.EvidenceUnusable, match="fetch report records no failure"):
        W.load_plan(batch_dir)


def _texts(tmp_path: Path, texts: dict[tuple[str, str], str]) -> F.EvidenceStore:
    """A real answers store holding the given texts, so the path encoding is the real one.

    `build_plan` reads through `fetch_stage.EvidenceStore`, and its `<site>%2F<field>.txt` naming is
    part of what the writer depends on; a stand-in would make that naming a second spelling.
    """
    store = F.EvidenceStore(tmp_path / "answers")
    for (site_id, field), text in texts.items():
        store.write(site_id=site_id, feature=field, body=text.encode("utf-8"))
    return store


def test_the_change_key_is_a_digest_of_the_transition_not_of_the_row() -> None:
    """`old -> new` and `new -> old` are two transitions and must not share a key."""
    there = W.change_key(
        site_id=SITE_A,
        table="unified_sites",
        column="country",
        old_value="Georgia",
        new_value="United States",
        test_id="P3/country",
    )
    back = W.change_key(
        site_id=SITE_A,
        table="unified_sites",
        column="country",
        old_value="United States",
        new_value="Georgia",
        test_id="P3/country",
    )
    assert there.startswith("phase3:") and len(there) == len("phase3:") + 64
    assert there != back


def test_the_read_statement_names_the_row_its_column_and_refuses_an_unwritable_one() -> None:
    """The read splices the column into the statement, so it refuses a column it may not read."""
    sql = W.stored_values_sql(column="country", site_ids=[SITE_A, SITE_B])
    assert "u.country AS value" in sql and "AS source_id" in sql
    assert SITE_A in sql and SITE_B in sql
    with pytest.raises(W.WriteRefused, match="not writable"):
        W.stored_values_sql(column="name_normalized", site_ids=[SITE_A])


def test_a_plan_side_row_that_is_not_a_real_change_is_refused() -> None:
    """`validate_rows` mirrors the transaction's guards, so a corrupted plan never renders."""
    good = _row(SITE_A, "country", "United States")
    W.validate_rows([good])
    with pytest.raises(W.WriteRefused, match="not a change"):
        W.validate_rows([_row(SITE_A, "country", "Georgia")])
    with pytest.raises(W.WriteRefused, match="appears twice"):
        W.validate_rows([good, _row(SITE_A, "country", "elsewhere")])
    with pytest.raises(W.WriteRefused, match="is not a UUID"):
        W.validate_rows([_row("not-a-uuid", "country", "United States")])


# ── the chunks ───────────────────────────────────────────────────────────────────────────────


def test_the_default_step_is_the_owners_hundred_rows() -> None:
    """`--chunk-size` defaults to 100 rows and `--apply` defaults to off."""
    args = W.build_parser().parse_args(["--batch-dir", "somewhere"])
    assert args.chunk_size == W.DEFAULT_CHUNK_SIZE == 100
    assert args.apply is False
    assert args.batch_dir == "somewhere"


def test_chunks_cut_the_plan_in_its_own_order_and_share_the_batch_id() -> None:
    """Five rows in steps of two: [2, 2, 1], in the plan's own order, one batch id."""
    rows = [
        _row(f"{index:08d}-1111-4111-8111-111111111111", "country", f"land{index}")
        for index in range(5)
    ]
    plan = W.WritePlan(batch_id=BATCH, pass_name="discover", rows=rows)
    chunks = W.chunks_for(plan, chunk_size=2)
    assert [len(chunk.rows) for chunk in chunks] == [2, 2, 1]
    assert [row.site_id for chunk in chunks for row in chunk.rows] == [row.site_id for row in rows]
    assert [chunk.label for chunk in chunks] == ["chunk-0001", "chunk-0002", "chunk-0003"]
    assert {chunk.batch_id for chunk in chunks} == {BATCH}


def test_a_chunk_size_below_one_is_refused() -> None:
    """Zero would be an endless series of empty chunks; the plan refuses it instead."""
    plan = W.WritePlan(batch_id=BATCH, pass_name="discover", rows=[])
    with pytest.raises(W.WriteRefused, match="at least one row"):
        W.chunks_for(plan, chunk_size=0)


def test_an_empty_plan_yields_no_chunk() -> None:
    """ "Nothing to write" must not look like a chunk that wrote nothing."""
    assert W.chunks_for(W.WritePlan(batch_id=BATCH, pass_name="discover", rows=[])) == []


def test_every_chunk_carries_a_digest_over_its_own_rows() -> None:
    """Two chunks of one plan have two digests, and a changed row changes its chunk's."""
    rows = [
        _row(f"{index:08d}-1111-4111-8111-111111111111", "country", f"land{index}")
        for index in range(2)
    ]
    plan = W.WritePlan(batch_id=BATCH, pass_name="discover", rows=rows)
    chunks = W.chunks_for(plan, chunk_size=1)
    assert chunks[0].digest != chunks[1].digest
    assert chunks[0].digest == W.plan_digest(chunks[0].rows)
    assert W.plan_digest([_row(SITE_A, "country", "elsewhere")]) != W.plan_digest(
        [_row(SITE_A, "country", "land0")]
    )


def test_the_run_stamp_names_the_batch_and_the_chunk_and_the_reversal_gets_its_own(
    tmp_path: Path,
) -> None:
    """No clock: the same chunk renders the same stamp on every run, its undo its own."""
    chunk = W.chunks_for(_plan(tmp_path))[0]
    assert chunk.stamp == "phase3:batch-0001:chunk-0001"
    assert chunk.rollback_stamp == chunk.stamp + W.ROLLBACK_KEY_SUFFIX
    assert chunk.rollback_stamp != chunk.stamp


# ── the rendered statements ──────────────────────────────────────────────────────────────────


def test_the_write_statement_ends_in_commit_and_the_reversal_in_rollback(tmp_path: Path) -> None:
    """The reversal is rehearsed in a transaction that is rolled back, never kept."""
    chunk, apply_sql, rollback_sql = _rendered(tmp_path)
    assert "\nCOMMIT;\n" in apply_sql
    assert "\nROLLBACK;\n" in rollback_sql
    assert "\nCOMMIT;" not in rollback_sql
    assert f"'{chunk.rollback_stamp}'" in rollback_sql
    assert f"'{chunk.stamp}'" in apply_sql


def test_both_statements_set_on_error_stop(tmp_path: Path) -> None:
    """Without it psql walks past a failed statement and commits an empty transaction."""
    _, apply_sql, rollback_sql = _rendered(tmp_path)
    assert "\\set ON_ERROR_STOP on" in apply_sql
    assert "\\set ON_ERROR_STOP on" in rollback_sql
    assert "-v ON_ERROR_STOP=1" in W.PSQL
    assert W.PSQL_ROWS.endswith("-t -A")


def test_the_loop_calls_the_primitive_with_the_twelve_arguments_in_order(tmp_path: Path) -> None:
    """The order of `0018`'s signature is the order in the statement, argument for argument."""
    chunk, apply_sql, _ = _rendered(tmp_path)
    call = re.search(
        r"apply_remediation_change\(\n(?P<args>.*?)\n\s*END LOOP", apply_sql, re.DOTALL
    )
    assert call is not None, "the write statement does not call the primitive"
    arguments = [line.strip() for line in call.group("args").splitlines() if line.strip()]
    assert arguments == [
        "'unified_sites', r.column_name, r.pk_column, r.pk,",
        "r.old_value, r.new_value,",
        f"r.test_id, '{chunk.stamp}', r.change_key, 'authoritative',",
        "r.evidence, r.site_id);",
    ]


def test_the_write_guard_keeps_the_write_inside_the_curated_source(tmp_path: Path) -> None:
    """The statement refuses a row that is not a curated site, naming the source as an argument."""
    _, apply_sql, _ = _rendered(tmp_path)
    assert "u.source_id <> 'ancient_nerds';" in apply_sql
    assert "'phase3 write: % planned row(s) are not % sites', bad, ancient_nerds;" in apply_sql


def test_the_write_guard_refuses_a_value_that_is_not_a_change(tmp_path: Path) -> None:
    """An empty or unchanged value never reaches the loop: the allowlist and the test are in it."""
    _, apply_sql, _ = _rendered(tmp_path)
    assert "p.pk_column <> 'id'" in apply_sql
    assert "p.column_name NOT IN ('country', 'period_start', 'site_type')" in apply_sql
    assert "p.new_value = '' OR p.new_value IS NOT DISTINCT FROM p.old_value;" in apply_sql
    assert "IF moved <> expected THEN" in apply_sql
    assert "expected INTEGER := 1;" in apply_sql


def test_every_writable_column_has_a_comparison_in_the_guards(tmp_path: Path) -> None:
    """A column without a comparison would pass guard 3 for that column vacuously."""
    _, apply_sql, _ = _rendered(tmp_path)
    assert set(W.COLUMN_COMPARE) == set(W.WRITABLE_COLUMNS)
    assert set(W.WRITABLE_COLUMNS) == {"country", "period_start", "site_type"}
    for column in W.WRITABLE_COLUMNS:
        assert f"p.column_name = '{column}'" in apply_sql
    assert "u.period_start IS DISTINCT FROM p.old_value::integer" in apply_sql
    assert "u.period_start IS DISTINCT FROM p.new_value::integer" in apply_sql


def test_the_journal_invariant_covers_both_directions(tmp_path: Path) -> None:
    """Every planned row has its journal row, and this run stamp journals nothing outside the plan."""
    _, apply_sql, _ = _rendered(tmp_path)
    assert "WHERE l.id IS NULL" in apply_sql
    assert "NOT EXISTS (SELECT 1 FROM _phase3_plan p WHERE p.change_key = l.change_key)" in (
        apply_sql
    )
    assert "l.new_value IS DISTINCT FROM p.new_value" in apply_sql
    assert "l.old_value IS DISTINCT FROM p.old_value" in apply_sql


def test_the_reversal_carries_the_values_swapped_and_its_own_change_key(tmp_path: Path) -> None:
    """The undo is the other transition: values swapped, key suffixed, same test id."""
    chunk, _, rollback_sql = _rendered(tmp_path)
    insert = [match.groupdict() for match in ROW_RE.finditer(rollback_sql)]
    assert len(insert) == 1
    assert _unquote(insert[0]["old"]) == "United States"
    assert _unquote(insert[0]["new"]) == "Georgia"
    assert insert[0]["key"] == chunk.rows[0].change_key + W.ROLLBACK_KEY_SUFFIX
    assert insert[0]["test_id"] == "P3/country"


def test_the_plan_file_is_written_line_by_line_and_the_refusals_beside_it(tmp_path: Path) -> None:
    """`PLAN.jsonl` holds the rows as JSON, `REFUSED.jsonl` every field the plan did not write."""
    plan, out = _one_row(tmp_path)
    chunks = W.chunks_for(plan)
    W.write_plan_files(out, plan, chunks=chunks)
    assert [
        json.loads(line) for line in (out / W.PLAN_FILE).read_text(encoding="utf-8").splitlines()
    ] == [plan.rows[0].to_dict()]
    refusals = [
        json.loads(line) for line in (out / W.REFUSED_FILE).read_text(encoding="utf-8").splitlines()
    ]
    assert len(refusals) == 4  # the four fields of this site that were not written
    assert {refusal["rule"] for refusal in refusals} == {W.RULE_REVIEWER}
    for chunk in chunks:
        assert (out / W.CHUNKS_DIR / chunk.label / W.APPLY_FILE).exists()
        assert (out / W.CHUNKS_DIR / chunk.label / W.ROLLBACK_FILE).exists()


# ── the apply path ───────────────────────────────────────────────────────────────────────────


def test_the_apply_refuses_a_statement_that_was_generated_from_other_rows(tmp_path: Path) -> None:
    """The digest pin is the tie between `APPLY.sql` and the plan it is run for.

    A `chunks/` directory survives a re-render, and a plan can grow a row between the render and the
    apply. The file then names the rows it was generated from - the older, smaller plan - and running
    it would write a plan nobody reviewed.
    """
    plan, out, chunk = _ready(tmp_path)
    directory = out / W.CHUNKS_DIR / chunk.label
    assert (
        W.assert_pinned(
            (directory / W.APPLY_FILE).read_text(encoding="utf-8"), chunk.rows, what="apply"
        )
        == chunk.digest
    )

    grown = W.Chunk(
        batch_id=chunk.batch_id,
        index=chunk.index,
        rows=(chunk.rows[0], _row(SITE_B, "country", "United States")),
    )
    with pytest.raises(W.WriteRefused, match="generated from different rows"):
        W.apply_chunk(grown, out=out, run_sql_runner=FakePsql(_current(plan)), host="a-host")

    stale = (directory / W.APPLY_FILE).read_text(encoding="utf-8").replace(chunk.digest, "0" * 64)
    (directory / W.APPLY_FILE).write_text(stale, encoding="utf-8", newline="\n")
    with pytest.raises(W.WriteRefused, match="pinned to plan 0000"):
        W.apply_chunk(chunk, out=out, run_sql_runner=FakePsql(_current(plan)), host="a-host")


def test_the_apply_refuses_when_the_statements_were_never_rendered(tmp_path: Path) -> None:
    """Nothing is sent when the chunk's files are not there: render the plan, then apply it."""
    plan, out = _one_row(tmp_path)
    fake = FakePsql(_current(plan))
    with pytest.raises(W.WriteRefused, match="render the plan before applying"):
        W.apply_chunk(W.chunks_for(plan)[0], out=out, run_sql_runner=fake, host="a-host")
    assert fake.sent == []


def test_a_row_that_moved_since_the_snapshot_is_recorded_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    """The pre-flight drops a moved row, records what it holds now, and sends nothing."""
    plan, out, chunk = _ready(tmp_path)
    fake = FakePsql({(SITE_A, "country"): "Abkhazia"})
    outcome = W.apply_chunk(chunk, out=out, run_sql_runner=fake, host="a-host")

    assert outcome.written == 0 and outcome.preflight_held == 0
    assert fake.transactions == []
    reason = outcome.not_held[0]
    assert reason.rule == W.RULE_MATCHED_0 and reason.site_id == SITE_A
    assert "'Abkhazia'" in reason.detail and "'Georgia'" in reason.detail
    assert outcome.skipped is not None and "1 of 1" in outcome.skipped
    assert fake.rows[(SITE_A, "country")] == "Abkhazia"
    assert fake.journal == []


def test_a_site_that_left_the_curated_source_is_not_written(tmp_path: Path) -> None:
    """A row whose `source_id` changed is a matched-0 row too, and says which source it has."""
    plan, out, chunk = _ready(tmp_path)
    fake = FakePsql(_current(plan), sources={SITE_A: "lyra"})
    outcome = W.apply_chunk(chunk, out=out, run_sql_runner=fake, host="a-host")
    assert outcome.written == 0
    assert "'lyra'" in outcome.not_held[0].detail


def test_a_pre_flight_that_agrees_sends_the_read_first_and_then_the_write(tmp_path: Path) -> None:
    """The read comes first, the host the run was told to use is the one it is sent to."""
    plan, out, chunk = _ready(tmp_path)
    fake = FakePsql(_current(plan))
    outcome = W.apply_chunk(chunk, out=out, run_sql_runner=fake, host="a-host")

    assert fake.sent[0].startswith(VALUE_READ)
    assert fake.sent[1].startswith("-- Generated by")
    assert set(fake.hosts) == {"a-host"}
    assert outcome.preflight_held == 1 and outcome.written == 1
    assert fake.rows[(SITE_A, "country")] == "United States"
    assert [entry["run_stamp"] for entry in fake.journal] == [chunk.stamp]
    assert fake.journal[0]["old_value"] == "Georgia"
    assert fake.journal[0]["new_value"] == "United States"
    assert fake.journal[0]["test_id"] == "P3/country"
    assert outcome.read_back is not None and outcome.read_back.ok
    assert outcome.inverse is not None and outcome.inverse.ok
    assert outcome.rollback_rows == 0


def test_the_reversal_leaves_the_write_exactly_as_it_was(tmp_path: Path) -> None:
    """The rehearsal is rolled back: the data stays written and its whole journal line stays."""
    plan, out, chunk = _ready(tmp_path)
    fake = FakePsql(_current(plan))
    W.apply_chunk(chunk, out=out, run_sql_runner=fake, host="a-host")

    assert fake.rows[(SITE_A, "country")] == "United States"
    assert [entry["run_stamp"] for entry in fake.journal] == [chunk.stamp]
    assert chunk.rollback_stamp != chunk.stamp


def test_a_value_the_database_kept_differently_is_a_stop(tmp_path: Path) -> None:
    """The read-back compares the value, not the number of rows: an override stops the run."""
    plan, out, chunk = _ready(tmp_path)
    fake = FakePsql(_current(plan), sabotage={(SITE_A, "country"): "Sakartvelo"})
    with pytest.raises(W.ReadBackFailed) as excinfo:
        W.apply_chunk(chunk, out=out, run_sql_runner=fake, host="a-host")
    message = str(excinfo.value)
    assert SITE_A in message and "'Sakartvelo'" in message and "'United States'" in message
    assert "Stopping before" in message


def test_a_journal_row_outside_the_plan_is_a_stop(tmp_path: Path) -> None:
    """A statement that journalled more than the plan accounts for cannot pass, data or no data."""
    plan, out, chunk = _ready(tmp_path)
    fake = FakePsql(
        _current(plan),
        extra_journal=(
            {
                "row_pk": SITE_B,
                "table_name": "unified_sites",
                "column_name": "country",
                "change_key": "phase3:" + "9" * 64,
                "old_value": None,
                "new_value": "elsewhere",
                "test_id": "P3/country",
                "run_stamp": chunk.stamp,
            },
        ),
    )
    with pytest.raises(W.ReadBackFailed, match="2 journal row"):
        W.apply_chunk(chunk, out=out, run_sql_runner=fake, host="a-host")


def test_a_reversal_that_is_kept_is_a_stop(tmp_path: Path) -> None:
    """A reversal that commits moves the data back, so the read-back after it stops the run."""
    plan, out, chunk = _ready(tmp_path)
    directory = out / W.CHUNKS_DIR / chunk.label
    kept = (
        (directory / W.ROLLBACK_FILE)
        .read_text(encoding="utf-8")
        .replace("\nROLLBACK;\n", "\nCOMMIT;\n")
    )
    (directory / W.ROLLBACK_FILE).write_text(kept, encoding="utf-8", newline="\n")
    fake = FakePsql(_current(plan))
    with pytest.raises(W.InverseFailed) as excinfo:
        W.apply_chunk(chunk, out=out, run_sql_runner=fake, host="a-host")
    assert "did not leave the write exactly as it was" in str(excinfo.value)
    assert fake.rows[(SITE_A, "country")] == "Georgia"


# ── the report and the CLI ───────────────────────────────────────────────────────────────────


def test_the_report_counts_the_refusals_by_rule_and_names_the_fixed_points(tmp_path: Path) -> None:
    """Every refusal is a number with a cause, and the fixed-point ones carry site and field."""
    plan = W.load_plan(
        _batch(
            tmp_path,
            cleared={
                (SITE_A, "site_type"): _cleared(SITE_A, "site_type"),
                (SITE_A, "description"): _cleared(SITE_A, "description"),
            },
            answers={
                (SITE_A, "site_type"): _answer(proposed="settlement"),
                (SITE_A, "description"): _answer(proposed="a better description"),
            },
        )
    )
    payload = W.report(plan, chunks=[], outcomes=[], chunk_size=100, execute=False)
    assert payload["rows_planned"] == 0 and payload["dry_run"] is True
    assert payload["journal_rows_added"] is None
    assert payload["refused_by_rule"] == {
        W.RULE_FIXED_POINT: 1,
        W.RULE_REPORT_ONLY: 1,
        W.RULE_REVIEWER: 3,
    }
    assert payload["refused_by_fixed_point"] == 1
    detail = payload["refused_by_fixed_point_detail"][0]
    assert (detail["site_id"], detail["field"], detail["rule"]) == (
        SITE_A,
        "site_type",
        W.RULE_FIXED_POINT,
    )
    assert payload["not_cleared_by_the_reviewer"] == 3


def test_a_dry_run_sends_nothing_to_the_database(tmp_path: Path, monkeypatch: Any) -> None:
    """Without `--apply` the seam is never called: the plan is rendered, not run."""
    batch_dir = _cleared_batch(tmp_path)
    calls: list[str] = []

    def _boom(sql: str, *, host: str) -> str:
        calls.append(sql)
        raise AssertionError("a dry run sent a statement to the database")

    monkeypatch.setattr(W, "run_sql", _boom)
    out = tmp_path / "writes"
    assert W.main(["--batch-dir", str(batch_dir), "--out", str(out)]) == 0
    assert calls == []
    payload = json.loads((out / W.REPORT_FILE).read_text(encoding="utf-8"))
    assert payload["dry_run"] is True and payload["rows_written"] == 0
    assert payload["rows_planned"] == 1 and payload["chunks"] == 1
    assert (out / W.CHUNKS_DIR / "chunk-0001" / W.APPLY_FILE).exists()


def test_main_applies_through_the_seam_and_reports_the_numbers(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """The whole CLI path with the fake in place: pre-flight, write, read back, invert, report."""
    batch_dir = _cleared_batch(tmp_path)
    fake = FakePsql({(SITE_A, "country"): "Georgia"})
    monkeypatch.setattr(W, "run_sql", fake)
    out = tmp_path / "writes"
    assert W.main(["--batch-dir", str(batch_dir), "--out", str(out), "--apply", "--host", "h"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is False
    assert payload["rows_planned"] == 1 and payload["rows_written"] == 1
    assert payload["journal_rows_added"] == 1
    assert payload["chunk_results"][0]["rows_preflight_held"] == 1
    assert payload == json.loads((out / W.REPORT_FILE).read_text(encoding="utf-8"))
    assert fake.rows[(SITE_A, "country")] == "United States"
    assert [entry["run_stamp"] for entry in fake.journal] == ["phase3:batch-0001:chunk-0001"]
    assert fake.hosts == ["h"] * len(fake.hosts)


def test_main_refuses_a_chunk_number_the_plan_does_not_have(tmp_path: Path) -> None:
    """`--chunk 7` on a one-chunk plan is refused rather than silently running nothing."""
    batch_dir = _cleared_batch(tmp_path)
    with pytest.raises(W.WriteRefused, match="no such chunk"):
        W.main(["--batch-dir", str(batch_dir), "--out", str(tmp_path / "w"), "--chunk", "7"])


def test_the_plan_refuses_a_review_that_names_another_batch(tmp_path: Path) -> None:
    """Joining a review to another batch's input would apply verdicts to the wrong findings."""
    batch_dir = _cleared_batch(tmp_path)
    review = json.loads((batch_dir / W.REVIEW_FILE).read_text(encoding="utf-8"))
    review["batch_id"] = "batch-0002"
    (batch_dir / W.REVIEW_FILE).write_text(json.dumps(review), encoding="utf-8", newline="\n")
    with pytest.raises(InputError, match="refusing to join two batches"):
        W.load_plan(batch_dir)


def test_the_plan_refuses_a_batch_that_is_not_the_discover_pass(tmp_path: Path) -> None:
    """The per-field verdicts belong to the discover pass; another pass has another shape."""
    batch_dir = _cleared_batch(tmp_path)
    batch = json.loads((batch_dir / W.INPUT_FILE).read_text(encoding="utf-8"))
    batch["pass"] = "worklist"  # noqa: S105 - a batch marker, not a credential
    (batch_dir / W.INPUT_FILE).write_text(json.dumps(batch), encoding="utf-8", newline="\n")
    with pytest.raises(InputError, match="pass='worklist'"):
        W.load_plan(batch_dir)


def test_reading_a_missing_batch_directory_says_which_file_is_missing(tmp_path: Path) -> None:
    """A path that is not a batch is refused by name, not with a KeyError."""
    with pytest.raises(W.WriteRefused, match="input.json does not exist"):
        W.load_plan(tmp_path / "nowhere")


def test_a_field_whose_finder_call_was_a_hole_is_refused_and_no_row_is_planned(
    tmp_path: Path,
) -> None:
    """A hole has no answer text, so there is no value to write - a cleared hole is still a refusal.

    The batch is the shape `batch-0143` was left in: the finder's `model.json` names the `country`
    call as a `FailedCall`, `answers/` holds no `country` file, and the review cleared the field
    anyway. The writer may not build a row here - the value would be one nobody proposed. The
    review's own `applies` boolean is not consulted either (`rebuilt_verdict`), so a file that
    merely claims the verdict clears cannot smuggle the hole through.
    """
    batch_dir = _batch(
        tmp_path,
        cleared={(SITE_A, "country"): _cleared(SITE_A, "country")},
    )
    (batch_dir / "model.json").write_text(
        json.dumps(
            {
                "batch_id": BATCH,
                "failures": [
                    {"site_id": SITE_A, "field": "country", "reason": "the stream carries no text"}
                ],
                "judgements": [],
                "totals": {"calls": 1},
            }
        ),
        encoding="utf-8",
    )

    plan = W.load_plan(batch_dir)

    assert plan.rows == []
    refused = plan.refused_fields(W.RULE_NO_ANSWER)
    assert [(r.site_id, r.field) for r in refused] == [(SITE_A, "country")]
    assert "does not exist" in refused[0].detail
