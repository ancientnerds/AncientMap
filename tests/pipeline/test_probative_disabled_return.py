"""embed_probative_images returns the same five parts whether enabled or not."""

from types import SimpleNamespace

from pipeline.lyra.handlers.probative_images import embed_probative_images


async def test_disabled_embed_returns_five_parts_like_an_enabled_one():
    out = await embed_probative_images(
        "11111111-2222-3333-4444-555555555555",
        "paper text",
        "q",
        [],
        None,
        settings=SimpleNamespace(probative_images_enabled=False),
    )
    assert out == ("paper text", [], {}, {}, {})
