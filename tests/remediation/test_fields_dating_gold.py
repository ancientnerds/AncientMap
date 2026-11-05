"""D70/D71: the dating extractor's gold (`scripts/remediation/fields/dating_gold.py`) and the gates
`plan.py wave` holds a wd5x run to (`_require_gold`, `_require_owner_shown`).

DB-less and offline. What is pinned: who may be gold (a Claude keep or replace that a found quote
stands behind and that the live value still equals - never a rule row, a MiniMax answer, a model-less
WD1 row or an adversarial unclear/reject), the hard stratum apart, the seeded stratified draw with a
disjoint DEV set, the seal (an edited GOLD.jsonl is refused), the frozen code (a changed module or
CONFIG refuses the measurement), measured once, the gate's numbers (0.95, 200 gold, 100 emitted, each
tier and the period-word-only decisions on their own), the next round after a failed one, and the
wave's refusal without a passing verdict of the code as it is, VERIFIED.json and OWNER_SHOWN.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _root in (str(REPO), str(REPO / "scripts" / "remediation")):
    if _root not in sys.path:
        sys.path.insert(0, _root)

from fields import dating as X  # noqa: E402
from fields import dating_gold as G  # noqa: E402
from fields import plan as PLAN  # noqa: E402
from fields import rule as R  # noqa: E402
from mechanical.plan import PlanError  # noqa: E402

CLAUDE = "anthropic/claude-sonnet-5-5 (Claude Code agent)"
MINIMAX = "MiniMax-M3.1-Flash-Preview"
FOUND = [{"source": "https://en.wikipedia.org/wiki/A", "quote": "q", "outcome": "found"}]


def sid(n: int) -> str:
    return f"{n:08d}-0000-4000-8000-000000000000"


def decision(n: int, run: str, verdict: str = "replace", value: Any = "-300", **over: Any) -> dict:
    return {"site_id": sid(n), "field": "period_start", "decision": verdict, "value": value,
            "stored": None, "model": CLAUDE, "answered_by": "field_researcher:b1",
            "quotes": FOUND, "_run": run, **over}  # fmt: skip


def stored(n: int, year: int | None = -300, **over: Any) -> dict:
    return {"site_id": sid(n), "name": f"S{n}", "period_start": year, "scope_status": None,
            "site_type": "Settlement", **over}  # fmt: skip


class TestThePool:
    def test_who_is_gold_and_who_is_hard(self) -> None:
        rows = [stored(n) for n in range(1, 11)] + [stored(11, None)]
        histories = {
            sid(1): [decision(1, "wd3")],
            sid(2): [decision(2, "wd3", model=MINIMAX)],
            sid(3): [decision(3, "wd1", model=None)],
            sid(4): [decision(4, "wd3", answered_by="rule:site_type")],
            sid(5): [decision(5, "wd3", value="-500")],  # the live value moved since
            sid(6): [decision(6, "wd5", adversarial={"verdict": "unclear"})],
            sid(7): [decision(7, "wd5", verdict="unresolved", value=None), decision(7, "wd5-reask")],
            sid(8): [decision(8, "wd5", adversarial={"verdict": "unclear"}, owner={"by": "D69"})],
            sid(9): [decision(9, "wd3", quotes=[{"source": "u", "quote": "q", "outcome": "not found"}])],
            sid(10): [decision(10, "wd4", verdict="keep", value=None, stored=-300)],
            sid(11): [decision(11, "wd3")],  # undated now
        }  # fmt: skip
        pool, hard = G.gold_pool(rows, histories)
        assert [r["site_id"] for r in pool] == [sid(1), sid(10)]
        assert [r["site_id"] for r in hard] == [sid(7), sid(8)]
        assert pool[0]["gold_bucket"] == "500 BC - 1 AD"
        assert pool[0]["provenance"]["sources"] == ["https://en.wikipedia.org/wiki/A"]

    def test_the_strata(self) -> None:
        assert G.region_of({"lat": -13.5, "lon": -72.0, "country": "Peru"}) == "americas"
        assert G.region_of({"lat": 30.0, "lon": 31.0, "country": "Egypt"}) == "near-east-egypt"
        assert G.region_of({"lat": 27.0, "lon": 78.0, "country": "India"}) == "south-east-asia"
        assert G.region_of({"lat": 10.0, "lon": 10.0, "country": "Nigeria"}) == "africa"
        assert G.region_of({"lat": 45.0, "lon": 10.0, "country": "Italy"}) == "europe-mediterranean"
        assert [G.size_of(n) for n in (None, 900, 4000, 20000)] == ["none", "stub", "medium", "long"]
        assert G.type_group("Rock art") == "cave/rock art" and G.type_group("Hillfort") == "fort"


def world(n_sites: int = 1200) -> dict[str, Any]:
    """A pool of dated sites over two regions and the undated sites' shape."""
    sites, rows, histories, sizes = {}, [], {}, {}
    for n in range(1, n_sites + 1):
        americas = n % 4 == 0
        sites[sid(n)] = {"site_id": sid(n), "lat": -13.0 if americas else 45.0,
                         "lon": -72.0 if americas else 10.0,
                         "country": "Peru" if americas else "Italy"}  # fmt: skip
        rows.append(stored(n))
        histories[sid(n)] = [decision(n, "wd3")]
        sizes[sid(n)] = 900 if americas or n % 2 else 9000
    undated = [f"u{n}" for n in range(60)]
    for n, u in enumerate(undated):  # the undated shape: mostly American stubs
        sites[u] = {"site_id": u, "lat": -13.0, "lon": -72.0 if n % 3 else 10.0, "country": "Peru"}
        sizes[u] = 900
    return {"stored": rows, "histories": histories, "sites": sites, "sizes": sizes,
            "undated": undated}  # fmt: skip


