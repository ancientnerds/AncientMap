# SPDX-License-Identifier: AGPL-3.0-only
"""Security-focused tests for the application.

Rewritten 2026-08-06 (audit P3-13): the previous version tested the removed
`api.routes.ai` PIN system and rotted unnoticed because CI ran no backend
tests. These tests target the CURRENT security surfaces and need no DB —
endpoint-level auth tests live in the integration-marked API test files.
"""

import re
from pathlib import Path

import pytest

API_ROUTES_DIR = Path(__file__).resolve().parent.parent / "api" / "routes"


class TestTurnstileFailClosed:
    """Turnstile CAPTCHA verification must fail closed."""

    @pytest.mark.asyncio
    async def test_turnstile_rejects_without_secret(self, monkeypatch):
        """With no secret configured, verification must reject.

        Patches the module attribute directly — env-var deletion + reload is
        fragile here because the import chain re-runs load_dotenv() and
        restores the deleted variable from .env.
        """
        from api.services import turnstile

        monkeypatch.setattr(turnstile, "TURNSTILE_SECRET", "")
        assert await turnstile.verify_turnstile("any-token", "203.0.113.7") is False


class TestAdminKeyValidation:
    """Admin key comparisons must be timing-safe and header-based."""

    def test_news_log_key_uses_timing_safe_comparison(self):
        import inspect

        from api.routes import news

        source = inspect.getsource(news)
        assert "compare_digest" in source
        # The key must not be accepted via query parameter (leaks into access
        # logs and browser history) — header-only since audit 2026-08-05.
        assert 'Query(None, alias="key")' not in source


class TestErrorHandling:
    """Error responses must not leak exception details to clients."""

    # detail=f"...{e}..." / {str(e)} / {exc} hands internal exception text to
    # the client. Tool errors for the LLM are sanitized separately in
    # lyra_agent; this guards the HTTP layer.
    _LEAK_RE = re.compile(r"""detail=f["'][^"']*\{(?:str\()?(?:e|exc|err|error)\)?[.}]""")

    def test_no_route_interpolates_exceptions_into_detail(self):
        offenders: list[str] = []
        for path in sorted(API_ROUTES_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for m in self._LEAK_RE.finditer(source):
                line_no = source.count("\n", 0, m.start()) + 1
                offenders.append(f"{path.name}:{line_no}: {m.group(0)}")
        assert not offenders, "Exception details leak into HTTP responses:\n" + "\n".join(offenders)


class TestXSSPrevention:
    """Server-rendered output must escape user/DB-derived content."""

    def test_og_module_escapes_html(self):
        import inspect

        from api.routes import og

        source = inspect.getsource(og)
        assert "import html" in source or "from html import escape" in source
        assert "html.escape" in source or "escape(" in source

    def test_renderers_use_nh3_sanitizer(self):
        """Markdown-derived HTML must run through the nh3 allowlist sanitizer
        (the regex blocklist it replaced was bypassable — audit 2026-08-05)."""
        import inspect

        from pipeline import article_html_renderer

        source = inspect.getsource(article_html_renderer)
        assert "nh3.clean" in source
