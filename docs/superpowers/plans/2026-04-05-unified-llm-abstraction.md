# Unified LLM Abstraction Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both Anthropic and MiniMax backends work optimally through a single Anthropic SDK code path, with structured output via tool-use trick for MiniMax.

**Architecture:** Delete the OpenAI SDK MiniMax path. Both backends use the Anthropic SDK — Anthropic at its default URL, MiniMax at `https://api.minimax.io/anthropic`. Structured output on MiniMax uses the tool-use trick (forced tool call whose input_schema matches the desired JSON schema). All adaptation happens inside `_call_anthropic_api()`.

**Tech Stack:** Anthropic Python SDK, Python 3.13

**Spec:** `docs/superpowers/specs/2026-04-05-unified-llm-abstraction-design.md`

---

### Task 1: Add MiniMax Anthropic client + client selection

**Files:**
- Modify: `pipeline/lyra/config.py:387-407` (replace OpenAI client caching with Anthropic client caching)
- Test: `tests/pipeline/test_llm_abstraction.py` (create)

- [ ] **Step 1: Write failing test for MiniMax client creation**

Create `tests/pipeline/test_llm_abstraction.py`:

```python
"""Tests for the unified LLM abstraction layer in config.py."""
from unittest.mock import MagicMock, patch

import pytest

from pipeline.lyra.config import LyraSettings


@pytest.fixture
def anthropic_settings():
    return LyraSettings(
        anthropic_api_key="sk-ant-test",
        llm_backend="anthropic",
    )


@pytest.fixture
def minimax_settings():
    return LyraSettings(
        minimax_api_key="sk-cp-test",
        minimax_base_url="https://api.minimax.io/anthropic",
        llm_backend="minimax",
    )


class TestClientSelection:
    def test_anthropic_backend_uses_anthropic_client(self, anthropic_settings):
        from pipeline.lyra.config import _get_client

        with patch("pipeline.lyra.config._get_anthropic_client") as mock:
            mock.return_value = MagicMock()
            client = _get_client(anthropic_settings)
            mock.assert_called_once_with("sk-ant-test")

    def test_minimax_backend_uses_minimax_anthropic_client(self, minimax_settings):
        from pipeline.lyra.config import _get_client

        with patch("pipeline.lyra.config._get_minimax_anthropic_client") as mock:
            mock.return_value = MagicMock()
            client = _get_client(minimax_settings)
            mock.assert_called_once_with(minimax_settings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/pipeline/test_llm_abstraction.py::TestClientSelection -v`
Expected: FAIL — `_get_client` does not exist yet.

- [ ] **Step 3: Implement client selection**

In `pipeline/lyra/config.py`, replace the OpenAI MiniMax client block (lines 387-407) with:

```python
# ---------------------------------------------------------------------------
# MiniMax Anthropic-compatible client (cached)
# ---------------------------------------------------------------------------
_cached_minimax_anthropic_client = None
_cached_minimax_anthropic_key: str = ""


def _get_minimax_anthropic_client(settings: LyraSettings):
    """Return a cached Anthropic client pointed at MiniMax's Anthropic endpoint."""
    global _cached_minimax_anthropic_client, _cached_minimax_anthropic_key

    import anthropic

    cache_key = f"{settings.minimax_api_key}:{settings.minimax_base_url}"
    if _cached_minimax_anthropic_client is None or _cached_minimax_anthropic_key != cache_key:
        _cached_minimax_anthropic_client = anthropic.Anthropic(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            timeout=600.0,
            max_retries=2,
        )
        _cached_minimax_anthropic_key = cache_key
    return _cached_minimax_anthropic_client


def _get_client(settings: LyraSettings):
    """Return the appropriate Anthropic SDK client for the configured backend."""
    if settings.llm_backend == "minimax":
        return _get_minimax_anthropic_client(settings)
    return _get_anthropic_client(settings.anthropic_api_key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/pipeline/test_llm_abstraction.py::TestClientSelection -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_llm_abstraction.py pipeline/lyra/config.py
git commit -m "feat: add MiniMax Anthropic client + _get_client selector"
```

---

### Task 2: Implement structured output via tool-use trick

