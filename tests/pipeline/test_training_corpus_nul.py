"""NUL characters never reach PostgreSQL from the training corpus (2026-09-26).

PostgreSQL refuses U+0000 in TEXT and in JSONB. One NUL in one fetched page cost
runs aae36b9c and 23336ade their citation registry and every source link:
'A string literal cannot contain NUL (0x00) characters'.
"""

import hashlib
import json

from pipeline.lyra import training_corpus as tc


class _Result:
    def __init__(self) -> None:
        self.rowcount = 1

    def scalar_one(self) -> int:
        return 7


class _CaptureSession:
    """Keeps every (sql, params) pair, including executemany parameter lists."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.calls.append((stmt.text, params))
        return _Result()

    def commit(self) -> None:
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


def _capture(monkeypatch) -> _CaptureSession:
    session = _CaptureSession()
    monkeypatch.setattr(tc, "_session_factory", lambda: session)
    return session


def test_strip_nul_walks_nested_payloads():
    payload = {"a\x00": ["x\x00y", {"z": "\x00"}], "n": 3, "t": ("p\x00",)}
    assert tc._strip_nul(payload) == {"a": ["xy", {"z": ""}], "n": 3, "t": ["p"]}


def test_archived_document_loses_its_nul_bytes(monkeypatch):
    session = _capture(monkeypatch)
    doc = tc.ArchiveDocument(
        source_id="a1b2c3d4e5f6",
        url="https://x.example/\x00p",
        title="Ti\x00tle",
        full_text="he\x00llo",
        authors=["Wool\x00ley"],
        venue="Anti\x00quity",
    )
    tc.archive_documents([doc])
    ((_sql, params),) = session.calls
    row = params[0]
    assert row["full_text"] == "hello"
    assert row["title"] == "Title"
    assert row["url"] == "https://x.example/p"
    assert row["venue"] == "Antiquity"
    assert json.loads(row["authors"]) == ["Woolley"]
    assert row["content_hash"] == hashlib.sha256(b"hello").hexdigest()


def test_artifact_payload_is_nul_free_json(monkeypatch):
    session = _capture(monkeypatch)
    tc.save_artifact("req-1", "moderated", {"final_claims": [{"claim": "Ba\x00albek"}]}, "r\x00ef")
    _sql, params = session.calls[-1]
    assert "\\u0000" not in params["payload"]
    assert json.loads(params["payload"]) == {"final_claims": [{"claim": "Baalbek"}]}
    assert params["ref"] == "ref"


def test_run_links_are_nul_free(monkeypatch):
    session = _capture(monkeypatch)
    tc.record_run_links(
        "req-1",
        [
            {
                "source_id": "a1b2c3d4e5f6",
                "angle_id": "a\x001",
                "search_query": "ur\x00 pottery",
                "cited": False,
            }
        ],
    )
    ((_sql, params),) = session.calls
    assert params[0]["search_query"] == "ur pottery"
    assert params[0]["angle_id"] == "a1"
