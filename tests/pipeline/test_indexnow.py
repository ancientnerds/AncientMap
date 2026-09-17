# SPDX-License-Identifier: AGPL-3.0-only
"""pipeline/indexnow.py — Schluesseldatei, Payload, Chunking, Pfadbildung.

DB-los: submit() wird gegen ein gepatchtes httpx.post geprueft, die
Pfadbildung ist eine reine Funktion.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from pipeline import indexnow as ix


def test_schluesseldatei_liegt_im_frontend_public_und_traegt_den_schluessel():
    assert ix.KEY_FILE.name == f"{ix.INDEXNOW_KEY}.txt"
    assert ix.KEY_FILE.read_text(encoding="utf-8").strip() == ix.INDEXNOW_KEY
    assert len(ix.INDEXNOW_KEY) == 32


def _response(status: int) -> SimpleNamespace:
    return SimpleNamespace(status_code=status, text="")


def test_submit_schickt_host_key_keylocation_und_dedupliziert():
    with patch.object(ix.httpx, "post", return_value=_response(202)) as post:
        ok = ix.submit(
            [
                "https://ancientnerds.com/a",
                "",
                "https://ancientnerds.com/a",
                "https://ancientnerds.com/b",
            ]
        )
    assert ok is True
    post.assert_called_once()
    payload = post.call_args.kwargs["json"]
    assert payload["host"] == "ancientnerds.com"
    assert payload["key"] == ix.INDEXNOW_KEY
    assert payload["keyLocation"] == f"https://ancientnerds.com/{ix.INDEXNOW_KEY}.txt"
    assert payload["urlList"] == ["https://ancientnerds.com/a", "https://ancientnerds.com/b"]
    assert post.call_args.args[0] == ix.ENDPOINT


def test_submit_teilt_in_chunks_und_meldet_ablehnung_ohne_zu_werfen():
    urls = [f"https://ancientnerds.com/{n}" for n in range(5)]
    with (
        patch.object(ix, "CHUNK", 2),
        patch.object(
            ix.httpx, "post", side_effect=[_response(200), _response(422), _response(200)]
        ) as post,
    ):
        ok = ix.submit(urls)
    assert ok is False
    assert post.call_count == 3
    assert [len(c.kwargs["json"]["urlList"]) for c in post.call_args_list] == [2, 2, 1]


def test_submit_ueberlebt_netzfehler_und_leere_listen():
    with patch.object(ix.httpx, "post", side_effect=OSError("down")) as post:
        assert ix.submit(["https://ancientnerds.com/x"]) is False
    post.assert_called_once()
    with patch.object(ix.httpx, "post") as post:
        assert ix.submit([]) is True
    post.assert_not_called()


def test_pfade_je_gruppe_mit_hub_und_kodierung():
    paths = ix.paths_for(
        stories=[(4711, "Göbekli Tepe: new enclosure found")],
        papers=["the-egyptian-hard-stone-precision-debate"],
        journals=[],
        sites=[("Türkiye", "Göbekli Tepe", "9c8b7a65-4321-4cba-8000-111122223333")],
    )
    assert paths == [
        f"/news-archive/{ix.story_slug('Göbekli Tepe: new enclosure found', 4711)}",
        "/news-archive/",
        "/research/the-egyptian-hard-stone-precision-debate",
        "/research/",
        "/sites/türkiye/göbekli-tepe-9c8b7a65",
        "/sites/",
    ]
    assert ix.page_url("/sites/türkiye/göbekli-tepe-9c8b7a65") == (
        "https://ancientnerds.com/sites/t%C3%BCrkiye/g%C3%B6bekli-tepe-9c8b7a65"
    )


def test_nichts_geaendert_ergibt_keine_pfade():
    assert ix.paths_for([], [], [], []) == []
