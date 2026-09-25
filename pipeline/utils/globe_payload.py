"""The ``fields=globe`` projection of ``GET /api/sites/all`` (contract C2 of the globe-load plan).

One definition for the route (api/routes/sites.py) and the globe load probe
(scripts/globe_probe/probe.py), which simulates it against a server that does not honour
``fields`` yet and detects whether a server's answer is projected. The probe cannot import the
route module: importing any ``api`` module imports ``api.main``, which connects to the database.
"""

from __future__ import annotations

# The fields the globe's first frame draws: dots (la/lo), their colours and filters (s, t, c,
# p/pn), tooltips and the result list (n). Everything else loads after the intro (fields=all).
GLOBE_KEYS = ("id", "n", "la", "lo", "s", "t", "p", "pn", "c")


def globe_projection(payload: dict) -> dict:
    """The payload with each site cut to GLOBE_KEYS; keys a site lacks stay absent
    (snapshot sites omit t/p/pn/c when empty)."""
    return {
        **payload,
        "sites": [{k: s[k] for k in GLOBE_KEYS if k in s} for s in payload["sites"]],
    }
