# SPDX-License-Identifier: AGPL-3.0-only
"""Wohin der Discord-Login zurückkehren darf.

Die feste Liste kannte nur 7 Pfade, alle mit .html — die indexierten Seiten
liegen aber unter generierten Pfaden. Fünf von sechs getesteten Zielen warfen
den Rückkehrer auf /account.html (Audit 2026-08-09). Die Prüfung bleibt
explizit: alles nicht Erkannte wird abgelehnt, nichts wird zurechtgebogen.
"""

from __future__ import annotations

import pytest

from api.routes.auth import _is_allowed_return


class TestAllowed:
    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/account.html",
            "/globe.html",
            "/search.html",
            "/sites/",
            "/sites/denmark",
            "/sites/denmark/borremose-5281654c",
            "/sites/t%C3%BCrkiye",
            "/news-archive/",
            "/news-archive/aesir-etymology-gods-of-the-great-pole-or-asia-5072",
            "/research/the-squatter-man-petroglyph-and-auroral-sky-mythology",
            "/articles/weekly-archaeological-digest",
        ],
    )
    def test_same_origin_paths_pass(self, path):
        assert _is_allowed_return(path) is True


class TestRejected:
    @pytest.mark.parametrize(
        "value",
        [
            "//evil.com",  # protocol-relative: browsers go to another origin
            "//evil.com/sites/denmark",
            "/\\evil.com",  # backslash variant of the same trick
            "https://evil.com",
            "http://evil.com/sites/",
            "javascript:alert(1)",
            "/sites/x\r\nLocation: https://evil.com",  # header splitting
            "/sites/x%0d%0aLocation:%20https://evil.com",
            "/SITES/x%0D%0Aevil",  # case must not slip the CRLF check
            "/admin.html",  # a real path, but not opted in
            "/lyra-ops.html",
            "/db.html",
            "",
            None,
            123,
            ["/sites/denmark"],
        ],
    )
    def test_everything_else_is_rejected(self, value):
        assert _is_allowed_return(value) is False

    def test_a_prefix_lookalike_is_not_enough(self):
        """ "/sitesX" must not pass just because "/sites/" is allowed."""
        assert _is_allowed_return("/sitesevil.com") is False
