"""Replace mode for the probative-image backfill.

The backfill was built to fill papers that have NO images. Re-running the
reworked image pipeline over papers that already have (poor) ones needs the
old blocks removed first — including the gallery captions that sit detached
from any image, which is how the Yonaguni caption survived an earlier sweep.
"""

from __future__ import annotations

from pipeline.lyra.backfill_probative_images import _strip_inline_images

REPORT = """# Paper

Some prose about superflares [1].

![Terrace](/data/research-images/x/p2_terrace.jpg)

*Main Terrace. Photo: Melkov / Wikimedia Commons. A part of the monument.*
[Source](https://commons.wikimedia.org/wiki/File:Terrace.jpg)

*Ryukyu no Kaze. Photo: Paipateroma / Wikimedia Commons. A monument.*
[Source](https://commons.wikimedia.org/wiki/File:Kaze.jpg)

More prose that must survive [2].

## References

[1] A — https://a.example
[2] B — https://b.example
"""


def test_strip_removes_image_blocks_and_detached_captions():
    out = _strip_inline_images(REPORT)
    assert "/data/research-images/" not in out
    assert "Photo:" not in out
    assert "[Source]" not in out


def test_strip_keeps_prose_and_references():
    out = _strip_inline_images(REPORT)
    assert "Some prose about superflares [1]." in out
    assert "More prose that must survive [2]." in out
    assert "## References" in out
    assert "[1] A — https://a.example" in out


def test_strip_leaves_a_cover_image_alone():
    """`![Cover ...]` is the banner, not a probative image — the backfill
    replaces the evidence gallery, not the paper's own artwork."""
    md = "# T\n\n![Cover art](/data/research-images/x/cover.jpg)\n\nProse [1].\n"
    out = _strip_inline_images(md)
    assert "cover.jpg" in out


def test_strip_is_a_noop_on_a_paper_without_images():
    md = "# T\n\nJust prose [1].\n\n## References\n\n[1] A — https://a.example\n"
    assert _strip_inline_images(md) == md


def test_strip_does_not_eat_ordinary_italics():
    """Only captions carrying `Photo:` are attribution lines."""
    md = "# T\n\nThe word *emphasis* matters here [1].\n"
    assert "*emphasis*" in _strip_inline_images(md)