class TestTheBuild:
    def test_gold_and_dev_are_disjoint_seeded_and_shaped_like_the_undated(self, tmp_path: Path) -> None:
        w = world()
        result = G.build(tmp_path, seed=5, **w)
        assert (result["round"], result["gold"]) == (1, 400)
        round_dir = tmp_path / "round-01"
        gold = {r["site_id"] for r in G._read_jsonl(round_dir / G.GOLD_FILE)}
        dev = {r["site_id"] for r in G._read_jsonl(round_dir / G.DEV_FILE)}
        assert len(dev) == 300 and not gold & dev
        americas = sum(1 for s in gold if w["sites"][s]["lon"] < -30)
        assert americas >= 200  # the undated are two thirds American stubs: oversampled
        again = G.build(tmp_path / "again", seed=5, **w)
        assert again["gold_sha256"] == result["gold_sha256"]

    def test_an_edited_gold_is_refused(self, tmp_path: Path) -> None:
        G.build(tmp_path, seed=1, **world())
        path = tmp_path / "round-01" / G.GOLD_FILE
        path.write_text(path.read_text().replace("-300", "-301", 1))
        with pytest.raises(G.GoldError, match="not the sealed gold"):
            G.read_sealed(tmp_path / "round-01")

    def test_a_new_round_only_after_a_failed_verdict_and_the_old_gold_becomes_dev(
        self, tmp_path: Path
    ) -> None:
        w = world()
        G.build(tmp_path, seed=1, **w)
        with pytest.raises(G.GoldError, match="not judged yet"):
            G.build(tmp_path, seed=2, **w)
        G._write_json(tmp_path / "round-01" / G.VERDICT_FILE, {"pass": False})
        G.build(tmp_path, seed=2, **w)
        first = {r["site_id"] for r in G._read_jsonl(tmp_path / "round-01" / G.GOLD_FILE)}
        second = {r["site_id"] for r in G._read_jsonl(tmp_path / "round-02" / G.GOLD_FILE)}
        dev2 = {r["site_id"] for r in G._read_jsonl(tmp_path / "round-02" / G.DEV_FILE)}
        assert not first & second and first <= dev2
        G._write_json(tmp_path / "round-02" / G.VERDICT_FILE, {"pass": True})
        with pytest.raises(G.GoldError, match="passed"):
            G.build(tmp_path, seed=3, **w)


