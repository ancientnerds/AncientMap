"""D17 (2026-10-08): the Claude roles of the picture research - transport, prefilter, depicts, hero
re-check, targets and identity.

DB-less and offline: pictures are small generated JPEGs, answers are written through
`opus_handoff.write_answer` into a temporary handoff, and every answer carries the stamp of the model
that the role is registered to (`roles.ROLES`).
"""

from __future__ import annotations

import functools
import io
import json
import sys
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
from candidate_search import judge as CJ  # noqa: E402
from image_roles import depicts as DP  # noqa: E402
from image_roles import hero_recheck as HR  # noqa: E402
from image_roles import identity as ID  # noqa: E402
from image_roles import pictures as PX  # noqa: E402
from image_roles import prefilter as PF  # noqa: E402
from image_roles import stage as SG  # noqa: E402
from image_roles import targets as TG  # noqa: E402
from image_roles import wiki_cache as WC  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image import vision as V  # noqa: E402

NOW = "2026-10-09T03:00:00+00:00"


@functools.cache
def jpeg(width: int = 2000, height: int = 1000, colour: int = 128) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (colour, colour, colour)).save(out, format="JPEG")
    return out.getvalue()


def stamp_of(role: str) -> str:
    return OH.ANSWER_MODELS[RO.role(role).model]


def answer_all(
    handoff: Path,
    spec: SG.Spec,
    texts: dict[str, str],
    *,
    role: str | None = None,
    model: str | None = None,
) -> None:
    """Record `texts[label]` for every question, in `role` (the spec's by default)."""
    role = role or spec.role
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff,
            batch_id=line["batch_id"],
            stage=spec.name,
            label=line["label"],
            text=texts[line["label"]],
            answered_by=f"{role}:{line['batch_id']}",
            model=model or stamp_of(role),
            now=lambda: NOW,
        )


# ====================================================================== the transport
def _tiny_spec(role: str = "image_prefilter") -> SG.Spec:
    def parse(meta: dict[str, Any], text: str) -> dict[str, Any]:
        data = SG.json_object(text, frozenset({"ok"}))
        if data["ok"] is not True:
            raise SG.AnswerShapeError("'ok' must be true")
        return {"ok": True}

    return SG.Spec(
        name="tiny-stage",
        role=role,
        prompt_id="tiny-v1",
        questions_file="QUESTIONS_TINY.jsonl",
        export_file="EXPORT_TINY.json",
        result_file="TINY.jsonl",
        parse=parse,
        what="say ok",
    )


def _tiny_export(tmp_path: Path, spec: SG.Spec) -> tuple[Path, Path, bytes]:
    run, handoff = tmp_path / "run", tmp_path / "handoff"
    picture = jpeg(40, 30)
    image = SG.image_ref("tiny-1", picture)
    question = SG.Question("b-001", "q1", "Look and say ok.", {"n": 1}, (image,))
    SG.export(run, handoff, spec, [question], {"tiny-1": picture})
    return run, handoff, picture


