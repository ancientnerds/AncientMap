"""The rounds of an identity stage and the shared Wikipedia cache they read.

`identity/rounds.py` exports a stage's questions into a handoff directory, reads the agents' answers
back against the prompts rebuilt from the data, and refuses an answer that is not the role's (no role,
the wrong role, the wrong model, a MiniMax stamp). `identity/wiki.py` is the cache of the article of
every shown site: the questions name its files, the import reads a cited article from it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

import opus_handoff as OH  # noqa: E402
from identity import rounds, wiki  # noqa: E402
from opus_audit import quotes as Q  # noqa: E402

from tests.remediation.identity_fixtures import CALIBRATED, passed_calibrations  # noqa: E402

SONNET = OH.ANSWER_MODELS["claude-sonnet-5-5"]
OPUS = OH.ANSWER_MODELS["claude-opus-5-5"]
HAIKU = OH.ANSWER_MODELS["claude-haiku-5-5"]
MINIMAX = OH.MINIMAX_MODEL
STAGE = "dup-verdict"
NOW = "2026-10-10T00:00:00+00:00"


def prompt_of(label: str, earlier: str | None) -> str:
    return f"question {label}" + (f" / {earlier}" if earlier else "")


def answer(model: str = SONNET, by: str = "web_verifier:b1") -> OH.Answer:
    return OH.Answer(text="{}", answered_by=by, answered_at=NOW, model=model)


# ------------------------------------------------------------------------------------- wiki
class TestTheWikiCache:
    def cache(self, tmp_path: Path, pages: list[dict[str, Any]]) -> wiki.WikiIndex:
        root = tmp_path / "wiki_cache"
        lines = []
        for i, page in enumerate(pages):
            path = root / page["lang"] / f"{i}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({k: v for k, v in page.items() if k != "site_id"}), encoding="utf-8"
            )
            lines.append(
                {
                    "site_id": page["site_id"],
                    "lang": page["lang"],
                    "title": page["title"],
                    "file": f"{page['lang']}\\{i}.json",
                }
            )
        (root / "INDEX.jsonl").write_text(
            "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8"
        )
        return wiki.WikiIndex.load(root)

    def page(self, site: str, lang: str, title: str, **over: Any) -> dict[str, Any]:
        return {
            "site_id": site,
            "lang": lang,
            "title": title,
            "resolved_title": title,
            "fetched_at": "2026-10-08",
            "text": f"{title} text",
            **over,
        }

    def test_a_sites_pages_come_english_first(self, tmp_path: Path) -> None:
        index = self.cache(
            tmp_path, [self.page("s1", "fr", "Banias"), self.page("s1", "en", "Banias")]
        )
        assert [p.lang for p in index.site_pages("s1")] == ["en", "fr"]
        assert index.site_pages("nobody") == []

    def test_a_missing_page_is_not_a_page(self, tmp_path: Path) -> None:
        index = self.cache(tmp_path, [self.page("s1", "en", "Banias", missing=True)])
        assert index.site_pages("s1") == []
        assert index.for_url("https://en.wikipedia.org/wiki/Banias") is None

    def test_a_cited_article_is_found_by_its_url_or_its_resolved_title(
        self, tmp_path: Path
    ) -> None:
        index = self.cache(tmp_path, [self.page("s1", "en", "Banias_old", resolved_title="Banias")])
        by_url = index.for_url("https://en.wikipedia.org/wiki/Banias")
        assert by_url is not None and by_url.text() == "Banias_old text"
        assert index.for_url("https://en.wikipedia.org/wiki/Banias_old") is by_url
        assert index.for_url("https://de.wikipedia.org/wiki/Banias") is None
        assert index.for_url("https://example.org/wiki/Banias") is None

    def test_the_url_of_an_article_round_trips(self) -> None:
        url = wiki.article_url("en", "Theatre of Marcellus (Rome)")
        assert url == "https://en.wikipedia.org/wiki/Theatre_of_Marcellus_(Rome)"
        assert wiki.url_page(url) == ("en", "Theatre of Marcellus (Rome)")
        assert wiki.url_page("https://en.wikipedia.org/wiki/%C3%91usta_Hispana") == (
            "en",
            "Ñusta Hispana",
        )
        assert wiki.url_page("https://www.wikidata.org/wiki/Q1") is None

    def test_an_index_naming_a_file_the_cache_lacks_is_an_error(self, tmp_path: Path) -> None:
        root = tmp_path / "wiki_cache"
        root.mkdir()
        (root / "INDEX.jsonl").write_text(
            json.dumps({"site_id": "s", "lang": "en", "title": "T", "file": "en\\0.json"}) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(
            FileNotFoundError, match="the index names a page the cache does not hold"
        ):
            wiki.WikiIndex.load(root)

    def test_the_cache_is_stored_as_the_text_the_agent_read(self, tmp_path: Path) -> None:
        index = self.cache(
            tmp_path,
            [self.page("s1", "en", "Banias", text="Banias, also known as Caesarea Philippi.")],
        )
        pages = tmp_path / "pages"
        url = "https://en.wikipedia.org/wiki/Banias"

        def never(urls: list[str], store: Path) -> dict[str, int]:
            raise AssertionError("fetched")

        assert rounds.keep_pages(pages, [url], index, never, now=lambda: NOW) == {"cache": 1}
        library = Q.Library(REPO, pages)
        assert (
            Q.check_quote(
                {"source": url, "quote": "also known as Caesarea Philippi"},
                {"change_key": "k", "evidence_files": []},
                library,
            ).outcome
            == Q.FOUND
        )
        meta = json.loads((pages / f"{Q.url_key(url)}.json").read_text(encoding="utf-8"))
        assert meta["fetched_at"] == "2026-10-08" and meta["content_type"].startswith("text/plain")

    def test_an_uncached_url_is_fetched_once_and_a_cached_one_not_again(
        self, tmp_path: Path
    ) -> None:
        index = self.cache(tmp_path, [self.page("s1", "en", "Banias")])
        calls: list[list[str]] = []

        def fetch(urls: list[str], store: Path) -> dict[str, int]:
            calls.append(urls)
            return {"fetched": len(urls)}

        out = rounds.keep_pages(
            tmp_path / "p",
            ["https://en.wikipedia.org/wiki/Banias", "https://example.org/a"],
            index,
            fetch,
        )
        assert out == {"cache": 1, "fetched": 1} and calls == [["https://example.org/a"]]
        rounds.keep_pages(tmp_path / "p", ["https://en.wikipedia.org/wiki/Banias"], index, fetch)
        assert calls == [["https://example.org/a"]]

    def test_without_a_cache_every_url_is_fetched(self, tmp_path: Path) -> None:
        out = rounds.keep_pages(
            tmp_path / "p",
            ["https://en.wikipedia.org/wiki/Banias"],
            None,
            lambda urls, store: {"fetched": len(urls)},
        )
        assert out == {"cache": 0, "fetched": 1}


# ---------------------------------------------------------------------------------- the roles
class TestTheRoleOfAnAnswer:
    @pytest.mark.parametrize(
        ("model", "by", "allowed", "message"),
        [
            (SONNET, "web_verifier:b1", ("web_verifier",), None),
            (OPUS, "adversarial:b1", ("adversarial", "pilot_judge"), None),
            (OPUS, "pilot_judge:b1", ("adversarial", "pilot_judge"), None),
            (MINIMAX, "web_verifier:b1", ("web_verifier",), "never ground truth"),
            (MINIMAX, "b1", ("web_verifier",), "never ground truth"),
            (SONNET, "b1", ("web_verifier",), "names no role"),
            (SONNET, "unknown:b1", ("web_verifier",), "names no role"),
            (OPUS, "adversarial:b1", ("web_verifier",), "this stage asks web_verifier"),
            (
                SONNET,
                "adversarial:b1",
                ("adversarial", "pilot_judge"),
                "is registered to claude-opus-5-5",
            ),
            (OPUS, "web_verifier:b1", ("web_verifier",), "is registered to claude-sonnet-5-5"),
            (HAIKU, "web_verifier:b1", ("web_verifier",), "is registered to claude-sonnet-5-5"),
        ],
    )
    def test_each_case(
        self, model: str, by: str, allowed: tuple[str, ...], message: str | None
    ) -> None:
        problem = rounds.role_problem(answer(model, by), allowed)
        if message is None:
            assert problem is None
        else:
            assert problem is not None and message in problem


# ------------------------------------------------------------------------- the calibrations
class TestTheCalibrationGate:
    """D6: a role's answers count only after a sealed calibration of that role passed."""

    def root(self, tmp_path: Path) -> Path:
        root = tmp_path / "calibration"
        passed_calibrations(root)
        return root

    def check(
        self, tmp_path: Path, roles: Any = ("web_verifier",), calibrations: Any = None
    ) -> None:
        rounds.check_calibrated(
            roles, CALIBRATED if calibrations is None else calibrations, self.root(tmp_path)
        )

    def test_a_passed_sealed_calibration_of_the_role_counts(self, tmp_path: Path) -> None:
        self.check(tmp_path, ["web_verifier", "adversarial", "web_verifier"])

    def test_a_role_without_a_named_calibration_does_not(self, tmp_path: Path) -> None:
        with pytest.raises(rounds.RoundError, match="role adversarial answered"):
            self.check(tmp_path, ["adversarial"], {"web_verifier": "cal-web_verifier"})

    def test_a_calibration_without_a_verdict_does_not(self, tmp_path: Path) -> None:
        root = self.root(tmp_path)
        (root / "verdicts" / "cal-web_verifier.json").unlink()
        with pytest.raises(rounds.RoundError, match="has no verdict"):
            rounds.check_calibrated(["web_verifier"], CALIBRATED, root)

    def test_a_failed_verdict_does_not(self, tmp_path: Path) -> None:
        root = self.root(tmp_path)
        path = root / "verdicts" / "cal-web_verifier.json"
        path.write_text(
            json.dumps({"role": "web_verifier", "passed": False, "held": "the owner decides"}),
            encoding="utf-8",
        )
        with pytest.raises(rounds.RoundError, match="did not pass"):
            rounds.check_calibrated(["web_verifier"], CALIBRATED, root)

    def test_another_role_s_calibration_does_not(self, tmp_path: Path) -> None:
        with pytest.raises(rounds.RoundError, match="calibration of role adversarial, not of"):
            self.check(tmp_path, ["web_verifier"], {"web_verifier": "cal-adversarial"})

    def test_a_role_whose_registry_entry_changed_after_the_seal_does_not(
        self, tmp_path: Path
    ) -> None:
        root = self.root(tmp_path)
        seals = json.loads((root / "THRESHOLDS.json").read_text(encoding="utf-8"))
        seals["cal-web_verifier"]["role_sha256"] = "0" * 64
        (root / "THRESHOLDS.json").write_text(json.dumps(seals), encoding="utf-8")
        with pytest.raises(rounds.RoundError, match="changed after the seal"):
            rounds.check_calibrated(["web_verifier"], CALIBRATED, root)

    def test_a_verdict_without_a_seal_does_not(self, tmp_path: Path) -> None:
        root = self.root(tmp_path)
        (root / "THRESHOLDS.json").write_text("{}", encoding="utf-8")
        with pytest.raises(rounds.RoundError, match="is not sealed"):
            rounds.check_calibrated(["web_verifier"], CALIBRATED, root)

    def test_the_flag_is_role_equals_id(self) -> None:
        assert rounds.parse_calibrations(["a=b", "c=d"]) == {"a": "b", "c": "d"}
        for bad in (["x"], ["=y"], ["x="], ["a=b", "a=c"]):
            with pytest.raises(rounds.RoundError):
                rounds.parse_calibrations(bad)


