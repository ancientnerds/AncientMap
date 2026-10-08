"""D18: the INSERT waves' credit refusals are found again and grouped by their source wave."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from import_hero import credit_refusals as CR  # noqa: E402

A, B, C, D = (f"{n}" * 8 + "-0000-0000-0000-000000000000" for n in "abcd")


def _wave(root: Path, name: str, failures: list[tuple[str, str]], fetched: list[str] = ()) -> Path:
    wave = root / name
    wave.mkdir(parents=True)
    (wave / CR.FAILURES).write_text(
        "".join(
            json.dumps({"site_id": sid, "commons_file": "X.jpg", "why": why}) + "\n"
            for sid, why in failures
        ),
        encoding="utf-8",
    )
    (wave / CR.FETCHED).write_text(json.dumps({s: {} for s in fetched}), encoding="utf-8")
    return wave


OLD = "the fetch failed: {sid}: the fetch of 'X.jpg' names no {cols}: the imageinfo answer carries"
NEW = "the fetch failed: s: the fetch of 'X.jpg' names no {cols}, which the licence 'L' demands (a)"


class TestWhatIsACreditRefusal:
    @pytest.mark.parametrize(
        ("why", "columns"),
        [
            (OLD.format(sid=A, cols="author_url"), ("author_url",)),
            (OLD.format(sid=A, cols="author_url, license_url"), ("author_url", "license_url")),
            (NEW.format(cols="author"), ("author",)),
            ("the fetch failed: the original of 'x.jpg' is 3x3", None),
        ],
    )
    def test_the_columns_a_refusal_names(self, why: str, columns: tuple[str, ...] | None) -> None:
        assert CR.named_columns(why) == columns

    def test_only_credit_columns_make_a_credit_refusal(self) -> None:
        assert CR.is_credit_refusal(OLD.format(sid=A, cols="author_url"))
        assert not CR.is_credit_refusal(OLD.format(sid=A, cols="filename, author_url"))
        assert not CR.is_credit_refusal("the fetch failed: arrived 2560 px wide")


class TestTheSitesToAskAgain:
    def test_every_site_whose_latest_refusal_is_a_credit_one_is_named(self, tmp_path: Path) -> None:
        _wave(tmp_path, "insert-2026-10-07-001", [(A, OLD.format(sid=A, cols="author_url"))])
        _wave(
            tmp_path,
            "insert-2026-10-07-002",
            [
                (B, OLD.format(sid=B, cols="author_url, license_url")),
                (C, "the fetch failed: arrived 2560 px wide"),
            ],
        )
        assert CR.credit_refusals(tmp_path) == [A, B]

    def test_a_site_a_later_wave_fetched_is_not_asked_again(self, tmp_path: Path) -> None:
        _wave(tmp_path, "insert-2026-10-07-001", [(A, OLD.format(sid=A, cols="author_url"))])
        _wave(tmp_path, "insert-2026-10-07-002", [], fetched=[A])
        assert CR.credit_refusals(tmp_path) == []

    def test_a_retried_site_counts_by_its_latest_refusal(self, tmp_path: Path) -> None:
        _wave(tmp_path, "insert-2026-10-07-001", [(A, OLD.format(sid=A, cols="author_url"))])
        _wave(tmp_path, "insert-2026-10-07-002", [(A, "the fetch failed: arrived 2560 px wide")])
        assert CR.credit_refusals(tmp_path) == []

    def test_a_root_without_a_wave_is_refused_by_name(self, tmp_path: Path) -> None:
        with pytest.raises(CR.CreditRefusalError, match="no insert"):
            CR.credit_refusals(tmp_path)

    def test_the_sites_split_by_the_source_that_holds_their_file(self, tmp_path: Path) -> None:
        (tmp_path / CR.TARGETS).write_text(
            json.dumps({"site_id": A, "commons_file": "X.jpg"}) + "\n", encoding="utf-8"
        )
        assert CR.by_source([A, D], tmp_path) == ([A], [D])
        with pytest.raises(CR.CreditRefusalError, match="TARGETS"):
            CR.by_source([A], tmp_path / "nowhere")

    def test_each_source_gets_its_own_wave_and_its_own_seed(self) -> None:
        both = CR.commands(
            Path("cand"), Path("insert-2026-10-09"), Path("c.txt"), Path("i.txt"), Path("imp")
        )
        assert any(
            "insert-claims --run-dir cand --insert-run insert-2026-10-09-cand --sites c.txt" in x
            for x in both
        )
        assert any(
            "insert-seed --run-dir insert-2026-10-09-import --from-run imp --sites i.txt" in x
            for x in both
        )
        assert all("--min-width 800 --min-height 300" in x for x in both if " fetch " in x)
        only = CR.commands(Path("c"), Path("w"), Path("c.txt"), None, Path("imp"))
        assert not any("insert-seed" in x for x in only)