**Files:**
- Modify: `pipeline/lyra/config.py` (add helper functions)
- Test: `tests/pipeline/test_llm_abstraction.py` (extend)

- [ ] **Step 1: Write failing tests for tool-use trick helpers**

Append to `tests/pipeline/test_llm_abstraction.py`:

```python
import json


class TestStructuredOutputToolTrick:
    def test_build_tool_from_schema(self):
        from pipeline.lyra.config import _build_structured_output_tool

        schema = {
            "type": "object",
            "properties": {"score": {"type": "integer"}},
            "required": ["score"],
        }
        tool = _build_structured_output_tool(schema)
        assert tool["name"] == "structured_output"
        assert tool["input_schema"] == schema
        assert "description" in tool

    def test_extract_tool_result_from_tool_use_block(self):
        from pipeline.lyra.config import _extract_tool_use_json

        # Simulate Anthropic SDK response content blocks
        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = "Let me reason..."

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "structured_output"
        tool_block.input = {"score": 85, "reason": "important discovery"}

        content = [thinking_block, tool_block]
        result = _extract_tool_use_json(content)
        assert result == '{"score": 85, "reason": "important discovery"}'

    def test_extract_tool_result_no_tool_block_returns_none(self):
        from pipeline.lyra.config import _extract_tool_use_json

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = '{"score": 85}'

        result = _extract_tool_use_json([text_block])
        assert result is None

    def test_extract_tool_result_empty_content(self):
        from pipeline.lyra.config import _extract_tool_use_json

        result = _extract_tool_use_json([])
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_llm_abstraction.py::TestStructuredOutputToolTrick -v`
Expected: FAIL — `_build_structured_output_tool` and `_extract_tool_use_json` do not exist.

- [ ] **Step 3: Implement the helper functions**

Add to `pipeline/lyra/config.py` after the `_get_client` function:

```python
# ---------------------------------------------------------------------------
# Structured output via tool-use trick (MiniMax)
# ---------------------------------------------------------------------------

def _build_structured_output_tool(schema: dict) -> dict:
    """Build an Anthropic tool definition that forces JSON matching the schema.

    MiniMax's Anthropic endpoint doesn't support output_config/json_schema,
    so we force the model to "call" a tool whose input_schema IS the schema.
    Combined with tool_choice={"type": "tool", "name": "structured_output"},
    the model must produce valid JSON matching the schema.
    """
    return {
        "name": "structured_output",
        "description": (
            "Return the result as structured JSON. "
            "All fields are required and must match the schema exactly."
        ),
        "input_schema": schema,
    }


def _extract_tool_use_json(content: list) -> str | None:
    """Extract JSON string from a tool_use block in the response.

    Scans content blocks (skipping thinking blocks) for a tool_use block
    named 'structured_output'. Returns the input as a JSON string,
    or None if no tool_use block is found.
    """
    for block in content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "structured_output":
            return json.dumps(block.input)
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/pipeline/test_llm_abstraction.py::TestStructuredOutputToolTrick -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_llm_abstraction.py pipeline/lyra/config.py
git commit -m "feat: add structured output tool-use trick helpers"
```

---

### Task 3: Refactor `_call_anthropic_api()` with adaptation points

This is the core task. Refactor `_call_anthropic_api()` (lines 238-352) to handle both backends.

**Files:**
- Modify: `pipeline/lyra/config.py:238-352`
- Test: `tests/pipeline/test_llm_abstraction.py` (extend)

- [ ] **Step 1: Write failing tests for the unified dispatch**

Append to `tests/pipeline/test_llm_abstraction.py`:

