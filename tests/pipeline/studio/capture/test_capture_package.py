"""The package surface plan C's captures.py calls (contract C7)."""

import inspect

from pipeline.studio import capture, captures
from pipeline.studio.config import CAPTURE_KINDS


def test_each_capture_kind_records_through_its_contract_function():
    names = {
        "platform": "record_platform",
        "globe": "record_globe",
        "source": "capture_source",
        "mapbox_topdown": "mapbox_topdown",
    }
    assert set(names) == set(CAPTURE_KINDS)
    for name in names.values():
        fn = getattr(capture, name)
        assert list(inspect.signature(fn).parameters) == ["episode_dir", "spec"]
    assert sorted(capture.__all__) == sorted(names.values())
    # the table the capture step records with: every kind to its function of this package
    assert captures.default_recorders() == {
        kind: getattr(capture, name) for kind, name in names.items()
    }