# ------------------------------------------------------------------------------ measure and judge
class Loaded:
    """The extractor stand-in: every site decided -300, but every fifth -1500 (another bucket)."""

    def __init__(self, wrong_every: int = 5, abstain_every: int = 0) -> None:
        self.wrong_every, self.abstain_every = wrong_every, abstain_every
        self.skipped: dict[str, frozenset[str]] = {}
        self.sites: dict[str, Any] = {}

    def decide(self, site_id: str, *, skip_urls: frozenset[str] = frozenset()) -> X.Decision:
        self.skipped[site_id] = skip_urls
        n = int(site_id[:8])
        if self.abstain_every and n % self.abstain_every == 0:
            return X.Decision(site_id, X.ABSTAIN, reason=X.NO_CANDIDATE)
        start = -1500 if self.wrong_every and n % self.wrong_every == 0 else -300
        c = X.Candidate(start, start, start, X.YEAR, 2, "enwiki prose", "u", "q", 1, "built", "")
        return X.Decision(site_id, X.SINGLE, start, start, start, 2, c, [c])


def built(tmp_path: Path) -> Path:
    G.build(tmp_path, seed=1, **world())
    return tmp_path / "round-01"


CODE = {"a.py": "1", "CONFIG": "2"}


class TestMeasure:
    def test_measure_needs_the_frozen_code_and_runs_once(self, tmp_path: Path) -> None:
        round_dir = built(tmp_path)
        with pytest.raises(G.GoldError, match="FROZEN.json is missing"):
            G.measure(round_dir, Loaded(), CODE)
        G.freeze(round_dir, CODE)
        with pytest.raises(G.GoldError, match="CONFIG changed"):
            G.measure(round_dir, Loaded(), {**CODE, "CONFIG": "3"})
        loaded = Loaded(wrong_every=0)
        result = G.measure(round_dir, loaded, CODE)
        assert result["gold"]["precision"] == 1.0 and result["gold"]["emitted"] == 400
        # the gold decision's own pages are never read as tier 4 for its site
        assert all(urls == {"https://en.wikipedia.org/wiki/A"} for urls in loaded.skipped.values())
        with pytest.raises(G.GoldError, match="measured once"):
            G.measure(round_dir, loaded, CODE)
        with pytest.raises(G.GoldError, match="is measured"):
            G.freeze(round_dir, CODE)

    def test_the_verdict_passes_at_95_percent(self, tmp_path: Path) -> None:
        round_dir = built(tmp_path)
        G.freeze(round_dir, CODE)
        G.measure(round_dir, Loaded(wrong_every=0), CODE)
        record = G.verdict(round_dir)
        assert record["pass"] and record["reasons"] == [] and record["code"] == CODE
        assert G.require_passed(tmp_path, CODE)["round"] == 1
        with pytest.raises(G.GoldError, match="no round"):
            G.require_passed(tmp_path, {**CODE, "a.py": "9"})
        with pytest.raises(G.GoldError, match="judged once"):
            G.verdict(round_dir)

    def test_the_verdict_fails_below_and_says_why(self, tmp_path: Path) -> None:
        round_dir = built(tmp_path)
        G.freeze(round_dir, CODE)
        G.measure(round_dir, Loaded(wrong_every=5), CODE)
        record = G.verdict(round_dir)
        assert not record["pass"] and record["precision"] < 0.95
        assert any(r.startswith("bucket precision 0.") for r in record["reasons"])
        assert any(r.startswith("tier 2: precision") for r in record["reasons"])
        with pytest.raises(G.GoldError):
            G.require_passed(tmp_path, CODE)


class TestTheGate:
    SEAL = {"threshold": 0.95, "min_gold": 200, "min_emitted": 100, "tier_min": 20}

    def measured(self, **gold: Any) -> dict[str, Any]:
        base = {"sites": 400, "emitted": 150, "precision": 0.97,
                "by_tier": {"2": {"emitted": 150, "correct": 146, "precision": 0.9733}},
                "period_only": {"emitted": 0, "correct": 0}}  # fmt: skip
        return {"gold": {**base, **gold}}

    def test_it_passes(self) -> None:
        assert G.judge(self.SEAL, self.measured()) == (True, [])

    def test_too_few_emitted_or_gold_fail(self) -> None:
        ok, why = G.judge(self.SEAL, self.measured(emitted=99, sites=150))
        assert not ok and len(why) == 2

    def test_a_tier_with_too_few_cells_must_be_switched_off(self) -> None:
        by_tier = {"2": {"emitted": 140, "correct": 137, "precision": 0.9786},
                   "4": {"emitted": 3, "correct": 3, "precision": 1.0}}  # fmt: skip
        ok, why = G.judge(self.SEAL, self.measured(by_tier=by_tier))
        assert not ok and why == [
            "tier 4: 3 cell(s), too few to judge (< 20) - switch it off in dating.CONFIG"
        ]

    def test_period_words_alone_are_judged_on_their_own(self) -> None:
        ok, why = G.judge(self.SEAL, self.measured(period_only={"emitted": 40, "correct": 36}))
        assert not ok and why[0].startswith("period word alone: precision 0.9")

    def test_the_wilson_interval(self) -> None:
        assert G.wilson(190, 200) == (0.9104, 0.9726)
        assert G.wilson(0, 0) == (0.0, 0.0)


