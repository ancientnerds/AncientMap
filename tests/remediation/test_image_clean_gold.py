"""The clean gold of D117 (`image_roles/clean_gold.py`) and the D118 prefilter probe.

Offline: the sites, pictures and answers are invented; the answers carry the stamp of the role's
registered model (the probe's: the candidate's), and the interval is a stub.
"""

from __future__ import annotations

import functools
import io
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
import roles as RO  # noqa: E402
from image_roles import calibrate as CAL  # noqa: E402
from image_roles import clean_gold as CG  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import prefilter_probe as PP  # noqa: E402
from image_roles import stage as SG  # noqa: E402
from served_image import state as ST  # noqa: E402

#: Proven on the role registry as it stood until owner decision D153 (2026-11-10) put every role on
#: Fable: a tier move, the hold at the top tier, a release, a candidate trial and a stamp refused
#: between two roles' models all need roles on different tiers, and no calibration is run on Fable
#: (D154). `conftest.registry_until_d153` rebuilds that registry from the applied moves; what D153
#: and D154 changed is tested on the registry as it is (`test_roles_fable.py`).
pytestmark = pytest.mark.usefixtures("registry_until_d153")

DRAWN = "2026-11-06T01:00:00Z"
LABELLED = "2026-11-06T02:00:00+00:00"
FIXED = "2026-11-06T03:00:00Z"
MEASURED = "2026-11-06T04:00:00+00:00"


def cp(k: int, n: int) -> tuple[float, float]:
    return (0.0, 1.0)


@functools.cache
def jpeg(shade: int = 100) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (400, 300), (shade, shade, shade)).save(out, format="JPEG")
    return out.getvalue()


def read(case: Any) -> bytes:
    return jpeg()


def answer_all(
    handoff: Path, spec: SG.Spec, text_of, *, agent: str, now: str, model: str | None = None
) -> None:
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff, batch_id=line["batch_id"], stage=spec.name, label=line["label"],
            text=text_of(line), answered_by=f"{spec.role}:{agent}-{line['batch_id']}",
            model=OH.ANSWER_MODELS[model or RO.role(spec.role).model], now=lambda: now,
        )  # fmt: skip


def site(sid: str, lat: float = 51.0, lon: float = -1.8, kind: str = "Henge") -> dict[str, Any]:
    return {"id": sid, "name": f"Site {sid}", "country": "UK", "site_type": kind, "lat": lat,
            "lon": lon}  # fmt: skip


def context(sid: str) -> dict[str, Any]:
    return {"site_id": sid, "name": f"Site {sid}", "country": "UK", "site_type": "Henge",
            "lat": 51.0, "lon": -1.8, "description": "A henge.", "wikipedia_lead": None}  # fmt: skip


def picture(sid: str, file: str, hero: bool = False) -> dict[str, Any]:
    return {"file": file, "commons_file": file.replace(".webp", ".jpg"), "path": f"/x/{sid}/{file}",
            "picture_site": sid, "is_hero": hero, "image_id": abs(hash((sid, file))) % 10**6}  # fmt: skip


def state(sites: list[dict[str, Any]]) -> ST.State:
    return ST.State(
        read_at="r", sites={s["id"]: s for s in sites}, rows={}, retired=frozenset(), sha256="x"
    )


# ===================================================================== D116: the museum rule
def test_the_re_check_and_the_depicts_judge_share_the_d116_museum_rule() -> None:
    from image_roles import depicts as DP
    from image_roles import hero_recheck as HR
    from served_image import vision as V

    # D127 (served-check-v4) keeps D116's rule for an architectural part and narrows a loose find
    assert V.CHECK_PROMPT_V3_ID == "served-check-v3" and HR.PROMPT_ID == V.RECHECK_PROMPT_ID
    assert "the Ishtar Gate in Berlin for Babylon" in V.CHECK_PROMPT_V3
    assert "the Ishtar Gate in Berlin for Babylon" in V.RECHECK_PROMPTS[HR.PROMPT_ID]
    assert "the Ishtar Gate in Berlin for Babylon" in DP.JUDGE_LINE
    # the first check's frozen text keeps its old terms (its recorded questions are read back)
    assert "Ishtar" not in V.CHECK_PROMPT and "Ishtar" not in V.CHECK_PROMPT_V2


