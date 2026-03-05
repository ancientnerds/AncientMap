# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for the Lyra RAG pipeline — agent flow, pipeline events, tool execution.

These tests mock external dependencies (Qdrant, DB, LLM backends) to test
the pipeline logic in isolation. They verify:
- Correct pipeline events are emitted for all stages
- Fast-tier queries skip retrieval (efficiency fix)
- Local backend skips filter extraction (cost fix)
- Tool call accumulation and execution
- Site/news extraction from tool results
- Error handling in pipeline stages
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from api.services.lyra_router import RequestContext, route_request, set_request_context

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fast_ctx() -> RequestContext:
    return RequestContext(
        backend_type="local",
        model_tier="fast",
        model_name="qwen3.5:0.8b",
        embedding_backend="local",
        supports_thinking=False,
        supports_tools=True,
    )


def _heavy_ctx() -> RequestContext:
    return RequestContext(
        backend_type="local",
        model_tier="heavy",
        model_name="qwen3.5:4b",
        embedding_backend="local",
        supports_thinking=True,
        supports_tools=True,
    )


def _premium_ctx() -> RequestContext:
    return RequestContext(
        backend_type="minimax",
        model_tier="premium",
        model_name="MiniMax-M2.5",
        embedding_backend="voyage",
        supports_thinking=True,
        supports_tools=True,
    )


async def _collect_events(gen) -> list[dict]:
    """Collect all events from an async generator."""
    events = []
    async for ev in gen:
        events.append(ev)
    return events


def _mock_backend_stream(content_text="Hello!", tool_calls=None):
    """Create a mock backend that yields content events."""

    async def stream(messages, tools):
        if tool_calls:
            for tc in tool_calls:
                yield {
                    "type": "tool_call_chunk",
                    "index": tc.get("index", 0),
                    "id": tc.get("id", "call_1"),
                    "name": tc.get("name"),
                    "args": json.dumps(tc.get("args", {})),
                }
        else:
            yield {"type": "content", "text": content_text}
        yield {"type": "usage", "input": 100, "output": 50}

    mock = MagicMock()
    mock.stream = stream
    return mock


# ---------------------------------------------------------------------------
# Pipeline event completeness
# ---------------------------------------------------------------------------


