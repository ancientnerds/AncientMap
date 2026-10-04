"""The studio CLI never prints a credential that travels in a query string.

httpx logs every request URL at INFO, and the studio turns INFO on: the Mapbox Static API
(`access_token=`) and the Europeana image connector (`wskey=`) put their credential in that URL.
Claude Code's Bash tool returns stderr into the model transcript.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import httpx
import pytest
from loguru import logger

from pipeline.connectors.museums.europeana import EuropeanaConnector
from pipeline.connectors.protocols.rest import RestProtocol
from pipeline.studio import __main__ as cli
from pipeline.studio import config

KEY = "SECRETTESTKEY123"


@pytest.fixture(autouse=True)
def _restore_http_loggers():
    """main() lowers these loggers for the rest of the process: put them back after the test."""
    names = ("httpx", "httpcore")
    levels = {n: logging.getLogger(n).level for n in names}
    yield
    for n, level in levels.items():
        logging.getLogger(n).setLevel(level)


def test_main_keeps_request_urls_out_of_the_log(monkeypatch, caplog):
    monkeypatch.setattr(config, "load_env", lambda: None)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={})

    def run(args: argparse.Namespace) -> int:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            client.get(f"https://api.mapbox.example/static?access_token={KEY}")
        logging.getLogger("pipeline.studio.test").info("the step went on")
        return 0

    parser = argparse.ArgumentParser()
    parser.set_defaults(func=run)
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    # basicConfig does nothing under pytest (its handlers are on the root logger already): the
    # level it would set is set here, so the INFO records main() has to keep out are produced.
    caplog.set_level(logging.INFO)
    assert cli.main([]) == 0
    assert seen == [f"https://api.mapbox.example/static?access_token={KEY}"]
    assert "the step went on" in caplog.text
    assert KEY not in caplog.text


@pytest.fixture
def loguru_lines():
    lines: list[str] = []
    # INFO, the level the pipeline logs at (pipeline/utils/logging.py): RestProtocol.get names
    # every request URL at DEBUG, which nothing here switches on.
    sink = logger.add(lines.append, level="INFO", format="{message}")
    yield lines
    logger.remove(sink)


def _europeana(status: int) -> EuropeanaConnector:
    connector = EuropeanaConnector(api_key=KEY)
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={}))
    connector.rest = RestProtocol(
        base_url=connector.base_url, http_client=httpx.AsyncClient(transport=transport)
    )
    return connector


def test_a_failed_europeana_search_does_not_log_the_key(loguru_lines):
    assert asyncio.run(_europeana(500).search("baalbek")) == []
    failures = [m for m in loguru_lines if "Europeana search failed" in m]
    assert len(failures) == 1 and "500" in failures[0]
    assert KEY not in "".join(loguru_lines)


def test_a_failed_europeana_item_fetch_does_not_log_the_key(loguru_lines):
    assert asyncio.run(_europeana(500).get_item("europeana:/9200/abc")) is None
    failures = [m for m in loguru_lines if "Failed to get Europeana item" in m]
    assert len(failures) == 1 and "500" in failures[0]
    assert KEY not in "".join(loguru_lines)
