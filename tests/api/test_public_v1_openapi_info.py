# SPDX-License-Identifier: AGPL-3.0-only
"""The public API's OpenAPI info block (/api/v1/openapi.json, the one /api/ path robots.txt
opens to crawlers). Until 2026-10-20 it said "750K+" sites, from before the database grew to
1.76 million records, and had neither info.license nor info.contact (SEO evaluation
2026-10-19, roadmap S7)."""

from __future__ import annotations


def test_openapi_info_names_the_real_size_the_licence_and_a_contact():
    from api.routes.public_v1 import create_public_api

    info = create_public_api().openapi()["info"]
    assert "750K" not in info["description"]
    assert "1.7 million" in info["description"]
    # No single licence covers the aggregate: the terms say which part is CC BY 4.0.
    assert info["license"] == {
        "name": "CC BY 4.0 for Ancient Nerds content; source licences for third-party records",
        "url": "https://ancientnerds.com/terms.html",
    }
    assert info["contact"]["email"] == "contact@ancientnerds.com"
    assert info["contact"]["url"] == "https://ancientnerds.com/api.html"
