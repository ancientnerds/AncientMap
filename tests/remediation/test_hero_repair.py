"""Does the hero repair move the flag only where the evidence allows it?

The repair is five thousand conditional UPDATEs against production, so the interesting
mistakes are not exceptions but a plan that is *wrong and happy*: a replacement that is an
upscale (a bigger `og:image` tag over the same real detail), a suspect gallery image promoted
to hero, a tier that could not be computed read as "clear", a site left with two heroes or
none. Each of those has a test that fails with a named reason rather than a row count.

No snapshot, no cache, no database: `build_plan` is a pure function of four arguments, and the
SQL renderer is checked as text, because what must be true of the production write is exactly
what can be read off the statement it emits (the old value in the `WHERE`, one transaction,
a journal row per change, no DELETE).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from hero_repair import apply as A  # noqa: E402
from hero_repair import plan as P  # noqa: E402

SITE_A = "11111111-1111-1111-1111-111111111111"
SITE_B = "22222222-2222-2222-2222-222222222222"


def image(**over: object) -> dict[str, object]:
    """A snapshot `wiki_images` row, small enough to reason about by hand."""
    row: dict[str, object] = {
        "id": 1,
        "site_id": SITE_A,
        "filename": "a.webp",
        "original_url": "https://upload.wikimedia.org/wikipedia/commons/4/4f/A.jpg",
        "commons_page_url": "https://commons.wikimedia.org/wiki/File%3AA.jpg",
        "width": 1600,
        "height": 1067,
        "is_hero": False,
        "is_lead": False,
        "is_excluded": False,
        "sort_order": 0,
    }
    row.update(over)
    return row


def truth(width: int = 3417, height: int = 2278, status: str = "ok") -> dict[str, object]:
    return {"status": status, "canonical": "A.jpg", "width": width, "height": height,
            "bytes": 1_000_000, "url": "https://upload.wikimedia.org/..."}


def site(site_id: str = SITE_A, name: str = "Site A", source: str = P.CURATED_SOURCE) -> dict:
    return {"id": site_id, "name": name, "source_id": source}


# ------------------------------------------------------------------ the rule, line by line
def test_the_borrowed_minimum_matches_the_gateway_that_generated_the_files() -> None:
    """1600x900 is `GALLERY_WIDTH` and T09's hero minimum; a silent change here would
    relocate the whole repair without failing anything else."""
    assert (P.HERO_MIN_WIDTH, P.HERO_MIN_HEIGHT) == (1600, 900)


def test_a_tier_that_could_not_be_computed_is_never_clear() -> None:
    verdict = P.candidate_verdict(image(), None, truth())
    assert (verdict.eligible, verdict.reason) == (False, "tier-unknown")


@pytest.mark.parametrize("tier", ["A", "B"])
def test_a_suspect_gallery_image_never_becomes_the_hero(tier: str) -> None:
    verdict = P.candidate_verdict(image(), tier, truth())
    assert not verdict.eligible
    assert verdict.reason == f"tier-{tier}-suspect"


def test_the_suspect_tier_that_actually_occurs_is_refused_the_same_way() -> None:
    """Tier B is the one that matters in this corpus: 9,501 rows carry it, against 3,858
    tier-A and no tier that cannot be computed at all (`load_tiers` refuses those)."""
    assert P.candidate_verdict(image(), "B", truth()).reason == "tier-B-suspect"


@pytest.mark.parametrize("tier", ["C", "D"])
def test_grey_and_clear_are_both_accepted(tier: str) -> None:
    assert P.candidate_verdict(image(), tier, truth()).eligible


def test_a_local_file_larger_than_its_original_is_not_a_hero() -> None:
    """The upscale guard, stated as what the plan claims: the served 1600 px file must not
    exceed the original the download produced it from. In this corpus the guard never fires
    (measured 2026-09-20: of the 31,878 already-1600 px rows whose original is >= 1600x900,
    none exceeds its original - all 10,977 upscales have an original that is itself below the
    hero minimum, so `original-too-small` names them), and that is exactly why it is compared
    rather than asserted in prose."""
    verdict = P.candidate_verdict(image(width=1600, height=1067), "D", truth(1600, 900))
    assert (verdict.eligible, verdict.reason) == (False, "local-file-is-an-upscale")


def test_an_original_below_the_hero_minimum_is_refused() -> None:
    verdict = P.candidate_verdict(image(width=1600, height=900), "D", truth(1600, 799))
    assert (verdict.eligible, verdict.reason) == (False, "original-too-small")


def test_a_small_stored_file_is_refused_even_when_commons_has_a_large_one() -> None:
    """The other half of "both sources": truth alone would promote an 800 px local file."""
    verdict = P.candidate_verdict(image(width=800, height=533), "D", truth())
    assert (verdict.eligible, verdict.reason) == (False, "local-file-too-small")


@pytest.mark.parametrize(
    "row,reason",
    [
        (image(is_hero=True), "is-the-hero"),
        (image(is_excluded=True), "excluded-from-the-gallery"),
        (image(width=None, height=None), "stored-dims-missing"),
    ],
)
def test_rows_outside_the_gallery_are_refused_with_their_own_reason(row: dict, reason: str) -> None:
    verdict = P.candidate_verdict(row, "D", truth())
    assert (verdict.eligible, verdict.reason) == (False, reason)


def test_a_missing_commons_answer_is_not_a_pass() -> None:
    verdict = P.candidate_verdict(image(), "D", None)
    assert (verdict.eligible, verdict.reason) == (False, "commons-unknown-to-this-cache")
    verdict = P.candidate_verdict(image(), "D", truth(status="missing"))
    assert (verdict.eligible, verdict.reason) == (False, "commons-missing")


def test_a_row_whose_local_size_already_qualifies_needs_no_repair() -> None:
    assert P.is_hero_ready(image(width=1600, height=1067, is_hero=True))
    assert not P.is_hero_ready(image(width=800, height=600, is_hero=True))


def test_the_clearest_candidate_wins_before_the_largest() -> None:
    """Tier first: a clear 1600 px file beats a grey 4000 px one, because the audit that
    follows throws tier B/C away first and the whole point is not to undo this repair."""
    clear = ({"id": 2, "_tier": "D"}, truth(2000, 1300))
    grey = ({"id": 3, "_tier": "C"}, truth(6000, 4000))
    assert P.rank_key(clear) < P.rank_key(grey)


def test_within_one_tier_the_larger_true_original_wins() -> None:
    small = ({"id": 2, "_tier": "D"}, truth(1600, 900))
    big = ({"id": 3, "_tier": "D"}, truth(4000, 3000))
    assert P.rank_key(big) < P.rank_key(small)
    # ... and the image id breaks a tie, so the plan is reproducible
    assert P.rank_key(({"id": 2, "_tier": "D"}, truth(4000, 3000))) < P.rank_key(
        ({"id": 3, "_tier": "D"}, truth(4000, 3000))
    )


# ------------------------------------------------------------------------------ the plan
def build(records_images: dict[str, list[dict]], tiers: dict[int, str], truth_map: dict) -> P.Plan:
    return P.build_plan(
        [site(sid, f"Site {sid[:4]}") for sid in records_images],
        records_images,
        tiers,
        truth_map,
        snapshot_exported_at="2026-09-20T20:20:01+02:00",
    )


def test_a_repair_is_a_pair_demoted_hero_and_promoted_gallery_file() -> None:
    hero = image(id=10, is_hero=True, is_lead=True, width=800, height=533, filename="h.webp")
    cand = image(id=11, width=1600, height=1067, filename="c.webp")
    plan = build({SITE_A: [hero, cand]}, {10: "A", 11: "D"}, {"A.jpg": truth()})

    assert [(r.image_id, r.role, r.old_is_hero, r.new_is_hero) for r in plan.records] == [
        (10, "demote", True, False),
        (11, "promote", False, True),
    ]
    for record in plan.records:
        assert record.condition.startswith(f"id = {record.image_id} AND is_hero = ")
        assert record.evidence and all({"source", "quote"} <= set(e) for e in record.evidence)
    P.check_plan(plan, {SITE_A: [hero, cand]})


def test_a_hero_that_is_already_1600_px_is_left_alone() -> None:
    hero = image(id=10, is_hero=True, width=1600, height=1067)
    cand = image(id=11, width=1600, height=1067)
    plan = build({SITE_A: [hero, cand]}, {10: "A", 11: "D"}, {"A.jpg": truth()})
    assert plan.records == []
    assert plan.sites["already-hero-ready"] == 1


def test_a_site_without_a_hero_is_left_alone_and_named() -> None:
    """Its page already serves a 1600 px gallery file through the is_lead/sort_order
    fallback; planting a flag would change which image it serves for no size reason."""
    cand = image(id=11, width=1600, height=1067)
    plan = build({SITE_A: [cand]}, {11: "D"}, {"A.jpg": truth()})
    assert plan.records == []
    assert plan.sites["sites-without-hero-flag"] == 1
    assert plan.sites["repaired-sites"] == 0
    assert plan.skipped["no-hero-flag"][0]["site_id"] == SITE_A
    assert plan.skipped["no-hero-flag"][0]["eligible_candidates"] == 1


def test_an_upscale_only_site_is_reported_not_repaired() -> None:
    hero = image(id=10, is_hero=True, width=800, height=533)
    cand = image(id=11, width=1600, height=1067)
    plan = build({SITE_A: [hero, cand]}, {10: "A", 11: "D"}, {"A.jpg": truth(1600, 900)})
    assert plan.records == []
    assert plan.sites["plan-rule-candidate-but-stricter-rule-rejected"] == 1
    assert plan.sites["rejected-all-candidates-are-upscales"] == 1
    entry = plan.skipped["no-eligible-candidate"][0]
    assert entry["stored_dims_candidates"] == 1
    assert entry["reasons"] == {"local-file-is-an-upscale": 1}


def test_a_site_whose_only_candidate_has_a_small_original_says_so() -> None:
    """The shape the corpus actually has: a genuine 1600 px local file made from a 1024 px
    original. It stays in the gallery; it does not get to be the LCP image."""
    hero = image(id=10, is_hero=True, width=800, height=533)
    cand = image(id=11, width=1600, height=1067)
    plan = build({SITE_A: [hero, cand]}, {10: "A", 11: "D"}, {"A.jpg": truth(1024, 683)})
    assert plan.records == []
    assert plan.sites["rejected-all-originals-too-small"] == 1
    assert plan.skipped["no-eligible-candidate"][0]["reasons"] == {"original-too-small": 1}


def test_a_site_whose_candidates_are_all_suspect_says_so() -> None:
    hero = image(id=10, is_hero=True, width=800, height=533)
    cand = image(id=11, width=1600, height=1067)
    plan = build({SITE_A: [hero, cand]}, {10: "A", 11: "B"}, {"A.jpg": truth()})
    assert plan.sites["rejected-all-candidates-refused-by-tier"] == 1
    assert plan.sites["rejected-on-census-tier-alone"] == 1
    assert plan.sites["rejected-because-the-stored-size-was-the-only-witness"] == 0
    assert plan.records == []


def test_a_site_rejected_by_the_commons_truth_is_counted_as_such() -> None:
    """The distinction the report needs: here the stored size was the only witness, so
    trusting `wiki_images.width` would have moved the flag (276 sites in the corpus)."""
    hero = image(id=10, is_hero=True, width=800, height=533)
    cand = image(id=11, width=1600, height=1067)
    plan = build({SITE_A: [hero, cand]}, {10: "A", 11: "D"}, {"A.jpg": truth(1024, 683)})
    assert plan.sites["rejected-because-the-stored-size-was-the-only-witness"] == 1
    assert plan.sites["rejected-on-census-tier-alone"] == 0


def test_another_source_is_not_touched_at_all() -> None:
    hero = image(id=10, is_hero=True, width=800, height=533)
    cand = image(id=11, width=1600, height=1067)
    plan = P.build_plan(
        [site(SITE_A, "Foreign", source="list_inscriptions")],
        {SITE_A: [hero, cand]},
        {10: "A", 11: "D"},
        {"A.jpg": truth()},
    )
    assert plan.records == []
    assert plan.sites["sites"] == 0


def test_only_one_hero_per_site_is_required_not_produced() -> None:
    """The invariant is enforced on paper before it is enforced in production: a promotion
    without its demotion would leave the site with two hero rows."""
    hero = image(id=10, is_hero=True, width=800, height=533)
    cand = image(id=11, width=1600, height=1067)
    plan = build({SITE_A: [hero, cand]}, {10: "A", 11: "D"}, {"A.jpg": truth()})
    broken = P.Plan(
        records=[r for r in plan.records if r.role == "promote"],
        counters=plan.counters,
        sites=plan.sites,
        skipped=plan.skipped,
        snapshot_exported_at=plan.snapshot_exported_at,
    )
    with pytest.raises(P.PlanError, match="promoted without exactly one demotion"):
        P.check_plan(broken, {SITE_A: [hero, cand]})


def test_a_row_planned_twice_is_refused() -> None:
    record = P.ChangeRecord(
        image_id=11, site_id=SITE_A, site_name="Site A", role="promote",
        old_is_hero=False, new_is_hero=True, condition="id = 11 AND is_hero = false",
        reason="r",
    )
    plan = P.Plan(
        records=[record, record],
        counters=P.Counter(),
        sites=P.Counter(),
        skipped={},
        snapshot_exported_at=None,
    )
    with pytest.raises(P.PlanError, match="appears twice"):
        P.check_plan(plan, {SITE_A: []})


# --------------------------------------------------------------------------------- inputs
def test_a_tier_beside_the_snapshot_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "findings.jsonl"
    path.write_text(json.dumps({"current_value": {"image_id": 1, "tier": "D"}}) + "\n", encoding="utf-8")
    assert P.load_tiers(path) == {1: "D"}

    path.write_text(json.dumps({"current_value": {"image_id": 1, "tier": "E"}}) + "\n", encoding="utf-8")
    with pytest.raises(P.PlanError, match="unknown tier"):
        P.load_tiers(path)

    path.write_text(json.dumps({"current_value": {"image_id": 1}}) + "\n", encoding="utf-8")
    with pytest.raises(P.PlanError, match="unknown tier None"):
        P.load_tiers(path)


def test_a_missing_tier_artifact_is_not_an_empty_one(tmp_path: Path) -> None:
    with pytest.raises(P.PlanError, match="run the T10 census"):
        P.load_tiers(tmp_path / "nope.jsonl")


def test_a_cache_without_entries_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "commons_imageinfo.json"
    path.write_text(json.dumps({"summary": {"ok": 3}}), encoding="utf-8")
    with pytest.raises(P.PlanError, match="no 'entries' key"):
        P.load_truth(path)


# ------------------------------------------------------------------------------ the write
def records_pair() -> list[P.ChangeRecord]:
    return [
        P.ChangeRecord(
            image_id=10, site_id=SITE_A, site_name="Site A", role="demote",
            old_is_hero=True, new_is_hero=False, condition="id = 10 AND is_hero = true",
            reason="old hero is 800x533", evidence=[{"source": "test", "quote": "10"}],
        ),
        P.ChangeRecord(
            image_id=11, site_id=SITE_A, site_name="Site A", role="promote",
            old_is_hero=False, new_is_hero=True, condition="id = 11 AND is_hero = false",
            reason="1600x1067 local, 3417x2278 on Commons", evidence=[{"source": "test", "quote": "11"}],
        ),
    ]


def test_every_row_goes_through_the_journal_function_with_its_old_value_as_text() -> None:
    """The primitive is the only write path: `apply_remediation_change` does the conditional
    UPDATE and the journal INSERT in one statement. `p_old`/`p_new` are TEXT on purpose - the
    function casts them to the column's own type (migration 0018) -, and a boolean column
    written by hand would be the bypass that diverges the journal from the data."""
    sql = A.render_transaction(records_pair(), site_ids={SITE_A})
    assert "moved := moved + apply_remediation_change(" in sql
    assert "'wiki_images', 'is_hero', 'id', r.image_id::text," in sql
    assert "r.old_value::text, r.new_value::text," in sql
    assert "'T09/hero-not-best'" in sql and "'2026-09-20_remediation'" in sql
    assert "'authoritative'" in sql
    assert "r.evidence, r.site_id);" in sql
    # no hand-written write to the data or the journal anywhere in the file
    assert "UPDATE wiki_images" not in sql
    assert "INSERT INTO remediation_change_log" not in sql


def test_the_statement_is_one_transaction() -> None:
    sql = A.render_transaction(records_pair(), site_ids={SITE_A})
    assert sql.count("BEGIN;") == 1
    assert sql.count("COMMIT;") == 1
    assert "moved <> expected" in sql  # nothing half-applied
    assert "DELETE" not in sql.upper().replace("-- DELETE", "")
    assert "\\set ON_ERROR_STOP on" in sql


def test_the_one_hero_per_site_check_is_not_multiplied_by_the_plan_table() -> None:
    """The plan holds two rows per site. A plain join to `wiki_images` would count each
    remaining hero twice and reject a correct repair; the measured rehearsal of the emitted
    statement failed exactly this way (2026-09-20), which is why the check drives from
    `SELECT DISTINCT site_id`."""
    sql = A.render_transaction(records_pair(), site_ids={SITE_A})
    assert "SELECT s.site_id FROM (SELECT DISTINCT site_id FROM _hero_plan) s" in sql


def test_the_statement_refuses_rows_outside_the_curated_source() -> None:
    sql = A.render_transaction(records_pair(), site_ids={SITE_A})
    assert "u.source_id <> 'ancient_nerds'" in sql
    assert "w.site_id IS DISTINCT FROM p.site_id" in sql


def test_an_empty_plan_is_not_written_as_an_empty_transaction() -> None:
    with pytest.raises(P.PlanError, match="empty transaction"):
        A.render_transaction([], site_ids=set())


def test_the_rollback_reverses_each_row_with_its_journaled_value(tmp_path: Path) -> None:
    plan = build(
        {SITE_A: [image(id=10, is_hero=True, width=800, height=533), image(id=11)]},
        {10: "A", 11: "D"},
        {"A.jpg": truth()},
    )
    path = tmp_path / "ROLLBACK.sql"
    assert P.write_rollback_sql(plan, path) == 2
    sql = path.read_text(encoding="utf-8")
    assert f"run_stamp = '{A.ROLLBACK_RUN_STAMP}'" in sql
    assert A.ROLLBACK_RUN_STAMP != P.RUN_STAMP
    # the forward promotion is reversed: old value true -> new value false on image 11
    assert "(11, '11111111-1111-1111-1111-111111111111', true, false" in sql


def test_the_plan_rows_carry_their_old_value_into_the_temp_table() -> None:
    sql = A.render_transaction(records_pair(), site_ids={SITE_A})
    assert "(10, '11111111-1111-1111-1111-111111111111', true, false" in sql
    assert "(11, '11111111-1111-1111-1111-111111111111', false, true" in sql


def test_the_rehearsal_is_the_same_file_with_commit_replaced_by_rollback() -> None:
    """The rehearsal is only worth anything if it runs the identical guards; a separate
    rehearsal script would approve a statement nobody applies."""
    sql = A.render_transaction(records_pair(), site_ids={SITE_A})
    rehearsal = A.rehearse(sql)
    assert "\nROLLBACK;\n" in rehearsal
    assert "COMMIT;" not in rehearsal
    assert rehearsal.count("apply_remediation_change(") == sql.count("apply_remediation_change(")
    assert "journal rows for this run stamp" in rehearsal
    assert "curated hero rows" in rehearsal
    with pytest.raises(A.PlanError, match="no COMMIT"):
        A.rehearse("BEGIN;\nSELECT 1;\n")


def test_the_primitive_check_asks_for_the_type_safe_body() -> None:
    """The write depends on migration 0018's body. If a database ever holds the 0017 body
    again, `--check-primitive` has to say so before the apply, not after."""
    sql = A.PRIMITIVE_CHECK_SQL
    assert "casts_value_to_column_type" in sql
    assert "stored a different value" in sql
    assert "pg_get_functiondef" in sql


def test_the_plan_round_trips_through_the_jsonl_the_apply_reads(tmp_path: Path) -> None:
    plan = build(
        {SITE_A: [image(id=10, is_hero=True, width=800, height=533), image(id=11)]},
        {10: "A", 11: "D"},
        {"A.jpg": truth()},
    )
    path = tmp_path / "PLAN.jsonl"
    assert P.write_plan_jsonl(plan, path) == 2
    loaded = A.load_records(path)
    assert [r.image_id for r in loaded] == [10, 11]
    assert [r.old_is_hero for r in loaded] == [True, False]
    assert loaded[1].evidence == plan.records[1].evidence


def test_reading_a_missing_plan_is_an_error_not_an_empty_write(tmp_path: Path) -> None:
    with pytest.raises(P.PlanError, match="build the plan first"):
        A.load_records(tmp_path / "PLAN.jsonl")


def test_the_verification_queries_are_read_only() -> None:
    """The post-apply check must not be able to change anything, and it must ask about the
    one invariant the repair promises: a curated site with no hero, or with two."""
    sql = A.VERIFY_SQL.upper()
    for forbidden in ("UPDATE ", "INSERT ", "DELETE ", "ALTER ", "DROP "):
        assert forbidden not in sql
    assert "SITES WITH EXACTLY ONE HERO" in sql
    assert "SITES WITH MORE THAN ONE HERO" in sql
    assert "HEROES OUTSIDE THE CURATED SOURCE" in sql
    assert "SERVED IMAGE IS NARROWER THAN 1600 PX" in sql
