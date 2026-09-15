"""Interactive-app gate for server-rendered pages.

SitePage swaps its static site record for the interactive SitePopup only
after `GET /api/app/interactive` answers 204. The path is deliberately under
the robots.txt `Disallow: /api/` with no Allow: Google's renderer applies
robots.txt to a page's own fetches, so for Googlebot the probe fails and the
SSR record stays — the popup's galleries and source panels would otherwise
render as "No photos found / 0 sources" and were filed as Soft 404 on ~2,100
detail pages (GSC, 2026-09-05). Until 2026-09-15 the gate was
/api/sources/, which kept the source registry blocked and left /search.html
and /globe.html stuck on "LOADING" in Google's render; the registry is
crawlable now and this probe carries the gate alone.

Everyone gets the same HTML and JavaScript; only what the client may fetch
differs, and that is what robots.txt is for.
"""

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()


@router.get("/interactive")
def interactive() -> Response:
    """204: the interactive app may take over this page."""
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
