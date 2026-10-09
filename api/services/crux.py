# SPDX-License-Identifier: AGPL-3.0-only
"""Google's own field data for our origin: the Chrome UX Report history.

The p75 of real Chrome users over a rolling 28 days, one point a week, 25
weeks back - the numbers Google's page-experience signal reads, as opposed
to the vitals our own tracker measures (Problems panel). The key is the
Google Cloud API key restricted to the CrUX and PageSpeed APIs; on the VPS it
is CRUX_API_KEY in the .env the API containers read.

Verified against the live API on 2026-10-09: 25 collection periods per form
factor (2026-03-22 to 2026-10-03); a week without enough INP samples carries
null in ``p75s``; CLS p75 arrives as a string ("0.03"), LCP and INP as ints.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

HISTORY_URL = "https://chromeuxreport.googleapis.com/v1/records:queryHistoryRecord"
ORIGIN = "https://ancientnerds.com"
METRICS = {
    "largest_contentful_paint": "lcp",
    "interaction_to_next_paint": "inp",
    "cumulative_layout_shift": "cls",
}
FORM_FACTORS = {"PHONE": "phone", "DESKTOP": "desktop"}


def _number(value: Any) -> float | None:
    return None if value is None else float(value)


def _period_end(period: dict[str, Any]) -> str:
    d = period["lastDate"]
    return f"{d['year']:04d}-{d['month']:02d}-{d['day']:02d}"


async def field_vitals() -> dict[str, Any]:
    """Per form factor: the end date of every weekly window and the p75 of
    each metric in it, oldest first."""
    key = os.environ.get("CRUX_API_KEY")
    if not key:
        raise RuntimeError("CRUX_API_KEY is not set - the field-vitals panel has no access to CrUX")
    out: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        for form_factor, name in FORM_FACTORS.items():
            response = await client.post(
                HISTORY_URL,
                params={"key": key},
                json={"origin": ORIGIN, "formFactor": form_factor, "metrics": list(METRICS)},
            )
            response.raise_for_status()
            record = response.json()["record"]
            out[name] = {
                "weeks": [_period_end(p) for p in record["collectionPeriods"]],
                **{
                    short: [
                        _number(v)
                        for v in record["metrics"][metric]["percentilesTimeseries"]["p75s"]
                    ]
                    for metric, short in METRICS.items()
                },
            }
    return out
