"""The package surface plan C's captures.py calls (contract C7)."""

import inspect

from pipeline.studio import capture


def test_the_four_contract_functions_are_importable_from_the_package():
    names = {
        "platform": "record_platform",
        "globe": "record_globe",
        "source": "capture_source",
        "mapbox_topdown": "mapbox_topdown",
    }
    for name in names.values():
        fn = getattr(capture, name)
        assert list(inspect.signature(fn).parameters) == ["episode_dir", "spec"]
    assert sorted(capture.__all__) == sorted(names.values())
