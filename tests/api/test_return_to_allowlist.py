# SPDX-License-Identifier: AGPL-3.0-only
"""Where the Discord login is allowed to return to.

The fixed list once held only seven paths, all .html — the indexed pages live
under generated paths, so five of six tested targets bounced the returner to
/account.html (audit 2026-08-09). The check stays explicit: anything not
recognised is rejected, nothing is bent into shape.

The list also missed /lyra.html, and exact equality made every target with a
query string fail (LyraChatModal.tsx sends pathname + search), so Lyra's own
chat login returned to /account.html. Query strings are now allowed, but the
allowlist still decides on the PATH alone: the rejections (backslash, CR/LF,
%0d/%0a, protocol-relative, no leading "/") all run on the full string, so a
query can never widen the check.
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
            "/lyra.html",
            "/sites/",
            "/sites/denmark",
            "/sites/denmark/borremose-5281654c",
            "/sites/t%C3%BCrkiye",
            "/news-archive/",
            "/news-archive/aesir-etymology-gods-of-the-great-pole-or-asia-5072",
            "/research/the-squatter-man-petroglyph-and-auroral-sky-mythology",
            "/articles/weekly-archaeological-digest",
            # The chat modal sends pathname + search, so the site context comes
            # back with the user instead of being dropped.
            "/lyra.html?site=1f2e3d4c-5b6a-4789-8abc-ef0123456789",
            "/globe.html?site=1f2e3d4c-5b6a-4789-8abc-ef0123456789",
            "/sites/denmark?ref=globe",
            "/globe.html?",  # empty query: the path alone decides
            "/globe.html?a=1?b=2",  # only the FIRST "?" ends the path
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
            "/lyra-ops.html?site=1f2e3d4c-5b6a-4789-8abc-ef0123456789",
            "/db.html",
            "",
            None,
            123,
            ["/sites/denmark"],
            # Query variants of the attacks above: a query must not smuggle
            # anything past the checks, and it never becomes part of the path.
            "//evil.com?x=1",
            "/\\evil.com?x=1",
            "/globe.html?x=\\",  # a backslash in the query stays a backslash
            "/globe.html?x=%0d%0a",
            "/globe.html?x=%0D%0A",  # case must not slip the CRLF check
            "/globe.html?\r\nLocation: https://evil.com",
            "?/globe.html",  # no path, only a query
        ],
    )
    def test_everything_else_is_rejected(self, value):
        assert _is_allowed_return(value) is False

    def test_a_prefix_lookalike_is_not_enough(self):
        """ "/sitesX" must not pass just because "/sites/" is allowed."""
        assert _is_allowed_return("/sitesevil.com") is False

    def test_an_allowed_path_in_the_query_does_not_allow_the_target(self):
        """Only the path is looked up — the query content is never a target."""
        assert _is_allowed_return("/evil.html?x=/globe.html") is False
        assert _is_allowed_return("/evil.html?x=/sites/denmark") is False

    def test_a_traversal_inside_an_allowed_prefix_is_not_caught(self):
        """KNOWN LIMIT, measured 2026-09-20 — recorded so this file's coverage
        claim stays honest.

        This function looks up the STRING; the browser normalises the path
        afterwards. "/sites/../lyra-ops.html" therefore passes the check although
        the browser lands on /lyra-ops.html, a path the allowlist rejects.

        Not an open redirect: the origin is unchanged either way, and the pages
        behind it carry their own gates. Pre-existing — the version before the
        query change behaved identically (verified by the independent check).
        Fixing it would mean rejecting every ".." segment, which is a decision
        about the allowlist policy, not a bug fix.
        """
        assert _is_allowed_return("/lyra-ops.html") is False
        assert _is_allowed_return("/sites/../lyra-ops.html") is True