```python
from pipeline.lyra.config import _call_anthropic_api, NormalizedResponse, TextBlock


def _make_mock_text_response(text="result"):
    """Create a mock Anthropic Messages response with a text block."""
    mock_resp = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    text_block.citations = None
    mock_resp.content = [text_block]
    mock_resp.stop_reason = "end_turn"
    mock_resp.model = "test-model"
    mock_resp.usage = MagicMock(input_tokens=10, output_tokens=5)
    return mock_resp


def _make_mock_tool_response(tool_input: dict):
    """Create a mock Anthropic Messages response with a tool_use block."""
    mock_resp = MagicMock()
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "structured_output"
    tool_block.input = tool_input
    mock_resp.content = [tool_block]
    mock_resp.stop_reason = "end_turn"
    mock_resp.model = "MiniMax-M2.7"
    mock_resp.usage = MagicMock(input_tokens=10, output_tokens=5)
    return mock_resp


class TestUnifiedDispatch:
    def test_anthropic_structured_output_uses_output_config(self, anthropic_settings):
        """Anthropic backend uses native output_config for json_schema."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response('{"score": 85}')

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                anthropic_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "Score",
                        "strict": True,
                        "schema": {"type": "object", "properties": {"score": {"type": "integer"}}},
                    },
                },
            )

        assert "output_config" in captured
        assert "tools" not in captured  # no tool-use trick

    def test_minimax_structured_output_uses_tool_trick(self, minimax_settings):
        """MiniMax backend converts json_schema into forced tool call."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_tool_response({"score": 85})

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            resp = _call_anthropic_api(
                minimax_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "Score",
                        "strict": True,
                        "schema": {"type": "object", "properties": {"score": {"type": "integer"}}},
                    },
                },
            )

        # Should use tool-use trick, not output_config
        assert "output_config" not in captured
        assert "tools" in captured
        assert captured["tools"][0]["name"] == "structured_output"
        assert captured["tool_choice"] == {"type": "tool", "name": "structured_output"}
        # Model should be overridden to MiniMax-M2.7
        assert captured["model"] == "MiniMax-M2.7"
        # Response should unwrap tool result into text
        assert resp.text == '{"score": 85}'

    def test_minimax_temperature_clamped(self, minimax_settings):
        """MiniMax clamps temperature=0.0 to 0.01."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("ok")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                minimax_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                temperature=0.0,
                messages=[{"role": "user", "content": "test"}],
            )

        assert captured["temperature"] == 0.01

    def test_minimax_model_override(self, minimax_settings):
        """MiniMax overrides all model names to MiniMax-M2.7."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("ok")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                minimax_settings,
                model="claude-opus-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
            )

        assert captured["model"] == "MiniMax-M2.7"

    def test_minimax_documents_inlined(self, minimax_settings):
        """MiniMax inlines documents into user message text."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("ok")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                minimax_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "Summarize this."}],
                documents=[{"title": "Source 1", "data": "Source text here."}],
            )

        msgs = captured["messages"]
        user_content = msgs[-1]["content"]
        # Should be plain string with documents inlined, not content blocks
        assert isinstance(user_content, str)
        assert "Source 1" in user_content
        assert "Source text here." in user_content
        assert "Summarize this." in user_content

    def test_minimax_tool_trick_fallback_to_text(self, minimax_settings):
        """If MiniMax returns text instead of tool_use, fall back to parsing text."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response('{"score": 85}')

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            resp = _call_anthropic_api(
                minimax_settings,
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "Score",
                        "strict": True,
                        "schema": {"type": "object", "properties": {"score": {"type": "integer"}}},
                    },
                },
            )

        # Should still return the text content as-is (caller parses JSON)
        assert resp.text == '{"score": 85}'

    def test_anthropic_thinking_passed_through(self, anthropic_settings):
        """Anthropic backend passes thinking config through."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("article body here")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                anthropic_settings,
                model="claude-opus-4-6",
                max_tokens=128000,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": "Write article"}],
            )

        assert captured["thinking"] == {"type": "adaptive"}
        assert "temperature" not in captured  # thinking disables temperature

    def test_minimax_thinking_passed_through(self, minimax_settings):
        """MiniMax Anthropic endpoint also supports thinking."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("article body here")

        with patch("pipeline.lyra.config._get_client") as mock_get:
            mock_get.return_value.messages.create = fake_create
            _call_anthropic_api(
                minimax_settings,
                model="claude-opus-4-6",
                max_tokens=128000,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": "Write article"}],
            )

        assert captured["thinking"] == {"type": "adaptive"}
        assert captured["model"] == "MiniMax-M2.7"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/pipeline/test_llm_abstraction.py::TestUnifiedDispatch -v`
Expected: FAIL — `_call_anthropic_api` doesn't accept `minimax_settings` / doesn't have adaptation points.

- [ ] **Step 3: Rewrite `_call_anthropic_api()` with adaptation points**

