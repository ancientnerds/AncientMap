"""
Unified LLM backend abstraction for Lyra.

All backends normalize output to the same StreamEvent dicts:
  {"type": "reasoning", "text": str}
  {"type": "content", "text": str}          — standard append-mode tokens
  {"type": "diffusion", "text": str}        — full-text replacement (Mercury diffusing mode)
  {"type": "tool_call_chunk", "index": int, "id": str|None, "name": str|None, "args": str}
  {"type": "usage", "input": int, "output": int}
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Protocol

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StreamEvent Protocol
# ---------------------------------------------------------------------------


class LLMBackend(Protocol):
    """All backends normalize output to StreamEvent dicts."""

    def stream(
        self, messages: list[BaseMessage], tools: list, enable_thinking: bool = True
    ) -> AsyncIterator[dict]: ...

    async def complete(self, messages: list, response_format: dict | None = None) -> dict: ...

    async def generate(
        self, messages: list, tools: list | None = None, response_format: dict | None = None
    ) -> dict: ...


# ---------------------------------------------------------------------------
# Conversion helpers (moved from lyra_agent.py)
# ---------------------------------------------------------------------------


def _langchain_tools_to_openai(tools) -> list[dict]:
    """Convert LangChain @tool functions to OpenAI tool format."""
    from langchain_core.utils.function_calling import convert_to_openai_function

    return [{"type": "function", "function": convert_to_openai_function(t)} for t in tools]


def _langchain_messages_to_openai(messages: list) -> list[dict]:
    """Convert LangChain message objects to OpenAI dict format."""
    result = []
    for m in messages:
        if isinstance(m, SystemMessage):
            result.append({"role": "system", "content": m.content})
        elif isinstance(m, HumanMessage):
            result.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            msg: dict = {"role": "assistant", "content": m.content or ""}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"])
                            if isinstance(tc["args"], dict)
                            else tc["args"],
                        },
                    }
                    for tc in m.tool_calls
                ]
            result.append(msg)
        elif isinstance(m, ToolMessage):
            result.append(
                {
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content,
                }
            )
    return result


def _langchain_messages_to_ollama_native(messages: list) -> list[dict]:
    """Convert LangChain message objects to Ollama native /api/chat format.

    Differs from OpenAI format: no id/type in tool_calls, arguments is an
    object (not a JSON string), and tool responses omit tool_call_id.
    """
    result = []
    for m in messages:
        if isinstance(m, SystemMessage):
            result.append({"role": "system", "content": m.content})
        elif isinstance(m, HumanMessage):
            result.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            msg: dict = {"role": "assistant", "content": m.content or ""}
            if m.tool_calls:
                msg["tool_calls"] = [
                    {
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["args"]
                            if isinstance(tc["args"], dict)
                            else json.loads(tc["args"]),
                        },
                    }
                    for tc in m.tool_calls
                ]
            result.append(msg)
        elif isinstance(m, ToolMessage):
            result.append({"role": "tool", "content": m.content})
    return result


# ---------------------------------------------------------------------------
# OllamaBackend — raw openai.AsyncOpenAI (preserves reasoning field)
# ---------------------------------------------------------------------------


class OllamaBackend:
    """Uses Ollama native /api/chat for proper think=true/false support."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        max_tokens: int = 4096,
        num_ctx: int | None = None,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.num_ctx = num_ctx

    async def stream(
        self, messages: list[BaseMessage], tools: list, enable_thinking: bool = True
    ) -> AsyncIterator[dict]:
        """Stream from Ollama via native API (properly handles think param).

        Yields StreamEvent dicts.
        """
        import httpx

        openai_messages = _langchain_messages_to_ollama_native(messages)
        openai_tools = _langchain_tools_to_openai(tools) if tools else []

        body: dict = {
            "model": self.model,
            "messages": openai_messages,
            "think": enable_thinking,
            "stream": True,
        }
        options: dict = {"num_predict": self.max_tokens}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        # Qwen3.5 recommended: lower temperature/top_p when thinking is off
        if not enable_thinking:
            options["temperature"] = 0.7
            options["top_p"] = 0.8
        body["options"] = options
        if openai_tools:
            body["tools"] = openai_tools

        # Derive native API URL from the OpenAI-compat base_url
        # e.g. "http://host:11435/v1" -> "http://host:11435/api/chat"
        native_url = self.base_url.replace("/v1", "").rstrip("/") + "/api/chat"

        headers = {}
        if self.api_key and self.api_key != "unused":
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=600.0) as http:
            async with http.stream("POST", native_url, json=body, headers=headers) as resp:
                resp.raise_for_status()
                # Collect tool calls across streaming lines — Ollama may send
                # partial tool_calls in one line and complete them in the next.
                # Later entries for the same index override earlier ones.
                pending_tools: dict[int, dict] = {}

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    msg = data.get("message", {})

                    # Thinking tokens (only when think=true)
                    if msg.get("thinking"):
                        yield {"type": "reasoning", "text": msg["thinking"]}

                    # Content tokens
                    if msg.get("content"):
                        yield {"type": "content", "text": msg["content"]}

                    # Collect tool calls (may arrive across multiple lines)
                    if msg.get("tool_calls"):
                        for i, tc in enumerate(msg["tool_calls"]):
                            fn = tc.get("function", {})
                            name = fn.get("name")
                            raw_args = fn.get("arguments")
                            entry = pending_tools.setdefault(i, {})
                            if name:
                                entry["name"] = name
                            if raw_args:
                                entry["args"] = raw_args

                    # On done: yield finalized tool calls, then usage
                    if data.get("done"):
                        for i, tc_data in sorted(pending_tools.items()):
                            raw_args = tc_data.get("args", {})
                            args_str = (
                                json.dumps(raw_args)
                                if isinstance(raw_args, dict)
                                else str(raw_args)
                            )
                            yield {
                                "type": "tool_call_chunk",
                                "index": i,
                                "id": f"call_{i}",
                                "name": tc_data.get("name"),
                                "args": args_str,
                            }
                        pending_tools.clear()
                        yield {
                            "type": "usage",
                            "input": data.get("prompt_eval_count", 0),
                            "output": data.get("eval_count", 0),
                        }

    async def complete(self, messages: list, response_format: dict | None = None) -> dict:
        """Not supported for Ollama backend — structured output is Mercury-only."""
        raise NotImplementedError("OllamaBackend does not support complete()")

    async def generate(
        self, messages: list, tools: list | None = None, response_format: dict | None = None
    ) -> dict:
        """Not supported for Ollama backend — Mercury-only."""
        raise NotImplementedError("OllamaBackend does not support generate()")