# ---------------------------------------------------------------------------------- the rounds
class TestTheRoundFiles:
    def export(
        self, tmp_path: Path, labels: list[str], name: str = "h1", **kw: Any
    ) -> rounds.Round:
        return rounds.export_round(
            tmp_path / "run",
            STAGE,
            labels,
            prompt_of,
            tmp_path / name,
            basis="b",
            now=lambda: NOW,
            **kw,
        )

    def test_the_batches_hold_five_questions_in_label_order(self) -> None:
        grouped = rounds.batches([f"c{n}" for n in (3, 1, 2, 5, 4, 7, 6)], "r1")
        assert grouped == {"r1-b01": ["c1", "c2", "c3", "c4", "c5"], "r1-b02": ["c6", "c7"]}
        with pytest.raises(rounds.RoundError, match="at least one question"):
            rounds.batches(["a"], "r1", 0)

    def test_an_export_writes_the_prompts_the_manifest_and_the_round(self, tmp_path: Path) -> None:
        record = self.export(tmp_path, ["c2", "c1"])
        assert (
            record.name == "r1"
            and record.batches == {"r1-b01": ["c1", "c2"]}
            and record.basis == "b"
        )
        manifest = OH.read_manifest(tmp_path / "h1", "r1-b01")
        assert sorted(label for _stage, label in manifest) == ["c1", "c2"]
        first = tmp_path / "h1" / manifest[(STAGE, "c1")]["prompt_path"]
        assert first.read_text(encoding="utf-8") == "question c1"
        assert rounds.load_rounds(tmp_path / "run", STAGE) == [record]
        assert rounds.find_round(tmp_path / "run", STAGE, "r1") == record

    def test_no_question_and_a_label_asked_twice_are_refused(self, tmp_path: Path) -> None:
        with pytest.raises(rounds.RoundError, match="nothing to export"):
            self.export(tmp_path, [])
        with pytest.raises(rounds.RoundError, match="asked twice"):
            self.export(tmp_path, ["c1", "c1"])

    def test_a_reask_needs_a_round_to_re_ask(self, tmp_path: Path) -> None:
        with pytest.raises(rounds.RoundError, match="no dup-verdict round is exported yet"):
            rounds.newest_imported(tmp_path / "run", STAGE, "a re-ask")

    def test_an_unknown_round_is_named(self, tmp_path: Path) -> None:
        with pytest.raises(rounds.RoundError, match="no round 'r9'"):
            rounds.find_round(tmp_path / "run", STAGE, "r9")

    def test_the_earlier_reason_reaches_the_prompt(self, tmp_path: Path) -> None:
        self.export(tmp_path, ["c1"], earlier={"c1": "why"})
        manifest = OH.read_manifest(tmp_path / "h1", "r1-b01")
        assert (tmp_path / "h1" / manifest[(STAGE, "c1")]["prompt_path"]).read_text(
            encoding="utf-8"
        ) == "question c1 / why"

    def test_the_first_round_asks_everything_and_a_reask_the_held(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        assert rounds.labels_for_round(run, STAGE, ["b", "a"]) == (["a", "b"], {})
        self.export(tmp_path, ["a", "b"])
        with pytest.raises(rounds.RoundError, match="exported but not imported"):
            rounds.labels_for_round(run, STAGE, ["a"])
        stage = run / STAGE
        (stage / rounds.ANSWERS_DIR).mkdir(parents=True)
        (stage / rounds.ANSWERS_DIR / "r1.jsonl").write_text("", encoding="utf-8")
        (stage / rounds.DECISIONS_FILE).write_text(
            json.dumps({"label": "a", "status": "held", "reason": "r"})
            + "\n"
            + json.dumps({"label": "b", "status": "decided", "reason": ""})
            + "\n",
            encoding="utf-8",
        )
        assert rounds.labels_for_round(run, STAGE, ["a", "b"]) == (["a"], {"a": "r"})

    def test_a_label_decided_in_a_later_verdict_round_joins_the_next_recheck(
        self, tmp_path: Path
    ) -> None:
        """Recheck round 1 asked A; B became decided only in verdict round 2: the next recheck
        round asks B (never rechecked) and A's held recheck, not A's decided one."""
        run = tmp_path / "run"
        self.export(tmp_path, ["a"])
        stage = run / STAGE
        (stage / rounds.ANSWERS_DIR).mkdir(parents=True)
        (stage / rounds.ANSWERS_DIR / "r1.jsonl").write_text("", encoding="utf-8")
        decided = {"label": "a", "status": "decided", "reason": ""}
        (stage / rounds.DECISIONS_FILE).write_text(json.dumps(decided) + "\n", encoding="utf-8")
        assert rounds.labels_for_round(run, STAGE, ["a", "b"]) == (["b"], {})
        held = {"label": "a", "status": "held", "reason": "r"}
        (stage / rounds.DECISIONS_FILE).write_text(json.dumps(held) + "\n", encoding="utf-8")
        assert rounds.labels_for_round(run, STAGE, ["a", "b"]) == (["a", "b"], {"a": "r"})

    def test_only_the_newest_round_is_importable(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        self.export(tmp_path, ["a"])
        assert rounds.check_importable(run, STAGE, "r1").name == "r1"
        stage = run / STAGE
        (stage / rounds.ANSWERS_DIR).mkdir(parents=True)
        (stage / rounds.ANSWERS_DIR / "r1.jsonl").write_text("", encoding="utf-8")
        self.export(tmp_path, ["a"], name="h2")
        with pytest.raises(rounds.RoundError, match="is not the newest"):
            rounds.check_importable(run, STAGE, "r1")

    def test_the_answers_are_read_against_the_prompt_rebuilt_from_the_data(
        self, tmp_path: Path
    ) -> None:
        record = self.export(tmp_path, ["c1"])
        OH.write_answer(
            tmp_path / "h1",
            batch_id="r1-b01",
            stage=STAGE,
            label="c1",
            text="{}",
            answered_by="web_verifier:b1",
            model=SONNET,
        )
        got = rounds.read_answers(tmp_path / "run", STAGE, record, prompt_of, root=tmp_path)
        assert got["c1"].answered_by == "web_verifier:b1"
        with pytest.raises(OH.HandoffError, match="stale"):
            rounds.read_answers(
                tmp_path / "run",
                STAGE,
                record,
                lambda label, earlier: "another prompt",
                root=tmp_path,
            )

    def test_unanswered_questions_stop_the_read(self, tmp_path: Path) -> None:
        record = self.export(tmp_path, ["c1"])
        with pytest.raises(rounds.RoundError, match="1 missing"):
            rounds.read_answers(tmp_path / "run", STAGE, record, prompt_of, root=tmp_path)

    def test_the_shape_held_label_carries_its_reason(self) -> None:
        held = rounds.shape_held("c1", "r1", "b", "not JSON")
        assert held == {
            "label": "c1",
            "status": "held",
            "reason": "shape: not JSON",
            "round": "r1",
            "answered_by": "b",
            "members": [],
        }

    def test_the_quote_helpers_are_the_shape_rules_of_every_stage(self) -> None:
        assert rounds.parse_quotes([{"source": "https://example.org/a", "quote": "q"}], "w") == (
            {"source": "https://example.org/a", "quote": "q"},
        )
        for bad, message in (
            ("x", "quotes is not a list"),
            (None, "quotes is not a list"),
            (3, "quotes is not a list"),
            ([1], "is not {source, quote}"),
            ([{"source": "https://example.org/a"}], "is not {source, quote}"),
            ([{"source": "https://example.org/a", "quote": " "}], "needs a source and a text"),
            ([{"source": "Wikipedia", "quote": "q"}], "must be the URL of the page"),
            ([{"source": "https://ancientnerds.com/a", "quote": "q"}], "is never fetched here"),
        ):
            with pytest.raises(rounds.AnswerError, match=message):
                rounds.parse_quotes(bad, "w")
        assert rounds.quote_outcomes([], "k", Q.Library(REPO, Path("."))) == ([], None)
