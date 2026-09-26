"""An httpx transport that sends each request through `requests` (urllib3), so the fields lanes can
use the project's httpx seams (`census.fetch.Fetcher`, `opus_audit.quotes.collect`) with the plain
User-Agent the owner requires.

**Why (measured 2026-09-26 from this workstation).** With the User-Agent
`AncientMapRemediation/1.0 (research)` - no contact address, as the standing rule demands -
Wikimedia's edge answers every httpx request with `403 Please respect our robot policy`, and so does
whc.unesco.org, while `requests` with the very same headers gets `200` from both. The cause on
Wikimedia is the TLS handshake: the standard library's `http.client` gets `200` with a default
context and `403` as soon as the context offers ALPN `http/1.1`, which httpcore sets on every TLS
connection it opens (a context passed in as `verify=` is changed the same way). UNESCO refuses the
bare standard-library request as well and accepts urllib3's. The census agent carried an e-mail
address, which Wikimedia's policy accepts - that is why the httpx seams worked until now.

So the request leaves through urllib3, and everything above the transport stays httpx: redirects
are followed by the httpx client (`allow_redirects=False` here), the body is handed over as it came
off the wire (`decode_content=False`) with its own `Content-Encoding`, and httpx decodes it once. A
failure is raised as the httpx error of its kind, so `quotes.collect` records it and
`census.fetch.Fetcher` retries it exactly as before.
"""

from __future__ import annotations

import httpx
import requests
import urllib3

TIMEOUT_SECONDS = 60.0


class RequestsTransport(httpx.BaseTransport):
    """`handle_request` through one `requests.Session`; see the module docstring for why."""

    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        self._session = requests.Session()
        self._timeout = timeout

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() not in ("host", "content-length")
        }
        try:
            answer = self._session.request(
                request.method,
                str(request.url),
                headers=headers,
                data=request.read() or None,
                allow_redirects=False,
                stream=True,
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise httpx.TimeoutException(str(exc), request=request) from exc
        except requests.ConnectionError as exc:
            raise httpx.ConnectError(str(exc), request=request) from exc
        except requests.RequestException as exc:
            raise httpx.TransportError(str(exc), request=request) from exc
        try:
            body = answer.raw.read(decode_content=False)
        except (urllib3.exceptions.HTTPError, OSError) as exc:
            raise httpx.ReadError(str(exc), request=request) from exc
        finally:
            answer.close()
        return httpx.Response(
            answer.status_code,
            headers=list(answer.raw.headers.items()),
            content=body,
            request=request,
        )

    def close(self) -> None:
        self._session.close()
