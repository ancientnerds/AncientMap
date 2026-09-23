# SPDX-License-Identifier: AGPL-3.0-only
"""The shorts selector judges every image or stops: no silent 'no VLM verdict' rejects.

`judge_all` used to call the legacy `minimax_vlm`, which returns '' on every failure, so an
image whose call failed three times simply had no verdict and was rejected downstream as
'no VLM verdict' - a different short, made silently. The 16 selection.json files hold 32 such
rejections (design entry 7, item 10). It now calls `minimax_vlm_strict` and raises.

No network, no MiniMax: the client is a real `httpx.Client` over an `httpx.MockTransport`, so the
strict call runs for real against answers shaped like the coding-plan endpoint's - a 2xx whose
`base_resp` reports an error is refused here exactly as it is in production.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from pipeline.lyra import minimax_shared as mm
from pipeline.video import shorts_select as S

VERDICT = {
    "kind": "site_photo",
    "subject": "temple gate",
    "people_prominent": False,
    "text_or_overlay": False,
    "quality": 4,
    "relevance": 4,
    "illustrates": "",
    "focus": {"x": 0.5, "y": 0.5},
    "vertical_crop_ok": True,
    "other_site": False,
}


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"content": content, "base_resp": {"status_code": 0, "status_msg": "success"}}
    )


def _images(tmp_path: Path, n: int) -> list[Path]:
    paths = []
    for i in range(n):
        path = tmp_path / f"img_{i}.jpg"
        Image.new("RGB", (64, 48), (i * 40, 90, 60)).save(path, "JPEG")
        paths.append(path)
    return paths


@pytest.fixture
def vlm(monkeypatch):
    """Queue the endpoint's answers; record every request the strict call makes."""
    answers: list[httpx.Response | Exception] = []
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def client(base_url: str, api_key: str) -> httpx.Client:
        return httpx.Client(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(mm, "create_minimax_client", client)
    monkeypatch.setattr(
        S,
        "_get_settings",
        lambda: SimpleNamespace(minimax_base_url="https://vlm.invalid", minimax_api_key="k"),
    )
    monkeypatch.setattr(S, "VLM_RETRY_WAIT_S", 0.0)
    return SimpleNamespace(answers=answers, seen=seen)


def test_every_image_gets_the_verdict_the_endpoint_gave(tmp_path, vlm):
    vlm.answers += [_ok(json.dumps(VERDICT)), _ok("```json\n" + json.dumps(VERDICT) + "\n```")]
    verdicts = S.judge_all(_images(tmp_path, 2), "Temple", "The temple stands on a hill.")
    assert verdicts == [VERDICT, VERDICT]
    assert [r.url.path for r in vlm.seen] == ["/v1/coding_plan/vlm"] * 2


def test_a_transport_failure_is_retried_and_then_succeeds(tmp_path, vlm):
    vlm.answers += [httpx.ConnectError("reset"), _ok(json.dumps(VERDICT))]
    assert S.judge_all(_images(tmp_path, 1), "Temple", "text") == [VERDICT]
    assert len(vlm.seen) == 2


def test_a_failure_that_outlasts_the_retries_raises_and_names_the_image(tmp_path, vlm):
    """The old loop turned this into a None verdict and a silent 'no VLM verdict' reject."""
    vlm.answers += [_ok(json.dumps(VERDICT))] + [httpx.Response(502, text="bad gateway")] * 3
    with pytest.raises(mm.CodingPlanHTTPError) as exc:
        S.judge_all(_images(tmp_path, 2), "Temple", "text")
    assert len(vlm.seen) == 1 + S.VLM_ATTEMPTS
    assert "img_1.jpg, attempt 3/3" in "\n".join(exc.value.__notes__)


def test_a_2xx_whose_base_resp_reports_an_error_is_an_error_not_a_verdict(tmp_path, vlm):
    """The legacy wrapper read this as '' - indistinguishable from 'nothing to say'."""
    broken = httpx.Response(
        200, json={"content": "", "base_resp": {"status_code": 1027, "status_msg": "server error"}}
    )
    vlm.answers += [broken] * 3
    with pytest.raises(mm.CodingPlanResponseError):
        S.judge_all(_images(tmp_path, 1), "Temple", "text")
    assert len(vlm.seen) == S.VLM_ATTEMPTS


@pytest.mark.parametrize(
    ("answer", "error"),
    [
        (httpx.Response(401, text="invalid api key"), mm.CodingPlanAuthError),
        (
            httpx.Response(
                200,
                json={"base_resp": {"status_code": 2056, "status_msg": "usage limit exceeded"}},
            ),
            mm.CodingPlanQuotaError,
        ),
    ],
)
def test_a_dead_key_or_a_spent_budget_raises_at_once(tmp_path, vlm, answer, error):
    """No retry changes either, so the run does not wait VLM_ATTEMPTS times to learn it."""
    vlm.answers += [answer] * S.VLM_ATTEMPTS
    with pytest.raises(error):
        S.judge_all(_images(tmp_path, 1), "Temple", "text")
    assert len(vlm.seen) == 1


def test_an_answer_that_never_carries_a_json_verdict_stops_the_run(tmp_path, vlm):
    vlm.answers += [_ok("I cannot tell.")] * 3
    with pytest.raises(S.NoVerdictError) as exc:
        S.judge_all(_images(tmp_path, 1), "Temple", "text")
    assert "img_0.jpg: no JSON verdict in 3 answers" in str(exc.value)
    assert len(vlm.seen) == S.VLM_ATTEMPTS


def test_the_selector_no_longer_imports_the_empty_on_failure_wrapper():
    source = Path(S.__file__).read_text(encoding="utf-8")
    assert "minimax_vlm(" not in source
    assert "mm.minimax_vlm_strict(" in source