# ---------------------------------------------------------------------------
# MercuryBackend — OpenAI-compatible streaming (Mercury 2 by Inception Labs)
# ---------------------------------------------------------------------------


class MercuryBackend:
    """Uses openai.AsyncOpenAI for Mercury 2 cloud streaming."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        max_tokens: int,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self._client = None
        self._client_key: str = ""

    def _get_client(self):
        from openai import AsyncOpenAI

        from pipeline.lyra.config import get_main_api_key

        current_key = get_main_api_key()
        if self._client is None or self._client_key != current_key:
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=current_key,
                timeout=120.0,
                max_retries=5,
            )
            self._client_key = current_key
        return self._client

    async def stream(
        self, messages: list[BaseMessage], tools: list, enable_thinking: bool = True
    ) -> AsyncIterator[dict]:
        """Stream from Mercury via OpenAI SDK, yielding StreamEvent dicts."""
        client = self._get_client()

        openai_messages = _langchain_messages_to_openai(messages)
        openai_tools = _langchain_tools_to_openai(tools) if tools else None

        create_kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": self.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "reasoning_effort": "high",
            "extra_body": {"diffusing": True},
        }
        if openai_tools:
            create_kwargs["tools"] = openai_tools

        try:
            stream = await client.chat.completions.create(**create_kwargs)
        except Exception as e:
            from pipeline.lyra.config import mark_api_key_exhausted

            msg = str(e).lower()
            if "rate limit" in msg or "429" in msg or "quota" in msg:
                mark_api_key_exhausted()
                client = self._get_client()  # Picks up new key
                stream = await client.chat.completions.create(**create_kwargs)
            else:
                raise

        # Accumulate tool call chunks by index
        tool_calls: dict[int, dict] = {}

        async for chunk in stream:
            if not chunk.choices and chunk.usage:
                # Final chunk with usage only (stream_options includes it)
                yield {
                    "type": "usage",
                    "input": chunk.usage.prompt_tokens or 0,
                    "output": chunk.usage.completion_tokens or 0,
                }
                continue

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Content tokens (diffusion mode: each chunk is a full replacement)
            if delta.content:
                yield {"type": "diffusion", "text": delta.content}

            # Tool call chunks
            if delta.tool_calls:
                for tc_chunk in delta.tool_calls:
                    idx = tc_chunk.index
                    entry = tool_calls.setdefault(idx, {"id": None, "name": None, "args": ""})
                    if tc_chunk.id:
                        entry["id"] = tc_chunk.id
                    if tc_chunk.function and tc_chunk.function.name:
                        entry["name"] = tc_chunk.function.name
                    if tc_chunk.function and tc_chunk.function.arguments:
                        entry["args"] += tc_chunk.function.arguments

            # On finish: yield finalized tool calls
            finish = chunk.choices[0].finish_reason
            if finish == "tool_calls" and tool_calls:
                for idx, tc_data in sorted(tool_calls.items()):
                    yield {
                        "type": "tool_call_chunk",
                        "index": idx,
                        "id": tc_data["id"],
                        "name": tc_data["name"],
                        "args": tc_data["args"],
                    }
                tool_calls.clear()

    async def generate(
        self,
        messages: list,
        tools: list | None = None,
        response_format: dict | None = None,
    ) -> dict:
        """Single non-streaming call that handles tools + structured output.

        Returns {"content": str, "tool_calls": list, "usage": dict}.
        When response_format is set and no tool calls, content is the raw
        structured JSON string (caller parses it).
        """
        import asyncio as _aio

        client = self._get_client()
        openai_messages = _langchain_messages_to_openai(messages)

        create_kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": self.max_tokens,
            "stream": False,
            "reasoning_effort": "high",
        }
        if tools:
            create_kwargs["tools"] = _langchain_tools_to_openai(tools)
        if response_format:
            create_kwargs["response_format"] = response_format

        async def _call() -> dict:
            try:
                resp = await _aio.wait_for(
                    client.chat.completions.create(**create_kwargs), timeout=60.0
                )
            except Exception as e:
                from pipeline.lyra.config import mark_api_key_exhausted

                msg = str(e).lower()
                if "rate limit" in msg or "429" in msg or "quota" in msg:
                    mark_api_key_exhausted()
                    refreshed = self._get_client()
                    resp = await _aio.wait_for(
                        refreshed.chat.completions.create(**create_kwargs), timeout=60.0
                    )
                else:
                    raise

            message = resp.choices[0].message
            content = message.content or ""

            # Guard: Mercury sometimes returns empty content on rate limits
            # or overloaded state.  Raise explicitly so callers can retry.
            if not content.strip() and not message.tool_calls:
                raise ValueError(
                    "Mercury returned empty content with no tool calls — "
                    "likely rate-limited or overloaded"
                )

            result: dict = {
                "content": content,
                "tool_calls": [],
                "usage": {
                    "input": (resp.usage.prompt_tokens or 0) if resp.usage else 0,
                    "output": (resp.usage.completion_tokens or 0) if resp.usage else 0,
                },
            }
            if message.tool_calls:
                for tc in message.tool_calls:
                    result["tool_calls"].append(
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "args": tc.function.arguments,
                        }
                    )
            return result

        return await _call()

    async def complete(self, messages: list, response_format: dict | None = None) -> dict:
        """Non-streaming structured output only (used by judge scorer).

        Returns parsed JSON dict when response_format is json_schema.
        """
        import asyncio as _aio

        client = self._get_client()
        openai_messages = _langchain_messages_to_openai(messages)

        create_kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": self.max_tokens,
            "stream": False,
            "reasoning_effort": "high",
            "temperature": 0.1,
        }
        if response_format:
            create_kwargs["response_format"] = response_format

        async def _call(effort: str = "high") -> dict:
            kw = {**create_kwargs, "reasoning_effort": effort}
            try:
                resp = await _aio.wait_for(client.chat.completions.create(**kw), timeout=30.0)
            except Exception as e:
                from pipeline.lyra.config import mark_api_key_exhausted

                msg = str(e).lower()
                if "rate limit" in msg or "429" in msg or "quota" in msg:
                    mark_api_key_exhausted()
                    refreshed = self._get_client()
                    resp = await _aio.wait_for(
                        refreshed.chat.completions.create(**kw), timeout=30.0
                    )
                else:
                    raise
            content = resp.choices[0].message.content or "{}"
            parsed = json.loads(content)
            # Validate text field
            text = parsed.get("text", "")
            if response_format and not text.strip():
                raise ValueError("Structured output returned empty text")
            # Filter out empty site IDs
            if "sites" in parsed:
                parsed["sites"] = [s for s in parsed["sites"] if s.get("id", "").strip()]
            return parsed

        try:
            return await _call("high")
        except TimeoutError:
            logger.warning("complete() timed out with effort=high, retrying with medium")
            return await _call("medium")


# ---------------------------------------------------------------------------
# Backend factory — creates singleton backends keyed by model name
# ---------------------------------------------------------------------------

_backends: dict[str, LLMBackend] = {}


def get_backend(
    model_name: str,
    backend_type: str,
    num_ctx: int | None = None,
    max_tokens: int | None = None,
    base_url: str | None = None,
) -> LLMBackend:
    """Get or create a backend instance for the given model.

    Args:
        model_name: The model to use (e.g. "qwen3.5:4b", "mercury-2").
        backend_type: "local" for OllamaBackend, "mercury" for MercuryBackend.
        num_ctx: Override context window size (local only). Defaults to LYRA_OLLAMA_NUM_CTX env.
        max_tokens: Override max output tokens (local only). Defaults to 1024.
        base_url: Override base URL (local only). Bypasses LYRA_OLLAMA_BASE_URL.
    """
    key = f"{backend_type}:{model_name}:{num_ctx}:{max_tokens}:{base_url}"
    if key not in _backends:
        if backend_type == "local":
            ctx = num_ctx or int(os.getenv("LYRA_OLLAMA_NUM_CTX", "4096"))
            mt = max_tokens or 1024
            url = base_url if base_url is not None else os.getenv("LYRA_OLLAMA_BASE_URL", "")
            _backends[key] = OllamaBackend(
                model=model_name,
                base_url=url,
                api_key=os.getenv("LYRA_OLLAMA_API_KEY", "") if not base_url else "",
                max_tokens=mt,
                num_ctx=ctx,
            )
            logger.info(f"Created OllamaBackend for {model_name} at {url}")
        else:
            from pipeline.lyra.config import get_main_api_key, get_max_tokens

            api_key = get_main_api_key()
            mercury_url = os.getenv("LYRA_BASE_URL", "") or os.getenv(
                "LYRA_ANTHROPIC_BASE_URL", "https://api.inceptionlabs.ai/v1"
            )

            _backends[key] = MercuryBackend(
                model=model_name,
                api_key=api_key,
                base_url=mercury_url,
                max_tokens=get_max_tokens(),
            )
            logger.info(f"Created MercuryBackend for {model_name}")
    return _backends[key]
