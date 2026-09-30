"""Mapbox Static top-down frames (pipeline/studio/capture/mapbox.py); the HTTP call is faked."""

import io

import httpx
import pytest

from pipeline.studio.capture import mapbox
from pipeline.studio.capture.manifest import (
    CREDIT_MAPBOX_SATELLITE,
    CREDIT_MAPBOX_STREETS,
    CaptureError,
)

SPEC = {
    "id": "td1",
    "kind": "mapbox_topdown",
    "center": {"lat": 34.0029, "lng": 36.2018},
    "zoom": 15.0,
    "bearing": 0,
    "style": "satellite-v9",
    "width": 1280,
    "height": 720,
    "pins": [
        {"id": "p2", "label": "Quarry", "lat": 33.99917, "lng": 36.20028},
        {"id": "p1", "label": "Temple of Jupiter", "lat": 34.00667, "lng": 36.20333},
    ],
}


def test_static_url_asks_for_the_exact_retina_view():
    assert mapbox.static_url(SPEC, "pk.test") == (
        "https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/36.201800,34.002900,15.00,0.0,0/"
        "1280x720@2x?attribution=false&logo=false&access_token=pk.test"
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"center": {"lat": 34.0}}, "center must be"),
        ({"zoom": 23}, "zoom 23.0 outside"),
        ({"bearing": 360}, "bearing 360.0 outside"),
        ({"width": 1281}, "Static API limit"),
        ({"style": "dark-v11"}, "style 'dark-v11' not in"),
        ({"zoom": "15"}, "td1: zoom must be a number, got '15'"),
        ({"pitch": 30}, r"td1: unknown keys \['pitch'\]"),
    ],
)
def test_bad_views_are_rejected(changes, message):
    with pytest.raises(CaptureError, match=message):
        mapbox.static_url({**SPEC, **changes}, "pk.test")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        # a coordinate, but past the Web Mercator latitude the Static API draws
        ({"center": {"lat": 86.0, "lng": 0.0}}, r"td1: center latitude 86\.0 outside the Web "),
        ({"center": {"lat": 34.0, "lng": 181.0}}, r"td1: center: \(34\.0, 181\.0\) is not a"),
        # the renderer cover-fits the frame to 1920x1080: any other aspect is cropped, and a
        # pin inside the band can land off the screen
        ({"width": 1280, "height": 1280}, r"td1: 1280x1280 is not 16:9"),
    ],
)
def test_views_the_frame_cannot_show_whole_are_rejected(changes, message):
    with pytest.raises(CaptureError, match=message):
        mapbox.pin_events({**SPEC, **changes})


def _view_of(url):
    """(lng, lat, zoom, bearing) the Static API URL asks for."""
    lng, lat, zoom, bearing, _pitch = url.split("/static/")[1].split("/")[0].split(",")
    return float(lng), float(lat), float(zoom), float(bearing)


def test_pins_are_projected_for_the_view_the_url_asks_for():
    # the URL (and Mapbox itself) carries the zoom to 2 decimals, the bearing to 1, the
    # centre to 6: the pins are projected for exactly that view, not for the spec's digits
    spec = {
        **SPEC,
        "zoom": 14.8449,
        "bearing": 2.3456,
        "center": {"lat": 34.00290049, "lng": 36.2018},
    }
    lng, lat, zoom, bearing = _view_of(mapbox.static_url(spec, "pk.test"))
    assert (zoom, bearing) == (14.84, 2.3)
    asked = {**spec, "center": {"lat": lat, "lng": lng}, "zoom": zoom, "bearing": bearing}
    assert mapbox.pin_events(spec) == mapbox.pin_events(asked)
    # a bearing that rounds up to a full turn is north up, as 0
    assert _view_of(mapbox.static_url({**SPEC, "bearing": 359.97}, "pk.test"))[3] == 0.0


@pytest.mark.parametrize(
    ("pins", "message"),
    [
        (
            [SPEC["pins"][0], {**SPEC["pins"][1], "id": "p2"}],
            r"td1: pin ids must be unique, p2 is there twice",
        ),
        ([{**SPEC["pins"][0], "label": None}], r"event 'pin': label must be a non-empty string"),
        ([{**SPEC["pins"][0], "id": 7}], r"event 'pin': target must be a non-empty string"),
        ([{**SPEC["pins"][0], "lng": 396.2}], r"td1: pins\[0\]: \(33\.99917, 396\.2\) is not a"),
        ([{**SPEC["pins"][0], "lat": "34"}], r"td1: pins\[0\]\.lat must be a number"),
    ],
)
def test_pins_are_checked_like_the_case_file_places_they_stand_for(pins, message):
    with pytest.raises(CaptureError, match=message):
        mapbox.pin_events({**SPEC, "zoom": 0.5, "pins": pins})