# ======================================================================== the seal and the pins
class TestTheSeal:
    def test_d119_tolerates_two_percent_false_depicts_and_no_zero_foreign_rule(self) -> None:
        roles = CG.THRESHOLDS[CG.DEPICTS_KIND]["roles"]
        assert roles["image_depicts"]["false_depicts_max"] == 0.02
        assert roles["image_depicts"]["every_foreign_not_depicts"] is False
        assert roles["image_depicts"]["sensitivity_min"] == 0.90
        assert roles["image_depicts"]["precision_min"] == 0.95
        assert roles["adversarial"]["agreement_min"] == 0.95
        kinds = CG.THRESHOLDS[CG.KIND_KIND]["roles"]["image_prefilter"]
        assert kinds == {"photo_agreement_min": 0.92, "depicts_capable_recall_min": 0.98}

    def test_the_seal_binds_the_roles_and_pins_prompts_and_code(self, tmp_path: Path) -> None:
        d = tmp_path / "image-roles-v3"
        CG.seal(d, CG.DEPICTS_KIND, now=lambda: DRAWN)
        document = CG.sealed(d)
        assert document["version"] == "image-roles-v3"
        assert set(document["role_registry"]) == {"image_depicts", "adversarial", "pilot_judge"}
        assert document["role_registry"]["adversarial"]["role"] == "image_adversarial"
        assert document["pins"]["prompts"] == CG.prompt_pins()
        assert set(document["pins"]["modules"]) == set(CG.PINNED_MODULES)
        with pytest.raises(CG.GoldError, match="sealed already"):
            CG.seal(d, CG.DEPICTS_KIND)

    def test_a_moved_prompt_is_refused(self, tmp_path: Path, monkeypatch) -> None:
        d = tmp_path / "v3"
        CG.seal(d, CG.DEPICTS_KIND)
        CG.check_prompts(CG.sealed(d))
        monkeypatch.setattr(CG.DP, "JUDGE_LINE", CG.DP.JUDGE_LINE + " more")
        with pytest.raises(CG.GoldError, match="depicts.JUDGE_LINE"):
            CG.check_prompts(CG.sealed(d))

    def test_the_draw_needs_the_seal_and_is_written_once(self, tmp_path: Path) -> None:
        with pytest.raises(ST.StateError):
            CG.write_draw(tmp_path, [{"case_id": "x"}], {})
        CG.seal(tmp_path, CG.KIND_KIND)
        CG.write_draw(tmp_path, [{"case_id": "x"}], {}, now=lambda: DRAWN)
        with pytest.raises(CG.GoldError, match="drawn already"):
            CG.write_draw(tmp_path, [{"case_id": "y"}], {})
        (tmp_path / CG.DRAW_FILE).write_text('{"case_id": "z"}\n', encoding="utf-8")
        with pytest.raises(CG.GoldError, match="changed after it was drawn"):
            CG.drawn(tmp_path)


# ====================================================================================== the draw
def _gallery() -> tuple[ST.State, dict[str, list[dict[str, Any]]]]:
    sites = [
        site("stone", 51.1789, -1.8262),
        site("wood", 51.1893, -1.7856),  # 3.2 km from stone, the same type
        site("far", 40.0, 20.0, kind="Temple"),
        site("mus", 30.0, 30.0, kind="Temple"),
    ]
    sites[0]["name"], sites[1]["name"] = "Stonehenge", "Woodhenge"
    gallery = {
        "stone": [picture("stone", "Stonehenge.webp", True), picture("stone", "Stonehenge 2.webp")],
        "wood": [picture("wood", "Woodhenge.webp", True), picture("wood", "Woodhenge posts.webp")],
        "far": [
            picture("far", "Temple.webp", True),
            picture("far", "Village church.webp"),
            picture("far", "Temple 3.webp"),
        ],
        "mus": [picture("mus", "Relief in the British Museum.webp"), picture("mus", "x.webp")],
    }
    return state(sites), gallery


