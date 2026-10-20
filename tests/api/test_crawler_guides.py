# SPDX-License-Identifier: AGPL-3.0-only
"""robots.txt and llms.txt agree with each other and name the Atom feeds.

llms.txt advertised /api/v1/sites/search, /api/v1/sites/{site_id}, /api/v1/sources and
/api/v1/research while robots.txt disallows /api/ and allows only a few paths below it, so
a crawler that obeys robots.txt could fetch none of them (SEO evaluation 2026-10-19,
bing_geo-4). Pinned: every /api/ path llms.txt names is one robots.txt allows.
"""

from __future__ import annotations

import re
from pathlib import Path

PUBLIC = Path(__file__).resolve().parents[2] / "ancient-nerds-map" / "public"
ROBOTS = (PUBLIC / "robots.txt").read_text(encoding="utf-8")
LLMS = (PUBLIC / "llms.txt").read_text(encoding="utf-8")


def _general_group_allows() -> list[str]:
    """The Allow paths of the `User-agent: *` group (the AhrefsBot group follows it)."""
    general = ROBOTS.split("User-agent: AhrefsBot")[0]
    return re.findall(r"^Allow: (\S+)$", general, flags=re.M)


def test_llms_txt_names_no_api_path_robots_txt_blocks():
    allows = [a for a in _general_group_allows() if a.startswith("/api/")]
    assert allows, "robots.txt lost its /api/ allow list"
    named = re.findall(r"(/api/[^\s,)]+)", LLMS)
    assert named == ["/api/v1/openapi.json"]
    for path in named:
        assert any(path.startswith(allow) for allow in allows), path


def test_robots_and_llms_name_both_feeds():
    for name, text in (("robots.txt", ROBOTS), ("llms.txt", LLMS)):
        assert "https://ancientnerds.com/feeds/stories.xml" in text, name
        assert "https://ancientnerds.com/feeds/research.xml" in text, name