class TestTheTransport:
    def test_export_writes_the_prompt_the_picture_and_the_record_once(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, picture = _tiny_export(tmp_path, spec)
        assert (
            handoff / "b-001" / "tiny-stage" / "q1.prompt.txt"
        ).read_text() == "Look and say ok."
        assert (handoff / "images" / "tiny-1.jpg").read_bytes() == picture
        record = json.loads((run / spec.export_file).read_text(encoding="utf-8"))
        assert record["role"] == "image_prefilter" and record["questions"] == 1
        with pytest.raises(ST.StateError, match="written once"):
            _tiny_export(tmp_path, spec)

    def test_a_question_exported_twice_is_refused(self, tmp_path: Path) -> None:
        q = SG.Question("b-001", "q1", "p", {}, ())
        with pytest.raises(SG.StageError, match="twice"):
            SG.export(tmp_path / "r", tmp_path / "h", _tiny_spec(), [q, q], {})

    def test_a_picture_without_bytes_is_refused(self, tmp_path: Path) -> None:
        q = SG.Question("b-001", "q1", "p", {}, (SG.image_ref("x", b"abc"),))
        with pytest.raises(SG.StageError, match="no bytes for x"):
            SG.export(tmp_path / "r", tmp_path / "h", _tiny_spec(), [q], {})

    def test_the_stage_of_an_unregistered_role_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RO.RoleError, match="no role"):
            SG.export(tmp_path / "r", tmp_path / "h", _tiny_spec("oracle"), [], {})

    def test_the_brief_names_the_role_model_and_recording_command(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        text = SG.brief(run, handoff, spec, "b-001")
        assert "running as claude-haiku-5-5 in the role image_prefilter at effort low" in text
        assert "--model claude-haiku-5-5 --role image_prefilter" in text
        assert "check-answer --run-dir" in text and "--stage tiny-stage" in text
        assert "Do not use the web" in text
        with pytest.raises(SG.StageError, match="no batch"):
            SG.brief(run, handoff, spec, "b-999")

    def test_a_web_stage_may_read_the_cached_pages_and_the_web(self, tmp_path: Path) -> None:
        run, handoff = tmp_path / "run", tmp_path / "handoff"
        spec = ID.VERIFY_SPEC
        SG.export(run, handoff, spec, [SG.Question("idv-0001", "idv-0001", "p", {}, ())], {})
        text = SG.brief(run, handoff, spec, "idv-0001")
        assert "role web_verifier at effort high" in text
        assert "except the cached Wikipedia pages" in text and "403 or 429" in text

    def test_the_shape_of_an_answer_is_checked_without_recording_it(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        assert SG.check_answer(run, handoff, spec, "b-001", "q1", '{"ok": true}') is None
        assert "must be true" in SG.check_answer(run, handoff, spec, "b-001", "q1", '{"ok": 1}')
        assert "no JSON" in SG.check_answer(run, handoff, spec, "b-001", "q1", "nothing")
        with pytest.raises(SG.StageError, match="no question"):
            SG.check_answer(run, handoff, spec, "b-001", "zz", "{}")
        with pytest.raises(SG.StageError, match="not the handoff"):
            SG.check_answer(run, tmp_path / "elsewhere", spec, "b-001", "q1", "{}")
        assert not list(handoff.glob("**/*.answer.json"))

    def test_an_answer_in_the_roles_name_is_imported_with_its_stamp(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        answer_all(handoff, spec, {"q1": '{"ok": true}'})
        assert SG.import_answers(run, handoff, spec)["answers"] == 1
        (row,) = SG.read_results(run, spec)
        assert row["answered_by"] == "image_prefilter:b-001" and row["model"] == stamp_of(spec.role)
        assert row["meta"] == {"n": 1} and row["prompt_id"] == "tiny-v1"

    def test_an_answer_in_another_role_is_refused(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        answer_all(handoff, spec, {"q1": '{"ok": true}'}, role="adversarial")
        with pytest.raises(SG.StageError, match="not in the role image_prefilter"):
            SG.import_answers(run, handoff, spec)

    def test_an_answer_not_stamped_by_the_roles_model_is_refused(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        answer_all(handoff, spec, {"q1": '{"ok": true}'}, model=OH.OPUS_MODEL)
        with pytest.raises(SG.StageError, match="registered to claude-haiku-5-5"):
            SG.import_answers(run, handoff, spec)

    def test_an_answer_that_names_no_role_is_refused(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        OH.write_answer(
            handoff, batch_id="b-001", stage=spec.name, label="q1", text='{"ok": true}',
            answered_by="b-001", model=stamp_of(spec.role), now=lambda: NOW,
        )  # fmt: skip
        with pytest.raises(SG.StageError, match="not in the role image_prefilter"):
            SG.import_answers(run, handoff, spec)

    def test_an_unanswered_handoff_does_not_import(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        with pytest.raises(SG.StageError, match="1 missing"):
            SG.import_answers(run, handoff, spec)

    def test_a_changed_picture_stops_the_import(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        answer_all(handoff, spec, {"q1": '{"ok": true}'})
        (handoff / "images" / "tiny-1.jpg").write_bytes(jpeg(41, 30))
        with pytest.raises(SG.StageError, match="not the picture the question showed"):
            SG.import_answers(run, handoff, spec)

    def test_every_shape_problem_is_named_and_nothing_is_written(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        answer_all(handoff, spec, {"q1": '{"ok": false}'})
        with pytest.raises(SG.StageError, match="not in shape.*q1"):
            SG.import_answers(run, handoff, spec)
        assert not (run / spec.result_file).exists()

    def test_a_handoff_other_than_the_exported_one_is_refused(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        with pytest.raises(SG.StageError, match="not the handoff"):
            SG.import_answers(run, tmp_path / "elsewhere", spec)

    def test_a_changed_question_file_stops_the_import(self, tmp_path: Path) -> None:
        spec = _tiny_spec()
        run, handoff, _ = _tiny_export(tmp_path, spec)
        answer_all(handoff, spec, {"q1": '{"ok": true}'})
        path = run / spec.questions_file
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with pytest.raises(SG.StageError, match="not the file the export recorded"):
            SG.import_answers(run, handoff, spec)

    def test_the_text_helpers_refuse_what_is_out_of_shape(self) -> None:
        assert SG.text_field("  a note ", "note") == "a note"
        with pytest.raises(SG.AnswerShapeError, match="non-empty"):
            SG.text_field("  ", "note")
        with pytest.raises(SG.AnswerShapeError, match="at most 5"):
            SG.text_field("abcdef", "note", longest=5)
        with pytest.raises(SG.AnswerShapeError, match="not \\['a'\\]"):
            SG.json_object('{"b": 1}', frozenset({"a"}))


# ======================================================================== the pictures
class TestThePictures:
    def test_a_picture_is_made_smaller_never_larger(self) -> None:
        big = jpeg(2000, 1000)
        small = PX.downscale(big, PX.PREFILTER_SIDE)
        with Image.open(io.BytesIO(small)) as image:
            assert image.size == (640, 320)
        tiny = jpeg(100, 50)
        assert PX.downscale(tiny, PX.PREFILTER_SIDE) is tiny

    def test_the_depicts_side_is_the_projects_vlm_side(self) -> None:
        from pipeline.video.shorts_select import VLM_MAX_SIDE

        assert PX.DEPICTS_SIDE == VLM_MAX_SIDE

    def test_a_file_is_read_as_the_project_hands_it_to_a_judge(self, tmp_path: Path) -> None:
        path = tmp_path / "p.jpg"
        path.write_bytes(jpeg(3000, 2000))
        with Image.open(io.BytesIO(PX.picture_bytes(path, 1280))) as image:
            assert max(image.size) == 1280
        with Image.open(io.BytesIO(PX.picture_bytes(path, 640))) as image:
            assert max(image.size) == 640

    def test_image_names_are_stable_and_distinct(self) -> None:
        assert PX.image_name("pre", "a", "F.jpg") == PX.image_name("pre", "a", "F.jpg")
        assert PX.image_name("pre", "a", "F.jpg") != PX.image_name("pre", "b", "F.jpg")
        assert PX.image_name("pre", "a", "F.jpg").startswith("pre-")


# ======================================================================== the prefilter
def _candidates(n: int) -> list[dict[str, Any]]:
    return [{"site_id": f"s{i // 3}", "file": f"F{i}.jpg", "path": f"/x/{i}"} for i in range(n)]


class TestThePrefilter:
    def test_sixty_pictures_to_a_question_at_640_px(self) -> None:
        questions, pictures = PF.build_questions(_candidates(130), lambda c: jpeg())
        assert [len(q.images) for q in questions] == [60, 60, 10]
        assert [q.batch_id for q in questions] == ["pre-0001", "pre-0002", "pre-0003"]
        assert all(q.label == q.batch_id for q in questions)
        with Image.open(io.BytesIO(next(iter(pictures.values())))) as image:
            assert max(image.size) == 640

    def test_the_prompt_asks_for_kind_and_usable_and_not_for_the_site(self) -> None:
        (q,), _ = PF.build_questions(_candidates(3), lambda c: jpeg())
        for part in ("kind", "usable", "site_photo", "map_or_document", "C01", "C03"):
            assert part in q.prompt
        assert "Do not judge which site" in q.prompt
        assert q.meta["items"][1] == {"label": "C02", "site_id": "s0", "file": "F1.jpg"}

    def test_a_question_holds_at_most_sixty(self) -> None:
        with pytest.raises(SG.StageError, match="1..60"):
            PF.build_questions(_candidates(3), lambda c: jpeg(), batch_size=61)

    def _meta(self) -> dict[str, Any]:
        return {
            "items": [
                {"label": "C01", "site_id": "s", "file": "a"},
                {"label": "C02", "site_id": "s", "file": "b"},
            ]
        }

    def test_a_good_answer_parses(self) -> None:
        text = json.dumps(
            {
                "items": {
                    "C01": {"kind": "site_photo", "usable": True},
                    "C02": {"kind": "map_or_document", "usable": False},
                }
            }
        )
        got = PF.parse(self._meta(), text)["items"]
        assert got["C01"] == {"kind": "site_photo", "usable": True}

    @pytest.mark.parametrize(
        ("items", "problem"),
        [
            ({"C01": {"kind": "site_photo", "usable": True}}, "exactly C01..C02"),
            (
                {
                    "C01": {"kind": "photo", "usable": True},
                    "C02": {"kind": "other", "usable": True},
                },
                "not one of",
            ),
            (
                {
                    "C01": {"kind": "other", "usable": "yes"},
                    "C02": {"kind": "other", "usable": True},
                },
                "true or false",
            ),
            (
                {"C01": {"kind": "other"}, "C02": {"kind": "other", "usable": True}},
                "exactly 'kind' and 'usable'",
            ),
        ],
    )
    def test_an_answer_out_of_shape_is_named(self, items: dict[str, Any], problem: str) -> None:
        with pytest.raises(SG.AnswerShapeError, match=problem):
            PF.parse(self._meta(), json.dumps({"items": items}))

    def test_only_a_usable_picture_of_a_kind_that_can_show_a_site_survives(self) -> None:
        for kind in PF.KINDS:
            assert PF.survives({"kind": kind, "usable": True}) == (kind in PF.SURVIVING_KINDS)
            assert not PF.survives({"kind": kind, "usable": False})
        assert set(PF.SURVIVING_KINDS) == {"site_photo", "artifact", "painting_or_artwork"}

    def test_the_judged_candidates_are_flat_rows_with_their_stamp(self) -> None:
        row = {
            "meta": self._meta(),
            "items": {
                "C01": {"kind": "site_photo", "usable": True},
                "C02": {"kind": "people", "usable": True},
            },
            "answered_by": "image_prefilter:pre-0001",
            "model": stamp_of("image_prefilter"),
        }
        got = PF.judged([row])
        assert [(r["file"], r["survives"]) for r in got] == [("a", True), ("b", False)]
        assert got[0]["answered_by"] == "image_prefilter:pre-0001"

    def test_the_stage_runs_end_to_end_in_the_haiku_role(self, tmp_path: Path) -> None:
        run, handoff = tmp_path / "run", tmp_path / "handoff"
        questions, pictures = PF.build_questions(_candidates(2), lambda c: jpeg())
        SG.export(run, handoff, PF.SPEC, questions, pictures)
        text = json.dumps(
            {
                "items": {
                    "C01": {"kind": "site_photo", "usable": True},
                    "C02": {"kind": "other", "usable": False},
                }
            }
        )
        answer_all(handoff, PF.SPEC, {"pre-0001": text})
        SG.import_answers(run, handoff, PF.SPEC)
        got = PF.judged(SG.read_results(run, PF.SPEC))
        assert [r["survives"] for r in got] == [True, False]
        assert RO.role(PF.SPEC.role).model == "claude-haiku-5-5"


# ========================================================================== depicts
def _site(site_id: str, files: list[str], **over: Any) -> dict[str, Any]:
    base = {
        "site_id": site_id,
        "name": f"Site {site_id}",
        "country": "Greece",
        "site_type": "Tomb",
        "lat": 40.5,
        "lon": 24.5,
        "description": "A chamber tomb on a hill.",
        "wikipedia_lead": "Site is a chamber tomb in Greece.",
        "candidates": [
            {
                "file": f,
                "why": "a Commons picture search",
                "width": 3000,
                "height": 2000,
                "path": "/x",
            }
            for f in files
        ],
    }
    return base | over


class TestTheDepictsRole:
    def test_one_question_per_site_packed_without_splitting_a_site(self) -> None:
        sites = [_site("a", ["1.jpg", "2.jpg"]), _site("b", ["3.jpg"])]
        questions, pictures, left_out = DP.build_questions(sites, lambda c: jpeg())
        assert [(q.batch_id, q.label, len(q.images)) for q in questions] == [
            ("dep-0001", "a", 2),
            ("dep-0001", "b", 1),
        ]
        assert left_out == [] and len(pictures) == 3

    def test_the_prompt_carries_everything_the_old_one_lacked(self) -> None:
        site = _site("a", ["1.jpg"])
        site["candidates"][0] |= {
            "distance_m": 140.4,
            "why": "a Commons file geotagged within 300 m",
        }
        (q,), _, _ = DP.build_questions([site], lambda c: jpeg())
        for part in (
            '"Site a" (Tomb, Greece; latitude 40.5, longitude 24.5)',
            "A chamber tomb on a hill.",
            "Site is a chamber tomb in Greece.",
            "geotagged 140 m from the site's point",
            "C1: images/dep-",
            "quality",
            "the file name",  # the judge line: the name lies
            "A refusal is better than a wrong depicts",
        ):
            assert part in q.prompt, part

    def test_the_judge_line_names_the_three_recurring_classes(self) -> None:
        line = DP.JUDGE_LINE
        assert "street" in line and "Museum objects" in line and "generic" in line
        assert "legible sign" in line

    def test_a_site_without_an_article_says_so(self) -> None:
        (q,), _, _ = DP.build_questions(
            [_site("a", ["1.jpg"], wikipedia_lead=None)], lambda c: jpeg()
        )
        assert "none (no article)" in q.prompt

    def test_pictures_are_shown_at_1280_px(self) -> None:
        _, pictures, _ = DP.build_questions([_site("a", ["1.jpg"])], lambda c: jpeg(3000, 2000))
        with Image.open(io.BytesIO(next(iter(pictures.values())))) as image:
            assert max(image.size) == 1280

    def test_a_site_with_more_survivors_than_a_question_holds_names_the_rest(self) -> None:
        files = [f"{i}.jpg" for i in range(40)]
        questions, _, left_out = DP.build_questions([_site("a", files)], lambda c: jpeg())
        assert len(questions[0].images) == DP.MAX_PER_SITE == 36
        assert left_out == [{"site_id": "a", "file": f} for f in files[36:]]

    def _meta(self) -> dict[str, Any]:
        return {
            "site_id": "a",
            "name": "Site a",
            "items": [{"label": "C1", "file": "1.jpg"}, {"label": "C2", "file": "2.jpg"}],
        }

    def test_a_good_answer_parses_and_a_depicts_carries_a_quality(self) -> None:
        text = json.dumps(
            {
                "candidates": {
                    "C1": {"verdict": "depicts", "quality": 4, "note": "the chamber"},
                    "C2": {"verdict": "other_site", "quality": None, "note": "a coin"},
                }
            }
        )
        got = DP.parse(self._meta(), text)["candidates"]
        assert got["C1"]["quality"] == 4 and got["C2"]["quality"] is None

    @pytest.mark.parametrize(
        ("one", "problem"),
        [
            ({"verdict": "depicts", "quality": None, "note": "n"}, "needs a quality of 1 to 5"),
            ({"verdict": "depicts", "quality": 6, "note": "n"}, "needs a quality of 1 to 5"),
            ({"verdict": "depicts", "quality": True, "note": "n"}, "needs a quality of 1 to 5"),
            (
                {"verdict": "region_or_type", "quality": 3, "note": "n"},
                "only a depicts has a quality",
            ),
            ({"verdict": "maybe", "quality": None, "note": "n"}, "not one of"),
            ({"verdict": "other_site", "quality": None}, "exactly 'verdict', 'quality' and 'note'"),
            ({"verdict": "other_site", "quality": None, "note": " "}, "non-empty"),
        ],
    )
    def test_an_answer_out_of_shape_is_named(self, one: dict[str, Any], problem: str) -> None:
        ok = {"verdict": "other_site", "quality": None, "note": "n"}
        with pytest.raises(SG.AnswerShapeError, match=problem):
            DP.parse(self._meta(), json.dumps({"candidates": {"C1": one, "C2": ok}}))

    def test_every_candidate_must_be_judged(self) -> None:
        text = json.dumps(
            {"candidates": {"C1": {"verdict": "other_site", "quality": None, "note": "n"}}}
        )
        with pytest.raises(SG.AnswerShapeError, match="must judge exactly"):
            DP.parse(self._meta(), text)

    def test_the_verdict_rows_are_what_the_judge_stage_reads(self) -> None:
        result = {
            "meta": self._meta(),
            "candidates": {
                "C1": {"verdict": "depicts", "quality": 5, "note": "n"},
                "C2": {"verdict": "region_or_type", "quality": None, "note": "m"},
            },
            "answered_by": "image_depicts:dep-0001",
            "model": stamp_of("image_depicts"),
        }
        rows = DP.verdict_rows([result], {("a", "1.jpg"): (3000, 2000), ("a", "2.jpg"): (900, 400)})
        assert rows[0] | {} == {
            "site_id": "a", "name": "Site a", "file": "1.jpg", "verdict": "depicts", "quality": 5,
            "note": "n", "width": 3000, "height": 2000, "answered_by": "image_depicts:dep-0001",
            "model": stamp_of("image_depicts"),
        }  # fmt: skip
        with pytest.raises(SG.StageError, match="no size recorded"):
            DP.verdict_rows([result], {})

    def test_the_role_is_sonnet_at_medium_effort(self) -> None:
        assert (RO.role(DP.SPEC.role).model, RO.role(DP.SPEC.role).effort) == (
            "claude-sonnet-5-5",
            "medium",
        )


# ======================================================================= hero re-check
def _pick(site_id: str = "a", file: str = "1.jpg") -> dict[str, Any]:
    return {
        "site_id": site_id, "name": "Site a", "country": "Greece", "site_type": "Tomb",
        "lat": 40.5, "lon": 24.5, "qid": "Q9", "file": file, "path": "/x", "note": "the chamber",
        "answered_by": "image_depicts:dep-0001", "description": "A chamber tomb.",
        "wikipedia_title": "Site a", "picture_url": "https://upload.wikimedia.org/x.jpg",
    }  # fmt: skip


class TestTheHeroRecheck:
    def test_twelve_to_a_batch_and_the_round_in_the_batch_id(self) -> None:
        picks = [_pick(f"s{i}") for i in range(13)]
        questions, pictures = HR.build_questions(picks, lambda p: jpeg(), round_number=2)
        assert [q.batch_id for q in questions].count("rck-02-001") == 12
        assert questions[-1].batch_id == "rck-02-002" and len(pictures) == 13
        with pytest.raises(SG.StageError, match="from 1"):
            HR.build_questions(picks, lambda p: jpeg(), round_number=0)

    def test_the_prompt_is_the_d15_recheck_with_the_depicts_verdict_as_the_earlier_one(
        self,
    ) -> None:
        (q,), _ = HR.build_questions([_pick()], lambda p: jpeg(), round_number=1)
        assert q.prompt.startswith("You re-check a verdict.")
        assert "called the picture depicts: the chamber" in q.prompt
        assert "image-depicts, image_depicts:dep-0001" in q.prompt
        assert "is, or is about to become, the main image" in q.prompt
        assert q.label == "a" and q.meta == {"site_id": "a", "file": "1.jpg", "round": 1}

    def test_an_other_site_needs_the_monument_and_a_commons_page(self) -> None:
        good = json.dumps(
            {
                "verdict": "other_site",
                "shows": "the Treasury at Petra in Jordan",
                "basis": "commons.wikimedia.org/wiki/File:X.jpg shows it",
            }
        )
        assert HR.parse({}, good)["verdict"] == "other_site"
        bad = json.dumps({"verdict": "other_site", "shows": "a tomb", "basis": "looks like it"})
        with pytest.raises(SG.AnswerShapeError, match="at least 3 words"):
            HR.parse({}, bad)
        no_page = json.dumps(
            {"verdict": "other_site", "shows": "the Treasury at Petra", "basis": "memory"}
        )
        with pytest.raises(SG.AnswerShapeError, match="commons.wikimedia.org"):
            HR.parse({}, no_page)
        assert (
            HR.parse({}, json.dumps({"verdict": "depicts", "shows": "x", "basis": "y"}))["verdict"]
            == "depicts"
        )

    def test_the_role_is_the_adversarial_one_and_each_round_has_its_own_files(self) -> None:
        assert (RO.role(HR.SPEC.role).model, RO.role(HR.SPEC.role).effort) == (
            "claude-opus-5-5",
            "high",
        )
        one, two = HR.spec_for_round(1), HR.spec_for_round(2)
        assert one.questions_file != two.questions_file and one.result_file != two.result_file
        assert two.name == HR.SPEC.name and two.role == HR.SPEC.role

    def test_confirmed_and_rejected_files_by_site(self) -> None:
        rows = [
            {"verdict": "depicts", "meta": {"site_id": "a", "file": "1.jpg"}},
            {"verdict": "other_site", "meta": {"site_id": "a", "file": "2.jpg"}},
            {"verdict": "region_or_type", "meta": {"site_id": "b", "file": "3.jpg"}},
        ]
        assert HR.confirmed(rows) == {"a": {"1.jpg"}}
        assert HR.rejected(rows) == {"a": {"2.jpg"}, "b": {"3.jpg"}}


# ============================================================================ targets
def _v(
    site: str,
    file: str,
    quality: int | None,
    w: int = 3000,
    h: int = 2000,
    verdict: str = "depicts",
) -> dict[str, Any]:
    return {"site_id": site, "name": "n", "file": file, "verdict": verdict, "quality": quality, "note": "n", "width": w, "height": h, "answered_by": "x", "model": "m"}  # fmt: skip


def _r(site: str, file: str, verdict: str) -> dict[str, Any]:
    return {"verdict": verdict, "meta": {"site_id": site, "file": file}}


class TestTheTargets:
    def test_the_best_quality_wins_not_the_largest_file(self) -> None:
        rows = [_v("a", "big.jpg", 3, 6000, 4000), _v("a", "sharp.jpg", 5, 2000, 1500)]
        assert [r["file"] for r in TG.ranked(rows)["a"]] == ["sharp.jpg", "big.jpg"]
        assert CJ.rank_key(rows[1]) > CJ.rank_key(rows[0])

    def test_equal_quality_goes_to_the_most_pixels_then_the_name(self) -> None:
        rows = [
            _v("a", "b.jpg", 4, 2000, 1000),
            _v("a", "a.jpg", 4, 2000, 1000),
            _v("a", "c.jpg", 4, 4000, 3000),
        ]
        assert [r["file"] for r in TG.ranked(rows)["a"]] == ["c.jpg", "a.jpg", "b.jpg"]

    def test_only_depicts_rows_are_ranked(self) -> None:
        rows = [_v("a", "x.jpg", None, verdict="other_site"), _v("b", "y.jpg", 2)]
        assert set(TG.ranked(rows)) == {"b"}

    def test_a_site_waits_for_the_recheck_of_its_best_pick(self) -> None:
        state = TG.pick_round([_v("a", "1.jpg", 5), _v("a", "2.jpg", 3)], [])
        assert [r["file"] for r in state.to_check] == ["1.jpg"] and not state.confirmed

    def test_a_confirmed_pick_ends_the_site(self) -> None:
        state = TG.pick_round(
            [_v("a", "1.jpg", 5), _v("a", "2.jpg", 3)], [_r("a", "1.jpg", "depicts")]
        )
        assert state.confirmed["a"]["file"] == "1.jpg" and not state.to_check

    def test_a_rejected_pick_passes_the_site_to_its_next_candidate(self) -> None:
        verdicts = [_v("a", "1.jpg", 5), _v("a", "2.jpg", 3)]
        state = TG.pick_round(verdicts, [_r("a", "1.jpg", "other_site")])
        assert [r["file"] for r in state.to_check] == ["2.jpg"]
        state = TG.pick_round(
            verdicts, [_r("a", "1.jpg", "other_site"), _r("a", "2.jpg", "depicts")]
        )
        assert state.confirmed["a"]["file"] == "2.jpg"

    def test_a_site_whose_every_pick_was_rejected_is_exhausted_with_the_refused(self) -> None:
        verdicts = [_v("a", "1.jpg", 5)]
        state = TG.pick_round(verdicts, [_r("a", "1.jpg", "region_or_type")])
        assert list(state.exhausted) == ["a"] and state.exhausted["a"][0]["file"] == "1.jpg"
        assert state.counts() == {"confirmed": 0, "to_check": 0, "exhausted": 1}

    def test_a_candidate_rechecked_twice_with_two_verdicts_is_refused(self) -> None:
        with pytest.raises(SG.StageError, match="twice with two verdicts"):
            TG.judged_by_recheck([_r("a", "1.jpg", "depicts"), _r("a", "1.jpg", "other_site")])

    def test_targets_are_not_written_while_a_site_waits(self, tmp_path: Path) -> None:
        with pytest.raises(SG.StageError, match="wait for a re-check round"):
            TG.write_targets(tmp_path, [_v("a", "1.jpg", 5)], [])
        assert not (tmp_path / CJ.TARGETS).exists()

    def test_the_confirmed_pick_is_written_with_its_quality(self, tmp_path: Path) -> None:
        verdicts = [_v("a", "1.jpg", 5), _v("a", "2.jpg", 3), _v("b", "3.jpg", 2)]
        rechecks = [_r("a", "1.jpg", "depicts"), _r("b", "3.jpg", "other_site")]
        summary = TG.write_targets(tmp_path, verdicts, rechecks)
        assert summary["sites_to_fetch"] == 1 and summary["exhausted"] == 1
        (line,) = (tmp_path / CJ.TARGETS).read_text(encoding="utf-8").splitlines()
        assert json.loads(line) == {
            "site_id": "a",
            "commons_file": "1.jpg",
            "width": 3000,
            "height": 2000,
            "quality": 5,
        }

    def test_the_old_judge_s_rows_keep_their_largest_file_rule(self, tmp_path: Path) -> None:
        rows = [_v("a", "small.jpg", None, 800, 600), _v("a", "big.jpg", None, 4000, 3000)]
        CJ.write_targets(tmp_path, rows)
        line = (tmp_path / CJ.TARGETS).read_text(encoding="utf-8")
        assert json.loads(line)["commons_file"] == "big.jpg" and "quality" not in line

    def test_a_confirmed_set_limits_the_eligible_candidates(self, tmp_path: Path) -> None:
        rows = [_v("a", "best.jpg", 5), _v("a", "other.jpg", 2)]
        CJ.write_targets(tmp_path, rows, {("a", "other.jpg")})
        assert (
            json.loads((tmp_path / CJ.TARGETS).read_text(encoding="utf-8"))["commons_file"]
            == "other.jpg"
        )


# ============================================================================ identity
class Store:
    """`identity.entities.EntityStore`'s `get`: `(entity, source)`."""

    def __init__(self, entities: dict[str, dict[str, Any]]) -> None:
        self.entities = entities

    def get(self, qid: str) -> tuple[dict[str, Any] | None, str | None]:
        entity = self.entities.get(qid)
        return (entity, "harvest") if entity else (None, None)


def entity(
    label: str, lat: float | None, lon: float | None, aliases: list[str] = ()
) -> dict[str, Any]:  # type: ignore[assignment]
    claims: dict[str, Any] = {}
    if lat is not None:
        claims["P625"] = [
            {
                "mainsnak": {
                    "datavalue": {"value": {"latitude": lat, "longitude": lon, "precision": 0.0001}}
                },
                "rank": "normal",
            }
        ]
    return {
        "id": "Q1",
        "labels": {"en": {"value": label}},
        "aliases": {"en": [{"value": a} for a in aliases]},
        "claims": claims,
    }


def _isite(site_id: str = "a", **over: Any) -> dict[str, Any]:
    base = {
        "site_id": site_id, "name": "Pukara de Quitor", "country": "Chile", "site_type": "Fortress",
        "lat": -22.9, "lon": -68.2, "description": "A hill fort.", "qid": "Q1", "qid_conflict": None,
        "enwiki_title": "Pukara de Quitor", "enwiki_conflict": None,
    }  # fmt: skip
    return base | over


class TestTheIdentityFlags:
    def test_an_item_far_from_the_site_is_flagged(self) -> None:
        flags = ID.verify_flags(_isite(), entity("Pukara de Quitor", -22.0, -68.2))
        assert len(flags) == 1 and "km from the site's point" in flags[0]

    def test_an_item_near_the_site_with_its_name_is_not(self) -> None:
        assert ID.verify_flags(_isite(), entity("Pukara de Quitor", -22.9, -68.21)) == []

    def test_a_label_with_no_word_of_the_name_is_flagged_unless_an_alias_has_one(self) -> None:
        site = _isite(name="Sallachy Broch")
        assert "shares no word" in ID.verify_flags(site, entity("Lairg", -22.9, -68.2))[0]
        assert (
            ID.verify_flags(site, entity("Lairg", -22.9, -68.2, aliases=["Sallachy broch"])) == []
        )

    def test_an_item_without_a_point_is_judged_by_its_label_alone(self) -> None:
        assert ID.verify_flags(_isite(), entity("Pukara de Quitor", None, None)) == []

    def test_a_site_without_an_item_has_nothing_to_verify_and_a_missing_item_is_flagged(
        self,
    ) -> None:
        assert ID.verify_flags(_isite(qid=None), None) == []
        assert "neither the harvest nor its delta" in ID.verify_flags(_isite(), None)[0]

    def test_the_verify_population_is_the_flagged_sites_with_the_items_label(self) -> None:
        store = Store({"Q1": entity("Lairg", -22.9, -68.2)})
        sites = [
            _isite("a"),
            _isite("b", qid=None),
            _isite("c", qid="Q1", qid_conflict=["Q1", "Q2"]),
        ]
        got = ID.verify_population(sites, store)
        assert [s["site_id"] for s in got] == ["a"]
        assert got[0]["item_label"] == "Lairg" and got[0]["flags"]

    def test_the_research_population_is_no_identity_or_a_first_search_with_no_file(self) -> None:
        sites = [
            _isite("a", qid=None, enwiki_title=None),
            _isite("b"),
            _isite("c", qid=None),
            _isite("d"),
        ]
        got = ID.research_population(sites, ["d"])
        assert [s["site_id"] for s in got] == ["a", "d"]


class TestTheIdentityQuestions:
    def test_batches_of_five_to_verify_and_four_to_research(self) -> None:
        sites = [_isite(str(i), flags=["f"]) for i in range(11)]
        verify = ID.build_questions(sites, mode="verify", cache=None)
        research = ID.build_questions(sites, mode="research", cache=None)
        assert [len(q.meta["sites"]) for q in verify] == [5, 5, 1]
        assert [len(q.meta["sites"]) for q in research] == [4, 4, 3]
        assert verify[0].batch_id == "idv-0001" and research[0].batch_id == "idr-0001"
        with pytest.raises(SG.StageError, match="not 'verify' or 'research'"):
            ID.build_questions(sites, mode="x", cache=None)

    def test_the_prompt_names_the_flags_the_cache_and_the_rules_for_the_web(
        self, tmp_path: Path
    ) -> None:
        cache_root = tmp_path / "wiki"
        (cache_root / "en").mkdir(parents=True)
        (cache_root / "en" / "p.json").write_text(
            json.dumps({"resolved_title": "T", "revid": 1, "text": "Text."}), encoding="utf-8"
        )
        (cache_root / "INDEX.jsonl").write_text(
            json.dumps({"site_id": "a", "lang": "en", "title": "T", "file": "en\\p.json"}) + "\n",
            encoding="utf-8",
        )
        cache = WC.WikiCache(cache_root)
        site = _isite(
            "a", flags=["the item's point is 111.0 km from the site's point"], item_label="Lairg"
        )
        (q,) = ID.build_questions([site], mode="verify", cache=cache)
        for part in (
            "S1: Pukara de Quitor",
            "flagged because: the item's point is 111.0 km",
            "'Lairg'",
            "cached Wikipedia text:",
            "p.json",
            "403 or 429 is never a finding",
            "evidence",
        ):
            assert part in q.prompt, part
        assert q.meta["sites"] == [
            {"site_id": "a", "qid": "Q1", "enwiki_title": "Pukara de Quitor"}
        ]

    def test_a_research_prompt_asks_for_item_article_category_and_local_names(self) -> None:
        (q,) = ID.build_questions(
            [_isite("a", qid=None, enwiki_title=None)], mode="research", cache=None
        )
        for part in ("Commons category", "local names", "Wikidata item"):
            assert part in q.prompt, part
        assert "flagged because" not in q.prompt


def _verdict(**over: Any) -> dict[str, Any]:
    base = {
        "qid": "Q1", "qid_status": "confirmed", "enwiki_title": "Pukara de Quitor",
        "enwiki_status": "confirmed", "commons_category": "Pukara de Quitor", "local_names": ["Pukara"],
        "evidence": ["https://www.wikidata.org/wiki/Q1"], "note": "the same fortress",
    }  # fmt: skip
    return base | over


META = {
    "mode": "verify",
    "sites": [{"site_id": "a", "qid": "Q1", "enwiki_title": "Pukara de Quitor"}],
}


class TestTheIdentityAnswers:
    def _text(self, **over: Any) -> str:
        return json.dumps({"sites": {"a": _verdict(**over)}})

    def test_a_confirmed_link_parses(self) -> None:
        got = ID.parse(META, self._text())["sites"]["a"]
        assert got["qid"] == "Q1" and got["local_names"] == ["Pukara"]

    @pytest.mark.parametrize(
        ("over", "problem"),
        [
            ({"qid": "Q-1"}, "no Wikidata item id"),
            ({"qid_status": "maybe"}, "not one of"),
            ({"evidence": []}, "needs an evidence URL"),
            ({"evidence": ["wikidata.org/wiki/Q1"]}, "https URLs"),
            ({"commons_category": "Category:Pukara"}, "without 'Category:'"),
            ({"local_names": ["x"] * 9}, "at most 8"),
            ({"local_names": [""]}, "at most 8"),
            ({"qid": "Q2"}, "must name the item the database holds"),
            ({"enwiki_title": "Other"}, "must name the article the database holds"),
            ({"qid_status": "wrong"}, "replaced by another or by null"),
        ],
    )
    def test_an_answer_out_of_shape_is_named(self, over: dict[str, Any], problem: str) -> None:
        with pytest.raises(SG.AnswerShapeError, match=problem):
            ID.parse(META, self._text(**over))

    def test_a_wrong_link_is_replaced_by_another_or_by_null(self) -> None:
        wrong = {
            "qid_status": "wrong",
            "qid": None,
            "enwiki_status": "wrong",
            "enwiki_title": None,
            "commons_category": None,
            "evidence": [],
        }
        got = ID.parse(META, self._text(**wrong))["sites"]["a"]
        assert got["qid"] is None and got["qid_status"] == "wrong"

    def test_a_null_link_with_unknown_needs_no_evidence(self) -> None:
        unknown = {
            "qid": None,
            "qid_status": "unknown",
            "enwiki_title": None,
            "enwiki_status": "unknown",
            "commons_category": None,
            "evidence": [],
            "local_names": [],
        }
        assert ID.parse(META, self._text(**unknown))["sites"]["a"]["local_names"] == []

    def test_the_answer_covers_exactly_the_sites_asked(self) -> None:
        with pytest.raises(SG.AnswerShapeError, match="must answer exactly"):
            ID.parse(META, json.dumps({"sites": {}}))

    def test_the_role_is_the_web_verifier_for_both_modes(self) -> None:
        for spec in (ID.VERIFY_SPEC, ID.RESEARCH_SPEC):
            assert (RO.role(spec.role).model, RO.role(spec.role).effort) == (
                "claude-sonnet-5-5",
                "high",
            )
            assert spec.web is True


class TestMergingTheIdentity:
    def _answer(self, **over: Any) -> dict[str, Any]:
        return {"a": _verdict(**over) | {"answered_by": "web_verifier:idv-0001", "model": "m"}}

    def test_a_confirmed_link_stays_and_the_category_and_names_are_added(self) -> None:
        (site,) = ID.merge_identity([_isite()], self._answer())
        assert site["qid"] == "Q1" and site["commons_category"] == "Pukara de Quitor"
        assert site["local_names"] == ["Pukara"] and site["identity_changed"] is False

    def test_a_wrong_item_is_replaced_and_the_change_is_marked(self) -> None:
        (site,) = ID.merge_identity([_isite()], self._answer(qid_status="wrong", qid="Q7"))
        assert site["qid"] == "Q7" and site["identity_changed"] is True

    def test_a_wrong_item_replaced_by_null_routes_nothing_through_an_item(self) -> None:
        (site,) = ID.merge_identity(
            [_isite()], self._answer(qid_status="wrong", qid=None, evidence=["https://x.org/a"])
        )
        assert site["qid"] is None

    def test_the_research_may_find_the_link_a_site_lacked(self) -> None:
        bare = _isite(qid=None, enwiki_title=None)
        (site,) = ID.merge_identity(
            [bare],
            self._answer(
                qid_status="unknown", qid="Q7", enwiki_status="unknown", enwiki_title="Quitor"
            ),
        )
        assert (site["qid"], site["enwiki_title"]) == ("Q7", "Quitor") and site["identity_changed"]

    def test_an_undecided_answer_keeps_the_database_s_link(self) -> None:
        (site,) = ID.merge_identity(
            [_isite()],
            self._answer(
                qid_status="unknown",
                qid=None,
                enwiki_status="unknown",
                enwiki_title=None,
                evidence=[],
            ),
        )
        assert (site["qid"], site["enwiki_title"]) == ("Q1", "Pukara de Quitor")

    def test_a_site_without_an_answer_is_unchanged(self) -> None:
        assert ID.merge_identity([_isite("z")], self._answer()) == [_isite("z")]

    def test_a_site_answered_twice_is_refused(self) -> None:
        row = {"sites": {"a": _verdict()}, "answered_by": "x", "model": "m"}
        with pytest.raises(SG.StageError, match="answered this site twice"):
            ID.identity_rows([row, row])


# ============================================================================= the wiki cache
class TestTheWikiCache:
    def _cache(self, tmp_path: Path) -> WC.WikiCache:
        (tmp_path / "en").mkdir()
        page = {
            "resolved_title": "T",
            "revid": 1,
            "text": "Troy is a site in Turkey. It was settled early. " + "Long. " * 200,
        }
        (tmp_path / "en" / "p.json").write_text(json.dumps(page), encoding="utf-8")
        (tmp_path / "INDEX.jsonl").write_text(
            json.dumps({"site_id": "a", "lang": "en", "title": "T", "file": "en\\p.json"})
            + "\n"
            + json.dumps({"site_id": "gone", "lang": "en", "title": "G", "file": "en\\gone.json"})
            + "\n",
            encoding="utf-8",
        )
        return WC.WikiCache(tmp_path)

    def test_the_lead_is_the_first_sentences_that_fit(self, tmp_path: Path) -> None:
        cache = self._cache(tmp_path)
        lead = cache.lead("a", 48)
        assert lead == "Troy is a site in Turkey. It was settled early."
        assert cache.lead("a", 10) == "Troy is a site in Turkey."  # the first sentence, whole
        assert cache.lead("nobody") is None

    def test_an_indexed_page_that_is_gone_is_an_error_not_no_page(self, tmp_path: Path) -> None:
        with pytest.raises(WC.WikiCacheError, match="is indexed but does not exist"):
            self._cache(tmp_path).page("gone")

    def test_a_cache_without_an_index_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(WC.WikiCacheError, match="INDEX.jsonl"):
            WC.WikiCache(tmp_path)

    def test_an_index_line_in_another_shape_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "INDEX.jsonl").write_text('{"site_id": "a"}\n', encoding="utf-8")
        with pytest.raises(WC.WikiCacheError, match="not an index line"):
            WC.WikiCache(tmp_path)

    def test_an_empty_text_has_no_lead(self) -> None:
        assert WC.lead_of("   ") is None


def test_the_hero_recheck_shares_the_served_image_question_and_its_strict_parser() -> None:
    """One re-check, two lanes: the D15 prompt and the D17 prompt are the same text."""
    assert HR.PROMPT_ID == V.CHECK_PROMPT_V2_ID
    assert (
        V.parse_check(
            json.dumps(
                {
                    "verdict": "other_site",
                    "shows": "the Treasury at Petra",
                    "basis": "commons.wikimedia.org/x",
                }
            ),
            strict=True,
        )["verdict"]
        == "other_site"
    )