class TestTheDraw:
    def _draw(self, **over: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        st, gallery = _gallery()
        draw = {**CG.THRESHOLDS[CG.DEPICTS_KIND]["draw"], **over}
        pool = [("pool1", {"file": f"P{i}.jpg", "picture_url": f"https://u/{i}"}, v)
                for i, v in enumerate(["depicts", "other_site", "region_or_type", "depicts"])]  # fmt: skip
        st.sites["pool1"] = site("pool1", 10.0, 10.0)  # type: ignore[index]
        return CG.draw_depicts(
            state=st, site_context=context, gallery=gallery, pool=pool,
            pool_path=lambda c: f"/pool/{c['file']}", draw=draw, seed=1,
        )  # fmt: skip

    def test_the_forced_pair_asks_each_site_about_the_other_s_pictures(self) -> None:
        cases, notes = self._draw()
        assert notes["forced_pairs_missing"] == [["Avebury", "Silbury Hill"]]
        pair = [c for c in cases if c["group"].startswith("pair")]
        assert {c["site"]["site_id"] for c in pair} == {"stone"}
        assert {c["file"] for c in pair if c["group"] == "pair_other"} == {
            "Woodhenge.webp", "Woodhenge posts.webp"}  # fmt: skip
        assert all(c["picture_site"] == "wood" for c in pair if c["group"] == "pair_other")
        assert all(c["truth"] is None for c in cases)  # the labels decide, not the draw

    def test_a_site_is_drawn_into_one_stratum_only(self) -> None:
        cases, _ = self._draw()
        strata: dict[str, set[str]] = {}
        for c in cases:
            group = "pair" if c["group"].startswith("pair") else c["group"]
            group = "hero" if group in ("hero", "gallery", "gallery_trap", "neighbour") else group
            strata.setdefault(c["site"]["site_id"], set()).add(group)
        assert all(len(groups) == 1 for groups in strata.values())

    def test_museum_pool_and_hero_strata(self) -> None:
        cases, notes = self._draw()
        museum = [c for c in cases if c["group"] == "museum"]
        assert [c["file"] for c in museum] == ["Relief in the British Museum.webp"]
        pool = [c for c in cases if c["group"] == "pool"]
        # one candidate of each MiniMax class first, three at most, each with its route
        assert len(pool) == 3 and all(c["why"] == "a Commons search" for c in pool)
        assert all(c["path"].startswith("/pool/") and c["picture_url"] for c in pool)
        hero = [c for c in cases if c["site"]["site_id"] == "far"]
        assert [c["group"] for c in hero][:1] == ["hero"]
        assert "gallery_trap" in {c["group"] for c in hero}  # the village church is a trap
        assert notes["hero_sites_without_neighbour"] == 1

    def test_the_draw_is_deterministic(self) -> None:
        assert self._draw() == self._draw()

    def test_gallery_pictures_skip_the_asked_the_excluded_and_the_missing(self) -> None:
        rows = {
            "s": (
                {"id": 1, "filename": "a.webp", "is_hero": True, "is_excluded": False,
                 "original_url": "https://upload.wikimedia.org/wikipedia/commons/a/aa/A.jpg"},
                {"id": 2, "filename": "b.webp", "is_hero": False, "is_excluded": True},
                {"id": 3, "filename": "c.webp", "is_hero": False, "is_excluded": False},
                {"id": 4, "filename": "d.webp", "is_hero": False, "is_excluded": False},
                {"id": 5, "filename": "e.webp", "is_hero": False, "is_excluded": False},
            )
        }  # fmt: skip
        st = ST.State(
            read_at="r", sites={"s": site("s")}, rows=rows, retired=frozenset(), sha256="x"
        )
        out = CG.gallery_pictures(
            st, lambda sid, f: None if f == "e.webp" else f"/p/{f}", {4}, {("s", "c.webp")}
        )
        assert [p["file"] for p in out["s"]] == ["a.webp"]
        assert out["s"][0]["commons_file"] == "A.jpg" and out["s"][0]["is_hero"]

    def test_the_kind_draw_stratifies_by_what_the_file_names_promise(self) -> None:
        gallery = {
            "s": [picture("s", n) for n in
                  ["Map of x.webp", "Plan.webp", "Engraving.webp", "Museo.webp", "Portrait.webp",
                   "Ruin.webp", "Ruin 2.webp"]]
        }  # fmt: skip
        pool = [
            ("p", {"file": f"P{i}.jpg", "picture_url": f"https://u/{i}"}, "x") for i in range(5)
        ]
        cases, notes = CG.draw_kinds(
            gallery=gallery, pool=pool, pool_path=lambda c: f"/pool/{c['file']}",
            draw={"gallery_per_class": 1, "pool": 2}, seed=1,
        )  # fmt: skip
        assert notes["by_group"] == {
            "map": 1,
            "art": 1,
            "museum": 1,
            "people": 1,
            "plain": 1,
            "pool": 2,
        }
        assert all(c["role"] == "image_prefilter" and c["truth"] is None for c in cases)


# ================================================================ the labels and the fixed gold
def _depicts_dir(tmp_path: Path) -> tuple[Path, list[dict[str, Any]]]:
    d = tmp_path / "image-roles-v3"
    CG.seal(d, CG.DEPICTS_KIND, now=lambda: DRAWN)
    cases = []
    for i in range(4):
        sid = f"s{i}"
        for j, group in enumerate(["hero", "neighbour"]):
            pic = picture(sid if group == "hero" else "n", f"{sid}-{j}.webp")
            cases.append(CG._case(group, context(sid), pic))
    CG.write_draw(d, cases, {}, now=lambda: DRAWN)
    return d, cases


def _label_text(truth_of):
    def text(line: dict[str, Any], *, spec: SG.Spec, run: Path) -> str:
        q = SG.load_questions(run, spec)[(line["batch_id"], line["label"])]
        out = {}
        for item in q.meta["items"]:
            yes = truth_of(q.meta["site_id"], item["file"])
            out[item["label"]] = {
                "verdict": "depicts" if yes else "other_site",
                "quality": 4 if yes else None,
                "note": "the post markers; https://en.wikipedia.org/wiki/Woodhenge",
            }
        return json.dumps({"candidates": out})

    return text


def _label(d: Path, who: str, truth_of) -> None:
    handoff = d.parent / f"label-{who}"
    CG.label_export(d, who, handoff, read)
    spec = CG.LABEL_SPECS[who]
    text = _label_text(truth_of)
    answer_all(handoff, spec, lambda line: text(line, spec=spec, run=d), agent=who, now=LABELLED)
    SG.import_answers(d, handoff, spec)


class TestTheLabels:
    def test_two_labellers_a_third_on_the_disputes_and_the_majority(self, tmp_path: Path) -> None:
        d, cases = _depicts_dir(tmp_path)
        is_hero = lambda sid, f: f.endswith("-0.webp")  # noqa: E731
        _label(d, "a", is_hero)
        _label(d, "b", lambda sid, f: is_hero(sid, f) or f == "s0-1.webp")  # one dispute
        found = CG.disputes(d, write=True)
        dispute = [c["case_id"] for c in cases if c["file"] == "s0-1.webp"]
        assert found["disputed"] == dispute and found["agreement"] == 0.875
        with pytest.raises(ST.StateError, match="LABEL_C.jsonl does not exist"):
            CG.consensus(d)
        _label(d, "c", is_hero)
        exported = SG.load_questions(d, CG.LABEL_SPECS["c"])
        assert len(exported) == 1  # c is asked only the disputed case's site
        agreed = CG.consensus(d)
        assert agreed[dispute[0]]["truth"] == {"depicts": False}
        assert len(agreed[dispute[0]]["labels"]) == 3

    def test_one_agent_cannot_be_both_labellers(self, tmp_path: Path) -> None:
        d, _ = _depicts_dir(tmp_path)
        for who in ("a", "b"):
            handoff = d.parent / f"label-{who}"
            CG.label_export(d, who, handoff, read)
            spec = CG.LABEL_SPECS[who]
            text = _label_text(lambda sid, f: True)
            answer_all(handoff, spec, lambda line: text(line, spec=spec, run=d), agent="same",
                       now=LABELLED)  # fmt: skip
            SG.import_answers(d, handoff, spec)
        with pytest.raises(CG.GoldError, match="share agents"):
            CG.disputes(d)

    def test_a_labeller_shares_no_handoff(self, tmp_path: Path) -> None:
        d, _ = _depicts_dir(tmp_path)
        CG.label_export(d, "a", d.parent / "h", read)
        with pytest.raises(CG.GoldError, match="another labeller's handoff"):
            CG.label_export(d, "b", d.parent / "h", read)

    def test_the_fixed_gold_takes_the_check_and_draws_the_re_check(self, tmp_path: Path) -> None:
        d, cases = _depicts_dir(tmp_path)
        is_hero = lambda sid, f: f.endswith("-0.webp")  # noqa: E731
        _label(d, "a", is_hero)
        _label(d, "b", is_hero)
        with pytest.raises(CG.GoldError, match="does not exist"):
            CG.fix(d)
        listed = CG.spotcheck_list(d)
        assert len(listed) == len(cases)  # fewer cases than 30: every one is listed
        override = listed[0]["case_id"]
        rows = [
            {"case_id": r["case_id"], "truth": r["truth"] if r["case_id"] != override
             else {"depicts": not r["truth"]["depicts"]}, "agrees": r["case_id"] != override,
             "note": "checked against the picture"}
            for r in listed
        ]  # fmt: skip
        (d / CG.SPOTCHECK_FILE).write_text(ST.jsonl_text(rows), encoding="utf-8")
        result = CG.fix(d, now=lambda: FIXED)
        assert result["overrides"] == 1
        gold, _ = CAL.fixed_gold(d)
        depicts = [c for c in gold if c["role"] == "image_depicts"]
        flipped = next(c for c in depicts if c["case_id"] == override)
        assert flipped["truth"] == (
            "depicts" if not listed[0]["truth"]["depicts"] else "not_depicts"
        )
        recheck = [c for c in gold if c["role"] == "adversarial"]
        assert recheck and all(c["case_id"].startswith("rck-") for c in recheck)
        assert {c["truth"] for c in recheck} == {"depicts", "not_depicts"}
        with pytest.raises(CG.GoldError, match="the gold is fixed"):
            CG.label_export(d, "c", d.parent / "label-c2", read)


# ======================================================================================= measuring
def _gold_case(cid: str, truth: str, group: str = "hero", verdicts=("other_site",) * 2):
    return {
        "case_id": cid, "role": "image_depicts", "group": group, "site": {"site_id": cid},
        "file": f"{cid}.jpg", "truth": truth,
        "labels": [{"verdict": v} for v in verdicts],
    }  # fmt: skip


def _result(cid: str, verdict: str) -> dict[str, Any]:
    return {
        "meta": {"site_id": cid, "items": [{"label": "C1", "file": f"{cid}.jpg"}]},
        "candidates": {"C1": {"verdict": verdict, "quality": 3 if verdict == "depicts" else None,
                              "note": "n"}},
    }  # fmt: skip


class TestMeasuring:
    def test_depicts_counts_every_positive_and_every_negative(self) -> None:
        cases = [_gold_case(f"p{i}", "depicts") for i in range(9)] + [
            _gold_case("n1", "not_depicts", "neighbour"),
            _gold_case("n2", "not_depicts", "gallery_trap", ("region_or_type",) * 2),
        ]
        results = [_result(f"p{i}", "depicts" if i else "region_or_type") for i in range(9)]
        results += [_result("n1", "depicts"), _result("n2", "region_or_type")]
        m = CG.measure_depicts(cases, results, cp)
        assert (m["sensitivity"]["k"], m["sensitivity"]["n"]) == (8, 9)
        assert (m["false_depicts"]["k"], m["false_depicts"]["n"]) == (1, 2)
        assert (m["precision"]["k"], m["precision"]["n"]) == (8, 9)
        assert m["foreign_called_depicts"] == ["n1"] and m["foreign_rows"] == 1
        assert m["by_group"]["neighbour"] == {"fp": 1}
        document = {"roles": CG.THRESHOLDS[CG.DEPICTS_KIND]["roles"]}
        failures = CAL.decide("image_depicts", document, m)
        assert any("false_depicts 0.5 is above 0.02" in f for f in failures)
        assert not any("foreign row" in f for f in failures)  # D119: no zero-tolerance rule

    def test_kinds_measure_the_labelled_survivors(self) -> None:
        cases = [
            {"case_id": "k1", "role": "image_prefilter", "truth": {"photo": True, "survives": True}},
            {"case_id": "k2", "role": "image_prefilter", "truth": {"photo": False, "survives": False}},
            {"case_id": "k3", "role": "image_prefilter", "truth": {"photo": False, "survives": True}},
        ]  # fmt: skip
        results = [{
            "meta": {"items": [{"label": f"C0{i}", "site_id": f"k{i}", "file": "f"} for i in (1, 2, 3)]},
            "items": {"C01": {"kind": "site_photo", "usable": True},
                      "C02": {"kind": "map_or_document", "usable": True},
                      "C03": {"kind": "painting_or_artwork", "usable": False}},
            "answered_by": "x", "model": "y",
        }]  # fmt: skip
        m = CG.measure_kinds(cases, results, cp)
        assert m["photo_agreement"]["k"] == 3
        assert (m["depicts_capable_recall"]["k"], m["depicts_capable_recall"]["n"]) == (1, 2)
        assert m["dropped"] == ["k3"]

    def test_the_re_check_agreement_names_what_it_confirmed_wrongly(self) -> None:
        cases = [
            {"case_id": "rck-a", "role": "adversarial", "file": "a.jpg", "truth": "depicts"},
            {"case_id": "rck-b", "role": "adversarial", "file": "b.jpg", "truth": "not_depicts"},
        ]
        results = [
            {"meta": {"site_id": "rck-a", "file": "a.jpg"}, "verdict": "depicts"},
            {"meta": {"site_id": "rck-b", "file": "b.jpg"}, "verdict": "depicts"},
        ]
        m = CG.measure_adversarial(cases, results, cp)
        assert m["agreement"]["k"] == 1 and m["confirmed_false"] == ["rck-b"]


# ================================================================================ D118: the probe
class TestTheProbe:
    @pytest.fixture(autouse=True)
    def _as_the_probe_ran(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The registry as the probe ran (D118 moved the prefilter to Opus on its evidence)."""
        monkeypatch.setattr(
            RO,
            "ROLES",
            {
                **RO.ROLES,
                "image_prefilter": replace(RO.ROLES["image_prefilter"], model="claude-sonnet-5-5"),
            },
        )

    def _source(self, tmp_path: Path) -> tuple[Path, list[dict[str, Any]]]:
        src = tmp_path / "image-roles-v2"
        src.mkdir()
        cases = [
            {"case_id": f"kind-{i}", "role": "image_prefilter", "group": "kind", "site": {},
             "file": f"{i}.jpg", "path": "/x", "truth": t}
            for i, t in enumerate(["site_photo", "map_or_document", "artifact"])
        ]  # fmt: skip
        (src / CAL.GOLD_FILE).write_text(CAL.gold_text(cases, truth=True), encoding="utf-8")
        digest = ST.sha256_text(CAL.gold_text(cases, truth=True))
        (src / CAL.SEAL_LOG).write_text(
            json.dumps({"gold_sha256": digest, "cases": 3, "fixed_at": DRAWN}) + "\n",
            encoding="utf-8",
        )
        flat = [{"site_id": c["case_id"], "file": c["file"], "path": "/x"} for c in cases]
        questions, pictures = PF.build_questions(flat, read)
        old = tmp_path / "old-handoff"
        SG.export(src, old, PF.SPEC, questions, pictures)
        kinds = {"C01": "other", "C02": "map_or_document", "C03": "artifact"}  # C01 a Sonnet miss
        answer_all(old, PF.SPEC, lambda line: json.dumps(
            {"items": {k: {"kind": v, "usable": True} for k, v in kinds.items()}}),
            agent="sonnet", now=LABELLED)  # fmt: skip
        SG.import_answers(src, old, PF.SPEC)
        return src, cases

    def test_the_probe_asks_v2_s_questions_of_opus_and_compares(self, tmp_path: Path) -> None:
        src, _ = self._source(tmp_path)
        run, handoff = tmp_path / "probe", tmp_path / "probe-handoff"
        summary = PP.export(src, run, handoff)
        old = json.loads((src / PF.SPEC.export_file).read_text(encoding="utf-8"))
        assert summary["questions_sha256"] == old["questions_sha256"]
        brief = PP.brief(run, handoff, "pre-0001")
        assert (
            "running as claude-opus-5-5" in brief and "--candidate-model claude-opus-5-5" in brief
        )
        right = {"C01": "site_photo", "C02": "map_or_document", "C03": "artifact"}
        answer_all(handoff, PF.SPEC, lambda line: json.dumps(
            {"items": {k: {"kind": v, "usable": True} for k, v in right.items()}}),
            agent="probe", now=MEASURED, model=PP.CANDIDATE)  # fmt: skip
        result = PP.measure(run, handoff, cp=cp)
        assert result["probe_model"] == [OH.ANSWER_MODELS[PP.CANDIDATE]]
        assert (result["before_failed"], result["probe_failed"], result["fixed"]) == (1, 0, 1)
        assert result["probe"]["photo_agreement"]["k"] == 3
        with pytest.raises(ST.StateError, match="written once"):
            PP.measure(run, handoff, cp=cp)

    def test_an_answer_in_the_registered_model_s_stamp_is_no_trial(self, tmp_path: Path) -> None:
        src, _ = self._source(tmp_path)
        run, handoff = tmp_path / "probe", tmp_path / "probe-handoff"
        PP.export(src, run, handoff)
        answer_all(handoff, PF.SPEC, lambda line: json.dumps(
            {"items": {f"C0{i}": {"kind": "other", "usable": True} for i in (1, 2, 3)}}),
            agent="probe", now=MEASURED)  # fmt: skip
        with pytest.raises(SG.StageError, match="candidate model"):
            PP.measure(run, handoff, cp=cp)


def test_the_probe_is_no_trial_once_the_prefilter_is_registered_on_opus() -> None:
    """D118 applied the move the probe was evidence for: Opus is the role's model, not a candidate."""
    assert RO.role("image_prefilter").model == PP.CANDIDATE
    with pytest.raises(RO.RoleError, match="it is no candidate"):
        RO.candidate_model(PF.SPEC.role, PP.CANDIDATE)


def test_repicture_fetches_exactly_the_pool_pictures_of_a_draw(tmp_path: Path) -> None:
    from candidate_search import pool as PL
    from candidate_search import repicture as RP

    d, old = tmp_path / "image-roles-v3", tmp_path / "candidates-old"
    CG.seal(d, CG.DEPICTS_KIND)
    candidate = {"file": "P.jpg", "picture_url": "https://thumb.wikimedia.org/x/1280px-P.jpg"}
    pool_case = CG._case("pool", context("s"), {"file": "P.jpg", "commons_file": "P.jpg",
                         "path": str(PL.picture_path(old, candidate))})  # fmt: skip
    pool_case["picture_url"] = candidate["picture_url"]
    gallery_case = CG._case("hero", context("s"), picture("s", "a.webp"))
    CG.write_draw(d, [pool_case, gallery_case], {})
    assert RP.need_gold(old, d) == [("s", candidate)]
    pool_case["path"] = "/elsewhere"
    d2 = tmp_path / "image-roles-v3b"
    CG.seal(d2, CG.DEPICTS_KIND)
    CG.write_draw(d2, [pool_case], {})
    with pytest.raises(RP.RepictureError, match="its path is not"):
        RP.need_gold(old, d2)


def test_two_labellers_of_one_batch_are_briefed_under_two_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    d, _ = _depicts_dir(tmp_path)
    for who in ("a", "b"):
        CG.label_export(d, who, d.parent / f"label-{who}", read)
    from image_roles import run as RUN

    briefs = []
    for who in ("a", "b"):
        RUN.main(["brief", "--run-dir", str(d), "--handoff", str(d.parent / f"label-{who}"),
                  "--stage", f"image-gold-label-{who}", "--batch-id", "dep-0001"])  # fmt: skip
        briefs.append(capsys.readouterr().out)
    assert "--answered-by image-gold-label-a-dep-0001" in briefs[0]
    assert "--answered-by image-gold-label-b-dep-0001" in briefs[1]
    assert "--role pilot_judge" in briefs[0] and "running as claude-opus-5-5" in briefs[0]


def test_a_case_whose_picture_is_not_served_is_voided_before_the_labels(tmp_path: Path) -> None:
    d, cases = _depicts_dir(tmp_path)
    with pytest.raises(CG.GoldError, match="names its reason"):
        CG.void(d, cases[0]["case_id"], " ")
    CG.void(d, cases[0]["case_id"], "Commons serves no 1280 px rendering")
    assert [c["case_id"] for c in CG.drawn(d)[0]] == [c["case_id"] for c in cases[1:]]
    on_disk = tmp_path / "pic.jpg"
    on_disk.write_bytes(jpeg())
    d2 = tmp_path / "image-roles-v3x"
    CG.seal(d2, CG.DEPICTS_KIND)
    shown = {**cases[1], "path": str(on_disk)}
    CG.write_draw(d2, [shown, cases[2]], {})
    with pytest.raises(CG.GoldError, match="never voided"):
        CG.void(d2, shown["case_id"], "x")
    CG.label_export(d, "a", d.parent / "label-a", read)
    with pytest.raises(CG.GoldError, match="label was asked already"):
        CG.void(d, cases[1]["case_id"], "x")