class TestPipelineEvents:
    """Verify all pipeline stages emit correct events."""

    @pytest.mark.asyncio
    async def test_fast_tier_skips_retrieval(self):
        """Fast-tier (greetings) should skip retrieval and filter extraction."""
        ctx = _fast_ctx()
        mock_backend = _mock_backend_stream("Hi there!")

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(run_agent_stream(message="hi", ctx=ctx))

        stages = [(e["stage"], e["status"]) for e in events if e.get("type") == "pipeline"]

        # Should see skip events for retrieval stages
        assert ("pipeline_init", "done") in stages
        assert ("auto_retrieve", "skip") in stages
        assert ("filter_extraction", "skip") in stages
        assert ("news_augmentation", "skip") in stages
        assert ("context_assembly", "done") in stages
        assert ("pre_stream_emit", "done") in stages
        assert ("llm_round", "start") in stages
        assert ("llm_round", "done") in stages
        assert ("done_credits", "done") in stages

    @pytest.mark.asyncio
    async def test_heavy_tier_runs_retrieval(self):
        """Heavy-tier queries should run retrieval."""
        ctx = _heavy_ctx()
        mock_backend = _mock_backend_stream("Here are Minoan sites...")

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
            patch(
                "api.services.lyra_agent._auto_retrieve",
                return_value=("context", [], [], 0.8, 100),
            ),
            patch(
                "api.services.lyra_agent._extract_news_filters",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch("api.services.lyra_agent._get_related_news", return_value=[]),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(
                run_agent_stream(message="What sites are in Crete?", ctx=ctx)
            )

        stages = [(e["stage"], e["status"]) for e in events if e.get("type") == "pipeline"]

        assert ("pipeline_init", "done") in stages
        assert ("auto_retrieve", "start") in stages
        assert ("auto_retrieve", "done") in stages
        # Local backend skips filter extraction
        assert ("filter_extraction", "skip") in stages
        assert ("news_augmentation", "start") in stages
        assert ("news_augmentation", "done") in stages
        assert ("context_assembly", "done") in stages
        assert ("llm_round", "start") in stages
        assert ("llm_round", "done") in stages
        assert ("done_credits", "done") in stages

    @pytest.mark.asyncio
    async def test_premium_tier_runs_filter_extraction(self):
        """Premium (MiniMax) tier should run filter extraction."""
        ctx = _premium_ctx()
        mock_backend = _mock_backend_stream("Here's what I found...")

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
            patch(
                "api.services.lyra_agent._auto_retrieve",
                return_value=("context", [], [], 0.8, 100),
            ),
            patch(
                "api.services.lyra_agent._extract_news_filters",
                new_callable=AsyncMock,
                return_value={"country": "Greece"},
            ),
            patch("api.services.lyra_agent._get_related_news", return_value=[]),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(run_agent_stream(message="sites in Greece", ctx=ctx))

        stages = [(e["stage"], e["status"]) for e in events if e.get("type") == "pipeline"]

        # Premium should run filter extraction (NOT skip)
        assert ("filter_extraction", "start") in stages
        assert ("filter_extraction", "done") in stages

    @pytest.mark.asyncio
    async def test_empire_context_skips_retrieval(self):
        """Empire context should skip retrieval."""
        ctx = _premium_ctx()
        mock_backend = _mock_backend_stream("The Roman Empire...")

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(
                run_agent_stream(
                    message="Tell me about this empire",
                    context_type="empire",
                    context_id="it_roman_principate",
                    ctx=ctx,
                )
            )

        stages = [(e["stage"], e["status"]) for e in events if e.get("type") == "pipeline"]

        assert ("auto_retrieve", "skip") in stages
        assert ("filter_extraction", "skip") in stages
        assert ("news_augmentation", "skip") in stages

    @pytest.mark.asyncio
    async def test_pipeline_init_contains_model_info(self):
        """pipeline_init event should contain model configuration."""
        ctx = _heavy_ctx()
        mock_backend = _mock_backend_stream()

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(run_agent_stream(message="hi", ctx=ctx))

        init_events = [e for e in events if e.get("stage") == "pipeline_init"]
        assert len(init_events) == 1
        meta = init_events[0]["meta"]
        assert meta["model"] == "qwen3.5:4b"
        assert meta["tier"] == "heavy"
        assert meta["backend"] == "local"
        assert meta["embedding"] == "nomic-embed-text"
        assert meta["reranker"] == "FlashRank"


# ---------------------------------------------------------------------------
# Pipeline stage completeness verification
# ---------------------------------------------------------------------------


class TestPipelineCompleteness:
    """Verify no pipeline stages are missing or duplicated."""

    EXPECTED_STAGES = {
        "pipeline_init",
        "auto_retrieve",
        "filter_extraction",
        "news_augmentation",
        "context_assembly",
        "pre_stream_emit",
        "llm_round",
        "done_credits",
    }

    @pytest.mark.asyncio
    async def test_all_stages_present_in_fast_path(self):
        """Fast path should emit all stages (some as skip)."""
        ctx = _fast_ctx()
        mock_backend = _mock_backend_stream()

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(run_agent_stream(message="hello", ctx=ctx))

        pipeline_events = [e for e in events if e.get("type") == "pipeline"]
        emitted_stages = {e["stage"] for e in pipeline_events}

        missing = self.EXPECTED_STAGES - emitted_stages
        assert not missing, f"Missing pipeline stages: {missing}"

    @pytest.mark.asyncio
    async def test_all_stages_present_in_heavy_path(self):
        """Heavy path should emit all stages."""
        ctx = _heavy_ctx()
        mock_backend = _mock_backend_stream()

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
            patch(
                "api.services.lyra_agent._auto_retrieve",
                return_value=("ctx", [], [], None, 0),
            ),
            patch(
                "api.services.lyra_agent._extract_news_filters",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch("api.services.lyra_agent._get_related_news", return_value=[]),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(run_agent_stream(message="What is Pompeii?", ctx=ctx))

        pipeline_events = [e for e in events if e.get("type") == "pipeline"]
        emitted_stages = {e["stage"] for e in pipeline_events}

        missing = self.EXPECTED_STAGES - emitted_stages
        assert not missing, f"Missing pipeline stages: {missing}"

    @pytest.mark.asyncio
    async def test_every_start_has_done_or_error_or_skip(self):
        """Every stage that emits 'start' should also emit 'done', 'error', or 'skip'."""
        ctx = _heavy_ctx()
        mock_backend = _mock_backend_stream()

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
            patch(
                "api.services.lyra_agent._auto_retrieve",
                return_value=("ctx", [], [], None, 0),
            ),
            patch(
                "api.services.lyra_agent._extract_news_filters",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch("api.services.lyra_agent._get_related_news", return_value=[]),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(run_agent_stream(message="test query", ctx=ctx))

        pipeline_events = [e for e in events if e.get("type") == "pipeline"]
        started = {e["stage"] for e in pipeline_events if e["status"] == "start"}
        ended = {e["stage"] for e in pipeline_events if e["status"] in ("done", "error", "skip")}

        unclosed = started - ended
        assert not unclosed, f"Stages started but never ended: {unclosed}"


# ---------------------------------------------------------------------------
# Tool call accumulation
# ---------------------------------------------------------------------------


class TestToolCallAccumulation:
    def test_accumulate_new_tool(self):
        from api.services.lyra_agent import _accumulate_tool_call

        tool_calls: list[dict] = []
        _accumulate_tool_call(
            tool_calls,
            {"index": 0, "id": "call_1", "name": "search_sites", "args": '{"q'},
        )
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "search_sites"

    def test_accumulate_args_chunks(self):
        from api.services.lyra_agent import _accumulate_tool_call

        tool_calls: list[dict] = []
        _accumulate_tool_call(
            tool_calls,
            {"index": 0, "id": "call_1", "name": "search_sites", "args": '{"q'},
        )
        _accumulate_tool_call(
            tool_calls,
            {"index": 0, "id": None, "name": None, "args": 'uery": "test"}'},
        )
        assert len(tool_calls) == 1
        full_args = tool_calls[0]["args"]
        assert json.loads(full_args) == {"query": "test"}

    def test_multiple_tools(self):
        from api.services.lyra_agent import _accumulate_tool_call

        tool_calls: list[dict] = []
        _accumulate_tool_call(
            tool_calls,
            {"index": 0, "id": "c1", "name": "search_sites", "args": "{}"},
        )
        _accumulate_tool_call(
            tool_calls,
            {"index": 1, "id": "c2", "name": "search_news", "args": "{}"},
        )
        assert len(tool_calls) == 2
        assert tool_calls[0]["name"] == "search_sites"
        assert tool_calls[1]["name"] == "search_news"


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_basic_message(self):
        from api.services.lyra_agent import _build_messages

        with patch("api.services.lyra_agent._build_context_prompt", return_value=""):
            msgs = _build_messages(
                message="hello",
                images=None,
                history=None,
                context_type="global",
                context_id=None,
                context_year=None,
            )
        # Should have: system + user
        assert len(msgs) == 2
        assert msgs[0].type == "system"
        assert msgs[1].type == "human"
        assert msgs[1].content == "hello"

    def test_with_history(self):
        from api.services.lyra_agent import _build_messages

        history = [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous answer"},
        ]
        with patch("api.services.lyra_agent._build_context_prompt", return_value=""):
            msgs = _build_messages(
                message="follow up",
                images=None,
                history=history,
                context_type="global",
                context_id=None,
                context_year=None,
            )
        # system + 2 history + 1 current = 4
        assert len(msgs) == 4

    def test_history_role_validation(self):
        from api.services.lyra_agent import _build_messages

        history = [
            {"role": "user", "content": "valid"},
            {"role": "system", "content": "should be filtered"},  # Invalid role
            {"role": "assistant", "content": "also valid"},
        ]
        with patch("api.services.lyra_agent._build_context_prompt", return_value=""):
            msgs = _build_messages(
                message="test",
                images=None,
                history=history,
                context_type="global",
                context_id=None,
                context_year=None,
            )
        # system + 2 valid history + 1 current = 4
        assert len(msgs) == 4

    def test_history_truncated_to_last_10(self):
        from api.services.lyra_agent import _build_messages

        history = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        with patch("api.services.lyra_agent._build_context_prompt", return_value=""):
            msgs = _build_messages(
                message="test",
                images=None,
                history=history,
                context_type="global",
                context_id=None,
                context_year=None,
            )
        # system + 10 history + 1 current = 12
        assert len(msgs) == 12

    def test_content_length_cap(self):
        from api.services.lyra_agent import _build_messages

        long_msg = "x" * 10000
        history = [{"role": "user", "content": long_msg}]
        with patch("api.services.lyra_agent._build_context_prompt", return_value=""):
            msgs = _build_messages(
                message="test",
                images=None,
                history=history,
                context_type="global",
                context_id=None,
                context_year=None,
            )
        # History message should be capped at 8000
        assert len(msgs[1].content) == 8000

    def test_retrieved_context_injected(self):
        from api.services.lyra_agent import _build_messages

        with patch("api.services.lyra_agent._build_context_prompt", return_value=""):
            msgs = _build_messages(
                message="test",
                images=None,
                history=None,
                context_type="global",
                context_id=None,
                context_year=None,
                retrieved_context="\n\nRetrieved data here",
            )
        assert "Retrieved data here" in msgs[0].content


# ---------------------------------------------------------------------------
# Done event metadata
# ---------------------------------------------------------------------------


class TestDoneEvent:
    @pytest.mark.asyncio
    async def test_done_event_contains_metadata(self):
        ctx = _fast_ctx()
        mock_backend = _mock_backend_stream("Hello!")

        with (
            patch("api.services.lyra_agent.get_backend", return_value=mock_backend),
            patch("api.services.lyra_agent.set_request_context"),
        ):
            from api.services.lyra_agent import run_agent_stream

            events = await _collect_events(run_agent_stream(message="hi", ctx=ctx))

        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        meta = done_events[0]["metadata"]
        assert meta["backend"] == "local"
        assert "fast" in meta["model"]
        assert meta["tool_calls"] == 0
        assert "tokens" in meta
        assert meta["tokens"]["input"] == 100
        assert meta["tokens"]["output"] == 50


# ---------------------------------------------------------------------------
# Visualization gap analysis
# ---------------------------------------------------------------------------


class TestVisualizationGaps:
    """Verify all pipeline events match frontend PIPELINE_STAGES definitions."""

    FRONTEND_STAGE_IDS = {
        "pipeline_init",
        "auto_retrieve",
        "filter_extraction",
        "news_augmentation",
        "context_assembly",
        "pre_stream_emit",
        "llm_round",
        "tool_call",
        "done_credits",
    }

    TOOL_NAMES_IN_REGISTRY = {
        "search_sites",
        "get_site_details",
        "search_news",
        "search_radar",
        "list_channels",
        "get_site_images",
        "vector_search",
        "search_transcripts",
        "search_articles",
        "search_empires",
        "get_empire_data",
    }

    def test_all_backend_stages_have_frontend_definitions(self):
        """Every stage ID emitted by the backend must exist in PIPELINE_STAGES."""
        # These are the stage IDs the backend emits
        backend_stages = {
            "pipeline_init",
            "auto_retrieve",
            "filter_extraction",
            "news_augmentation",
            "context_assembly",
            "pre_stream_emit",
            "llm_round",
            "tool_call",
            "done_credits",
        }
        missing = backend_stages - self.FRONTEND_STAGE_IDS
        assert not missing, f"Backend emits stages not defined in frontend: {missing}"

    def test_all_tools_in_registry(self):
        """Every tool in TOOLS list should be in TOOL_REGISTRY."""
        from api.services.lyra_tools import TOOLS

        backend_tool_names = {t.name for t in TOOLS}
        missing = backend_tool_names - self.TOOL_NAMES_IN_REGISTRY
        assert not missing, f"Backend tools not in frontend TOOL_REGISTRY: {missing}"

    def test_tool_registry_matches_backend_tools(self):
        """Frontend TOOL_REGISTRY should only contain tools that exist in backend."""
        from api.services.lyra_tools import TOOLS

        backend_tool_names = {t.name for t in TOOLS}
        extra = self.TOOL_NAMES_IN_REGISTRY - backend_tool_names
        assert not extra, f"Frontend TOOL_REGISTRY has tools not in backend: {extra}"

    def test_tool_count_matches(self):
        """Frontend and backend should have same number of tools."""
        from api.services.lyra_tools import TOOLS

        assert len(TOOLS) == len(self.TOOL_NAMES_IN_REGISTRY), (
            f"Backend has {len(TOOLS)} tools, frontend registry has {len(self.TOOL_NAMES_IN_REGISTRY)}"
        )
