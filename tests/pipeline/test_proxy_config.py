# SPDX-License-Identifier: AGPL-3.0-only
"""LYRA_PROXY_URL: generic proxy (home-IP via Tailscale) replacing Webshare.

Both YouTube-facing fetch paths (transcripts via youtube-transcript-api,
storyboards via yt-dlp/requests) must honour an explicit proxy URL and
prefer it over Webshare credentials when both are configured.
"""

from __future__ import annotations

from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig

from pipeline.lyra.config import LyraSettings
from pipeline.lyra.screenshot_extractor import get_proxy_url
from pipeline.lyra.transcript_fetcher import _build_ytt_api

PROXY = "http://100.64.0.7:8888"


def _settings(**kwargs) -> LyraSettings:
    base = {"proxy_url": "", "webshare_username": "", "webshare_password": ""}
    base.update(kwargs)
    return LyraSettings(**base)


def test_ytt_api_uses_generic_proxy_when_proxy_url_set() -> None:
    api = _build_ytt_api(_settings(proxy_url=PROXY))
    cfg = api._fetcher._proxy_config
    assert isinstance(cfg, GenericProxyConfig)
    assert cfg.http_url == PROXY
    assert cfg.https_url == PROXY


def test_ytt_api_proxy_url_wins_over_webshare() -> None:
    api = _build_ytt_api(_settings(proxy_url=PROXY, webshare_username="u", webshare_password="p"))
    assert isinstance(api._fetcher._proxy_config, GenericProxyConfig)


def test_ytt_api_webshare_still_works_without_proxy_url() -> None:
    api = _build_ytt_api(_settings(webshare_username="u", webshare_password="p"))
    cfg = api._fetcher._proxy_config
    assert isinstance(cfg, WebshareProxyConfig)
    # Library default is 10 rotate-and-retry attempts per blocked IP — each
    # costs residential traffic, so we cap explicitly.
    assert cfg.retries_when_blocked == 3


def test_screenshot_proxy_prefers_proxy_url() -> None:
    assert get_proxy_url(_settings(proxy_url=PROXY)) == PROXY
    assert (
        get_proxy_url(_settings(proxy_url=PROXY, webshare_username="u", webshare_password="p"))
        == PROXY
    )


def test_screenshot_proxy_webshare_unchanged() -> None:
    url = get_proxy_url(_settings(webshare_username="u", webshare_password="p"))
    assert url == "http://u-rotate:p@p.webshare.io:80"
    assert get_proxy_url(_settings()) is None
