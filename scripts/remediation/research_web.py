"""The web identity of the 2026-09-26 remediation lanes (WD2: served images and scope).

Every request these lanes make carries this User-Agent and nothing else that names a person: no
e-mail address, no name (owner rule, 2026-09-26). The project's older identity
(`census.fetch.USER_AGENT`) carries a mailbox, so it is not used here.

**Why the project URL is in it.** The bare string `AncientMapRemediation/1.0 (research)` was asked
for; measured 2026-09-26 against `www.wikidata.org`, `commons.wikimedia.org` and `en.wikipedia.org`
(`/w/api.php`), all three answer it with HTTP 403 "Please respect our robot policy
https://w.wiki/4wJS" - the Wikimedia User-Agent policy wants a way to reach the operator. With the
project's public URL added, all three answer 200. A URL of the project is no personal data.
"""

from __future__ import annotations

import httpx

USER_AGENT = "AncientMapRemediation/1.0 (research; https://ancientnerds.com)"
HEADERS = {"User-Agent": USER_AGENT}
#: The whole request, redirects included, may take this long before it is a failed request.
TIMEOUT_SECONDS = 60.0


def client() -> httpx.Client:
    """An HTTP/1.1 client with the lanes' User-Agent that follows redirects."""
    return httpx.Client(headers=HEADERS, follow_redirects=True, timeout=TIMEOUT_SECONDS)
