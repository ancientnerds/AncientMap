"""embed_probative_images returns the same five parts whether enabled or not."""

from types import SimpleNamespace

import pytest

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


async def test_settings_without_the_switch_are_an_error_not_a_silent_enable():
    """LyraSettings always carries probative_images_enabled; an object without it is a bug,
    never a reason to embed images by default."""
    with pytest.raises(AttributeError, match="probative_images_enabled"):
        await embed_probative_images(
            "11111111-2222-3333-4444-555555555555",
            "paper text",
            "q",
            [],
            None,
            settings=SimpleNamespace(),
        )