# ------------------------------------------------------------------------------ the wave's gates
class TestTheWaveGates:
    def _run(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, code: dict[str, str]) -> Path:
        run = tmp_path / "wd5x"
        R.write_run(run, R.EXTRACT)
        (run / "DECISIONS.jsonl").write_text('{"site_id": "a"}\n', encoding="utf-8")
        sha = X._sha256(run / "DECISIONS.jsonl")
        X._write_json(run / X.EXTRACT_FILE, {"code": code, "decisions_sha256": sha})
        X._write_json(run / X.VERIFIED_FILE, {"decisions_sha256": sha})
        monkeypatch.setattr(X, "code_hashes", lambda *a: dict(CODE))
        monkeypatch.setattr(G, "GOLD_ROOT", tmp_path / "gold")
        return run

    def test_the_wave_needs_a_passing_gold_of_the_current_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = self._run(tmp_path, monkeypatch, code=CODE)
        with pytest.raises(PlanError, match="no round"):
            PLAN._require_gold(run)
        round_dir = tmp_path / "gold" / "round-01"
        G.build(tmp_path / "gold", seed=1, **world())
        G.freeze(round_dir, CODE)
        G.measure(round_dir, Loaded(wrong_every=0), CODE)
        G.verdict(round_dir)
        assert PLAN._require_gold(run)["round"] == 1

    def test_a_run_extracted_with_other_code_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = self._run(tmp_path, monkeypatch, code={**CODE, "a.py": "0"})
        with pytest.raises(PlanError, match="extract again"):
            PLAN._require_gold(run)

    def test_unverified_decisions_are_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = self._run(tmp_path, monkeypatch, code=CODE)
        (run / X.VERIFIED_FILE).unlink()
        with pytest.raises(PlanError, match="read at its permalink"):
            PLAN._require_gold(run)

    def test_the_shown_cells_gate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        run = self._run(tmp_path, monkeypatch, code=CODE)
        with pytest.raises(PlanError, match="shown before the wave"):
            PLAN._require_owner_shown(run)
        sha = X._sha256(run / "DECISIONS.jsonl")
        record = {"decisions_sha256": sha, "shown_by": "owner AFK, autonomous mandate 2026-11-05",
                  "n": 30, "wrong": 2, "go": False}  # fmt: skip
        X._write_json(run / X.SHOWN_FILE, record)
        with pytest.raises(PlanError, match="2 of 30 shown cells wrong"):
            PLAN._require_owner_shown(run)
        X._write_json(run / X.SHOWN_FILE, {**record, "wrong": 1, "go": True})
        assert PLAN._require_owner_shown(run)["wrong"] == 1
        X._write_json(run / X.SHOWN_FILE, {**record, "wrong": 0, "go": True, "decisions_sha256": "x"})
        with pytest.raises(PlanError, match="another DECISIONS.jsonl"):
            PLAN._require_owner_shown(run)


class TestConflicts:
    def test_d72_lists_the_dated_sites_read_into_another_bucket(self, tmp_path: Path) -> None:
        loaded = Loaded(wrong_every=2)
        rows = [stored(n) for n in range(1, 5)] + [stored(5, None), stored(6, scope_status="retired")]
        loaded.sites = {r["site_id"]: r for r in rows}
        out = tmp_path / "CONFLICTS.jsonl"
        assert G.conflicts(loaded, rows, out) == {"dated_sites": 4, "conflicts": 2}
        listed = [json.loads(r) for r in out.read_text().splitlines()]
        assert [r["extracted"] for r in listed] == [-1500, -1500]
