# SPDX-License-Identifier: AGPL-3.0-only
"""Der Mess-Redirect /goto/discord (api/routes/goto.py).

DB-los: der Router wird in eine leere FastAPI-App gehängt — kein Lifespan,
kein Postgres/Redis. Geprüft wird der Vertrag: Allowlist-src wird geloggt,
Freitext-src wird NIE geloggt (nur als 'unknown' gezählt), der Redirect
bricht in keinem Fall, und das 302-Ziel ist der echte Invite. Der
Cache-Header kommt von nginx (location = /goto/discord, no-store) und ist
hier bewusst nicht Thema.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.goto import ALLOWED_SOURCES, router
from pipeline.article_html_renderer import DISCORD_INVITE_URL

app = FastAPI()
app.include_router(router)
client = TestClient(app)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _get(url: str, ua: str = BROWSER_UA):
    return client.get(url, headers={"User-Agent": ua}, follow_redirects=False)


class TestRedirect:
    @pytest.mark.parametrize("src", sorted(ALLOWED_SOURCES))
    def test_allowed_src_302_to_invite(self, src):
        response = _get(f"/goto/discord?src={src}")
        assert response.status_code == 302
        assert response.headers["location"] == DISCORD_INVITE_URL

    @pytest.mark.parametrize(
        "url",
        [
            "/goto/discord",  # no src at all
            "/goto/discord?src=",
            "/goto/discord?src=not-on-the-list",
            "/goto/discord?src=SEO",  # allowlist is exact, no case folding
            "/goto/discord?src=%0d%0aevil",
        ],
    )
    def test_unknown_src_still_redirects(self, url):
        """Der Redirect darf nie brechen — Messfehler ja, tote Links nein."""
        response = _get(url)
        assert response.status_code == 302
        assert response.headers["location"] == DISCORD_INVITE_URL


class TestLogging:
    @pytest.fixture(autouse=True)
    def _capture(self, caplog):
        caplog.set_level(logging.INFO, logger="api.routes.goto")
        self.caplog = caplog

    def test_allowed_src_is_logged(self):
        _get("/goto/discord?src=seo")
        assert "goto_discord src=seo bot=0" in self.caplog.text

    def test_unknown_src_is_counted_but_never_echoed(self):
        _get("/goto/discord?src=attacker-controlled-text")
        assert "goto_discord src=unknown bot=0" in self.caplog.text
        assert "attacker" not in self.caplog.text

    def test_bot_ua_sets_the_flag(self):
        _get(
            "/goto/discord?src=seo",
            ua="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        )
        assert "goto_discord src=seo bot=1" in self.caplog.text

    def test_no_ip_or_referer_in_the_log(self):
        """DSGVO-Zusage der Route: nur src + Bot-Flag, sonst nichts."""
        response = _get("/goto/discord?src=seo")
        assert response.status_code == 302
        record = self.caplog.records[-1]
        assert record.getMessage() == "goto_discord src=seo bot=0"


class TestAllowlistSync:
    def test_matches_brand_ts(self):
        """ALLOWED_SOURCES und DiscordCtaSource (brand.ts) dürfen nicht driften."""
        brand_ts = (
            Path(__file__).resolve().parents[2]
            / "ancient-nerds-map"
            / "src"
            / "constants"
            / "brand.ts"
        ).read_text(encoding="utf-8")
        m = re.search(r"export type DiscordCtaSource = (.+)", brand_ts)
        assert m, "DiscordCtaSource type not found in brand.ts"
        ts_sources = set(re.findall(r"'([a-z]+)'", m.group(1)))
        assert ts_sources == set(ALLOWED_SOURCES)