Replace `_call_anthropic_api()` (lines 238-352) in `pipeline/lyra/config.py` with:

```python
def _call_anthropic_api(
    settings: LyraSettings,
    *,
    prefill: str | None = None,
    documents: list[dict] | None = None,
    timeout: float | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Call LLM via Anthropic SDK — works for both Anthropic and MiniMax backends.

    MiniMax adaptation points are clearly marked with # [MINIMAX].
    """
    is_minimax = settings.llm_backend == "minimax"
    client = _get_client(settings)

    # --- Extract params from kwargs ---
    system_blocks = kwargs.pop("system", None)
    system_text = ""
    if system_blocks:
        if isinstance(system_blocks, str):
            system_text = system_blocks
        elif isinstance(system_blocks, list):
            system_text = "\n\n".join(
                b["text"] if isinstance(b, dict) else str(b) for b in system_blocks
            )

    messages: list[dict] = []
    for msg in kwargs.pop("messages", []):
        messages.append({"role": msg["role"], "content": msg["content"]})

    response_format = kwargs.pop("response_format", None)
    thinking_config = kwargs.pop("thinking", None)
    tool_choice = kwargs.pop("tool_choice", None)
    tools = kwargs.pop("tools", None)
    kwargs.pop("reasoning_effort", None)

    model = kwargs.pop("model", settings.model_summarize)
    max_tokens = kwargs.pop("max_tokens", settings.max_tokens)
    temperature = kwargs.pop("temperature", None)

    # [MINIMAX] Adaptation 1: Model override — all calls use MiniMax-M2.7
    if is_minimax:
        model = "MiniMax-M2.7"

    # [MINIMAX] Adaptation 2: Documents — inline into user message
    # (MiniMax doesn't support document content blocks or citations)
    if documents and is_minimax:
        docs_text = "\n\n".join(
            f"--- {doc.get('title', 'Source')} ---\n{doc['data']}"
            for doc in documents
        )
        # Prepend documents to the last user message
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                original = messages[i]["content"]
                if isinstance(original, str):
                    messages[i]["content"] = f"{docs_text}\n\n{original}"
                break
        documents = None  # consumed — don't pass to Anthropic doc handling below

    # Anthropic: wrap documents as content blocks with citations
    if documents:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                question_text = messages[i]["content"]
                if isinstance(question_text, str):
                    content_blocks: list[dict] = [
                        {
                            "type": "document",
                            "source": {
                                "type": "text",
                                "media_type": "text/plain",
                                "data": doc["data"],
                            },
                            "title": doc.get("title", "Source"),
                            "citations": {"enabled": True},
                        }
                        for doc in documents
                    ]
                    content_blocks.append({"type": "text", "text": question_text})
                    messages[i]["content"] = content_blocks
                break

    # Extended thinking is incompatible with prefill and temperature
    if thinking_config is not None:
        prefill = None

    # --- Structured output handling ---
    use_structured_output = response_format and response_format.get("type") == "json_schema"
    use_tool_trick = False

    if use_structured_output:
        prefill = None  # structured output is incompatible with prefill
        schema = response_format["json_schema"]["schema"]

        if is_minimax:
            # [MINIMAX] Adaptation 3: Structured output via tool-use trick
            tool = _build_structured_output_tool(schema)
            tools = [tool] if not tools else [tool] + list(tools)
            tool_choice = {"type": "tool", "name": "structured_output"}
            use_tool_trick = True
        else:
            # Anthropic: native structured output via output_config
            pass  # handled below when building create_kwargs

    # Handle prefill — append as assistant message
    if prefill:
        messages.append({"role": "assistant", "content": prefill})

    # --- Build request kwargs ---
    create_kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    # Anthropic native structured output
    if use_structured_output and not use_tool_trick:
        js = response_format["json_schema"]
        create_kwargs["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": js["schema"],
            }
        }

    if tools:
        create_kwargs["tools"] = tools
    if tool_choice:
        create_kwargs["tool_choice"] = tool_choice
    if system_text:
        create_kwargs["system"] = [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    if thinking_config is not None:
        create_kwargs["thinking"] = thinking_config
        # Temperature must be omitted when thinking is enabled
    elif temperature is not None:
        # [MINIMAX] Adaptation 4: Temperature clamping (0,1] — exclusive of 0
        if is_minimax and temperature <= 0.0:
            temperature = 0.01
        else:
            temperature = max(settings.temperature_min, temperature)
        create_kwargs["temperature"] = temperature

    if timeout is not None:
        import httpx

        create_kwargs["timeout"] = httpx.Timeout(timeout, connect=30.0)

    # --- Make the API call ---
    response = client.messages.create(**create_kwargs)

    # --- Normalize the response ---
    # [MINIMAX] Adaptation 5: Extract tool result if tool-use trick was used
    if use_tool_trick:
        tool_json = _extract_tool_use_json(response.content)
        if tool_json is not None:
            # Wrap tool result as a text block so callers see response.text = JSON
            stop_reason = response.stop_reason or "end_turn"
            return NormalizedResponse(
                content=[TextBlock(text=tool_json)],
                stop_reason=stop_reason,
                model=response.model or "",
                usage={
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                },
            )
        # Fallback: model returned text instead of tool_use — pass through
        # (callers already have JSON parse error handling)
        logger.warning("MiniMax did not return tool_use block — falling back to text response")

    return _normalize_anthropic_response(response)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/pipeline/test_llm_abstraction.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run existing tests to verify no regression**

Run: `python -m pytest tests/pipeline/test_call_api_documents.py tests/pipeline/test_tool_calling.py -v`
Expected: ALL PASS — existing Anthropic behavior unchanged.

- [ ] **Step 6: Commit**

```bash
git add pipeline/lyra/config.py tests/pipeline/test_llm_abstraction.py
git commit -m "feat: refactor _call_anthropic_api with MiniMax adaptation points"
```

---

### Task 4: Delete old MiniMax OpenAI path + update `call_api()`

**Files:**
- Modify: `pipeline/lyra/config.py:410-492` (delete `_call_minimax_api`), `pipeline/lyra/config.py:515-543` (simplify `call_api`)
- Modify: `pipeline/lyra/config.py:157-163` (update settings)
- Test: `tests/pipeline/test_llm_abstraction.py` (extend)

- [ ] **Step 1: Write test for unified `call_api()` dispatch**

Append to `tests/pipeline/test_llm_abstraction.py`:

```python
from pipeline.lyra.config import call_api, LyraAPIError