def test_pins_are_projected_into_the_2x_image_with_label_and_coordinates():
    centre = {**SPEC, "pins": [{"id": "c", "label": "Centre", "lat": 34.0029, "lng": 36.2018}]}
    assert mapbox.pin_events(centre) == [
        {
            "t": 0.0,
            "name": "pin",
            "x": 1280.0,
            "y": 720.0,
            "target": "c",
            "label": "Centre",
            "lat": 34.0029,
            "lng": 36.2018,
        }
    ]
    events = mapbox.pin_events(SPEC)
    assert [e["target"] for e in events] == ["p2", "p1"]
    assert events[0]["y"] > 720 > events[1]["y"]  # the quarry lies south of the temple


def test_pins_off_the_frame_or_without_a_label_are_rejected():
    with pytest.raises(CaptureError, match="falls outside the frame"):
        mapbox.pin_events({**SPEC, "pins": [{"id": "far", "label": "x", "lat": 35.0, "lng": 36.2}]})
    # at zoom 15.6 the quarry sits at 94 % of the height: its label would go under the controls
    with pytest.raises(CaptureError, match=r"pin p2 sits at \(0\.42, 0\.94\) of the frame"):
        mapbox.pin_events({**SPEC, "zoom": 15.6})
    with pytest.raises(CaptureError, match=r"pins\[0\] must be"):
        mapbox.pin_events({**SPEC, "pins": [{"id": "p1", "lat": 34.0, "lng": 36.2}]})


class _Response:
    def __init__(self, content, content_type):
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


def _jpeg(size, fmt="JPEG"):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, "gray").save(buf, fmt)
    return buf.getvalue()


def test_the_site_map_style_is_a_png_with_the_streets_credit(tmp_path, monkeypatch):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")
    calls = []
    monkeypatch.setattr(
        mapbox.httpx,
        "get",
        lambda url, timeout: (
            calls.append(url) or _Response(_jpeg((2560, 1440), "PNG"), "image/png")
        ),
    )
    manifest = mapbox.mapbox_topdown(tmp_path, {**SPEC, "style": "satellite-streets-v12"})
    assert "/satellite-streets-v12/static/" in calls[0]
    assert manifest["path"] == "captures/td1.png"
    assert manifest["credits"] == [CREDIT_MAPBOX_STREETS]


def test_mapbox_topdown_writes_the_image_and_returns_a_still_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")
    calls = []
    monkeypatch.setattr(
        mapbox.httpx,
        "get",
        lambda url, timeout: calls.append(url) or _Response(_jpeg((2560, 1440)), "image/jpeg"),
    )
    manifest = mapbox.mapbox_topdown(tmp_path, SPEC)
    assert calls and "access_token=pk.test" in calls[0]
    assert manifest["path"] == "captures/td1.jpg" and (tmp_path / "captures" / "td1.jpg").is_file()
    assert (
        manifest["kind"],
        manifest["width"],
        manifest["height"],
        manifest["fps"],
        manifest["duration_s"],
    ) == (
        "mapbox_topdown",
        2560,
        1440,
        None,
        None,
    )
    assert manifest["credits"] == [CREDIT_MAPBOX_SATELLITE]
    assert not (tmp_path / "captures" / "td1.json").exists()  # pipeline.studio.captures stores it


def test_mapbox_topdown_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.delenv("VITE_MAPBOX_ACCESS_TOKEN", raising=False)
    with pytest.raises(CaptureError, match="VITE_MAPBOX_ACCESS_TOKEN"):
        mapbox.mapbox_topdown(tmp_path, SPEC)
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")
    monkeypatch.setattr(
        mapbox.httpx, "get", lambda url, timeout: _Response(_jpeg((1280, 720)), "image/jpeg")
    )
    with pytest.raises(CaptureError, match=r"expected \(2560, 1440\)"):
        mapbox.mapbox_topdown(tmp_path, SPEC)
    monkeypatch.setattr(
        mapbox.httpx, "get", lambda url, timeout: _Response(b"{}", "application/json")
    )
    with pytest.raises(CaptureError, match="not an image"):
        mapbox.mapbox_topdown(tmp_path, SPEC)
    # every refusal comes before any side effect
    assert not (tmp_path / "captures").exists()


def test_a_refused_request_is_a_capture_error_without_the_token(tmp_path, monkeypatch):
    monkeypatch.setenv("VITE_MAPBOX_ACCESS_TOKEN", "pk.test")

    class Unauthorized:
        def __init__(self, url):
            self.request = httpx.Request("GET", url)

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                f"Client error '401 Unauthorized' for url '{self.request.url}'",
                request=self.request,
                response=httpx.Response(401, request=self.request),
            )

    monkeypatch.setattr(mapbox.httpx, "get", lambda url, timeout: Unauthorized(url))
    with pytest.raises(CaptureError, match="td1: Mapbox Static API: Client error '401") as err:
        mapbox.mapbox_topdown(tmp_path, SPEC)
    assert "pk.test" not in str(err.value) and isinstance(
        err.value.__cause__, httpx.HTTPStatusError
    )
    assert not (tmp_path / "captures").exists()
