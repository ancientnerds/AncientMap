"""HTTP glue between the SSR sidecar and the built app shell."""

import json
from typing import Any

from fastapi import Response

from api.ssr_client import render_page
from pipeline.app_shell import render_app_shell


def ssr_shell_response(entry: str, route: dict[str, Any], headers: dict[str, str]) -> Response:
    """Render the route payload through the SSR sidecar and serve the document.

    Head and body both come from the React world (meta.ts renderHead() and
    renderToString()) — one description per page, which is the point of the
    react-ssr plan. The '<' escape keeps a payload string containing
    "</script>" from breaking out of the inline script tag.

    Raises SsrUnavailableError (mapped to 502 in api/main.py) when the
    sidecar is down — deliberately no fallback to a second renderer; the
    Python one died with react-ssr Task 16.
    """
    head, body = render_page(route)
    html = render_app_shell(
        entry,
        head_html=head,
        root_html=body,
        route=json.dumps(route, ensure_ascii=False).replace("<", "\\u003c"),
    )
    return Response(content=html, media_type="text/html", headers=headers)