class TestCallApiDispatch:
    def test_call_api_minimax_backend(self, minimax_settings):
        """call_api() dispatches through the unified path for MiniMax."""
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _make_mock_text_response("ok")

        with (
            patch("pipeline.lyra.config._get_settings", return_value=minimax_settings),
            patch("pipeline.lyra.config._get_client") as mock_get,
        ):
            mock_get.return_value.messages.create = fake_create
            resp = call_api(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[{"role": "user", "content": "test"}],
            )

        assert captured["model"] == "MiniMax-M2.7"
        assert resp.text == "ok"

    def test_call_api_wraps_errors(self, minimax_settings):
        """call_api() wraps exceptions as LyraAPIError."""
        with (
            patch("pipeline.lyra.config._get_settings", return_value=minimax_settings),
            patch("pipeline.lyra.config._get_client") as mock_get,
        ):
            mock_get.return_value.messages.create.side_effect = Exception("network error")
            with pytest.raises(LyraAPIError, match="network error"):
                call_api(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1000,
                    messages=[{"role": "user", "content": "test"}],
                )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/pipeline/test_llm_abstraction.py::TestCallApiDispatch -v`
Expected: FAIL — `call_api` still branches to old `_call_minimax_api`.

- [ ] **Step 3: Delete old MiniMax code and simplify `call_api()`**

In `pipeline/lyra/config.py`:

**Delete** these blocks entirely:
- `_cached_minimax_client` and `_cached_minimax_key` globals (if any remain after Task 1)
- `_get_minimax_client()` function
- `_call_minimax_api()` function (lines ~410-492)

**Replace** `call_api()` (lines ~515-543) with:

```python
def call_api(
    *,
    prefill: str | None = None,
    reasoning_effort: str | None = None,
    documents: list[dict] | None = None,
    timeout: float | None = None,
    **kwargs,
) -> NormalizedResponse:
    """Unified LLM call — dispatches to Anthropic or MiniMax via Anthropic SDK.

    Both backends use the same code path. MiniMax differences (model override,
    structured output via tool trick, temperature clamping) are handled inside
    _call_anthropic_api().

    Args:
        prefill: Prefix for the response (e.g. "{" for JSON).
        reasoning_effort: Ignored — kept for call-site compat.
        documents: Optional list of source documents for Anthropic citations.
            Each dict has shape {"title": str, "data": str}.
            On MiniMax, documents are inlined into the user message.
        timeout: Per-request timeout in seconds.
        **kwargs: model, max_tokens, messages, system, temperature, response_format, etc.
    """
    settings = _get_settings()

    try:
        return _call_anthropic_api(
            settings, prefill=prefill, documents=documents, timeout=timeout, **kwargs
        )
    except LyraAPIError:
        raise
    except Exception as e:
        raise LyraAPIError(f"{settings.llm_backend.title()} API error: {e}") from e
