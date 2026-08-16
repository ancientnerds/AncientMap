"""HTTP glue between the SEO page fragments and the built app shell."""

import json
from typing import Any

from fastapi import Response

from api.ssr_client import render_page
from pipeline.app_shell import render_app_shell
from pipeline.seo_pages import SeoPage


def shell_response(page: SeoPage, headers: dict[str, str]) -> Response:
    """Serve a Python-rendered SEO page inside the real app shell.

    Legacy path: dies with pipeline/seo_pages.py (react-ssr plan, Task 16)
    once the last page type renders through ssr_shell_response().
    """
    html = render_app_shell(
        page.entry,
        head_html=page.head,
        root_html=page.body,
        route=page.route,
    )
    return Response(content=html, media_type="text/html", headers=headers)


def ssr_shell_response(entry: str, route: dict[str, Any], headers: dict[str, str]) -> Response:
    """Render the route payload through the SSR sidecar and serve the document.

    Head and body both come from the React world (meta.ts renderHead() and
    renderToString()) — one description per page, which is the point of the
    react-ssr plan. The '<' escape mirrors seo_pages._route_json(): a payload
    string containing "</script>" must not break out of the inline script tag.

    Raises SsrUnavailableError (mapped to 502 in api/main.py) when the
    sidecar is down — deliberately no fallback to the Python renderer.
    """
    head, body = render_page(route)
    html = render_app_shell(
        entry,
        head_html=head,
        root_html=body,
        route=json.dumps(route, ensure_ascii=False).replace("<", "\\u003c"),
    )
    return Response(content=html, media_type="text/html", headers=headers)
