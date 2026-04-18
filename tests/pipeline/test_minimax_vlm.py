"""Unit tests for the minimax_vlm() helper — mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock

from pipeline.lyra.minimax_shared import minimax_vlm


def test_minimax_vlm_posts_to_vlm_endpoint_with_data_uri():
    client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"content": '{"verdict":"accept"}', "base_resp": {}}
    client.post.return_value = mock_resp

    image_bytes = b"\xff\xd8\xff\xe0fake-jpeg"
    result = minimax_vlm(client, image_bytes, "is this a bronze disc?")

    # Asserts: endpoint path, JSON shape, data URI scheme
    client.post.assert_called_once()
    path, kwargs = client.post.call_args[0][0], client.post.call_args[1]
    assert path == "/v1/coding_plan/vlm"
    body = kwargs["json"]
    assert body["prompt"] == "is this a bronze disc?"
    assert body["image_url"].startswith("data:image/jpeg;base64,")
    assert result == '{"verdict":"accept"}'


def test_minimax_vlm_returns_empty_on_http_error():
    client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "rate limited"
    client.post.return_value = mock_resp

    result = minimax_vlm(client, b"fake", "prompt")
    assert result == ""