```

**Update** `LyraSettings` — change `minimax_base_url` default and remove `minimax_model`:

```python
    # MiniMax Token Plan (Anthropic-compatible endpoint)
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.io/anthropic"
    # minimax_model removed — always MiniMax-M2.7, hardcoded in _call_anthropic_api
```

Remove the `minimax_model` line from `LyraSettings`.

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/pipeline/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/lyra/config.py tests/pipeline/test_llm_abstraction.py
git commit -m "feat: delete OpenAI MiniMax path, unify through Anthropic SDK"
```

---

### Task 5: Update `.env.example` and `.env`

**Files:**
- Modify: `.env.example:140-149`
- Modify: `.env:78-82`

- [ ] **Step 1: Update `.env.example`**

Replace the MiniMax section (lines ~140-149) in `.env.example`:

```ini
# =============================================================================
# MINIMAX TOKEN PLAN (Anthropic-compatible endpoint for pipeline LLM calls)
# =============================================================================
# Get a Token Plan key (sk-cp-...) at https://platform.minimax.io
# Used when LYRA_LLM_BACKEND=minimax — all pipeline LLM calls go through
# MiniMax's Anthropic-compatible API at this base URL.
LYRA_MINIMAX_API_KEY=
# LYRA_MINIMAX_BASE_URL=https://api.minimax.io/anthropic
# Backend: "minimax" (default, structured corrections) or "anthropic" (Opus + web_search)
LYRA_ARTICLE_WEB_BACKEND=minimax
```

- [ ] **Step 2: Update `.env`**

In `.env`, change the MiniMax base URL (line ~79 area) from:

```ini
LYRA_LLM_BACKEND=minimax
```

to (keep backend, update base URL if present):

```ini
LYRA_LLM_BACKEND=minimax
LYRA_MINIMAX_BASE_URL=https://api.minimax.io/anthropic
```

Remove any `LYRA_MINIMAX_MODEL` line if present.

- [ ] **Step 3: Verify settings load correctly**

Run: `python -c "from pipeline.lyra.config import _get_settings; s = _get_settings(); print(f'backend={s.llm_backend}, base_url={s.minimax_base_url}')"`
Expected: `backend=minimax, base_url=https://api.minimax.io/anthropic`

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "chore: update MiniMax config for Anthropic-compatible endpoint"
```

Note: Do NOT commit `.env` — it contains secrets. Just update it locally.

---

### Task 6: Integration smoke test

**Files:**
- No new files — run existing test suite

- [ ] **Step 1: Run full pipeline test suite**

Run: `python -m pytest tests/ -v --ignore=tests/api/`
Expected: ALL PASS

- [ ] **Step 2: Run linting**

Run: `python -m ruff check pipeline/lyra/config.py`
Expected: No errors

- [ ] **Step 3: Run mypy**

Run: `python -m mypy pipeline/lyra/config.py --ignore-missing-imports`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 4: Verify OpenAI SDK is no longer imported in config.py**

Run: `grep -n "openai\|OpenAI" pipeline/lyra/config.py`
Expected: No matches

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add pipeline/lyra/config.py
git commit -m "fix: address lint/type issues from LLM abstraction refactor"
```
