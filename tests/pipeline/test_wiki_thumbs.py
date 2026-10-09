"""pipeline.wiki_thumbs: the gallery thumbnails beside the wiki images."""

import os

from PIL import Image

from pipeline import wiki_thumbs as wt


def _image(path, width, height=300, color=(120, 80, 40)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (width, height), color).save(path, "WEBP")
    return path


def _trees(tmp_path):
    return tmp_path / "wiki", tmp_path / "wiki-thumbs"


def test_a_wide_image_gets_a_thumbnail_of_the_gallery_width(tmp_path):
    wiki, thumbs = _trees(tmp_path)
    _image(wiki / "d953e9b3" / "Göbekli Tepe, Urfa.webp", 1600, 1062)

    result = wt.sync(wiki, thumbs, workers=1)

    thumb = thumbs / "d953e9b3" / "Göbekli Tepe, Urfa.webp"
    with Image.open(thumb) as im:
        assert (im.width, im.height) == (wt.THUMB_WIDTH, round(1062 * wt.THUMB_WIDTH / 1600))
    assert result == wt.SyncResult(written=1, unchanged=0, narrow=0, removed=0)


def test_a_narrow_image_gets_none_and_a_second_run_changes_nothing(tmp_path):
    """nginx serves the image itself where no thumbnail exists."""
    wiki, thumbs = _trees(tmp_path)
    _image(wiki / "aaaaaaaa" / "small.webp", 300)
    _image(wiki / "aaaaaaaa" / "wide.webp", 2000)

    first = wt.sync(wiki, thumbs, workers=1)
    second = wt.sync(wiki, thumbs, workers=1)

    assert not (thumbs / "aaaaaaaa" / "small.webp").exists()
    assert first == wt.SyncResult(written=1, unchanged=0, narrow=1, removed=0)
    # The narrow one is looked at again (it has no thumbnail to compare), the wide one not.
    assert second == wt.SyncResult(written=0, unchanged=1, narrow=1, removed=0)


def test_a_replaced_image_gets_a_new_thumbnail(tmp_path):
    """A hero swap writes a new file under the same name: newer than its thumbnail."""
    wiki, thumbs = _trees(tmp_path)
    image = _image(wiki / "bbbbbbbb" / "hero.webp", 1600, color=(0, 0, 0))
    wt.sync(wiki, thumbs, workers=1)
    thumb = thumbs / "bbbbbbbb" / "hero.webp"
    old = thumb.stat().st_mtime
    _image(image, 1600, color=(255, 255, 255))
    os.utime(image, (old + 10, old + 10))

    assert wt.sync(wiki, thumbs, workers=1).written == 1
    with Image.open(thumb) as im:
        assert im.getpixel((10, 10))[0] > 200


def test_a_thumbnail_goes_when_its_image_goes_or_turns_narrow(tmp_path):
    """No thumbnail may show a picture its image no longer has."""
    wiki, thumbs = _trees(tmp_path)
    gone = _image(wiki / "cccccccc" / "gone.webp", 1600)
    shrunk = _image(wiki / "cccccccc" / "shrunk.webp", 1600)
    wt.sync(wiki, thumbs, workers=1)
    gone.unlink()
    _image(shrunk, 400)
    t = (thumbs / "cccccccc" / "shrunk.webp").stat().st_mtime
    os.utime(shrunk, (t + 10, t + 10))

    result = wt.sync(wiki, thumbs, workers=1)

    assert not (thumbs / "cccccccc" / "gone.webp").exists()
    assert not (thumbs / "cccccccc" / "shrunk.webp").exists()
    assert result.removed == 1 and result.narrow == 1
