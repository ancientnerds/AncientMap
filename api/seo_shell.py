"""HTTP glue between the SEO page fragments and the built app shell."""

from fastapi import Response

from pipeline.app_shell import render_app_shell
from pipeline.seo_pages import SeoPage


def shell_response(page: SeoPage, headers: dict[str, str]) -> Response:
    """Serve an SEO page inside the real app shell."""
    html = render_app_shell(
        page.entry,
        head_html=page.head,
        root_html=page.body,
        route=page.route,
    )
    return Response(content=html, media_type="text/html", headers=headers)
