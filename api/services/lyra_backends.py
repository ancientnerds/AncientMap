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
        self,
        messages: list,
        tools: list | None = None,
        response_format: dict | None = None,
        max_tokens: int | None = None,
        tool_choice: str | None = None,
        citations: bool = False,
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
        self,
        messages: list,
        tools: list | None = None,
        response_format: dict | None = None,
        max_tokens: int | None = None,
        tool_choice: str | None = None,
        citations: bool = False,
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

        from pipeline.lyra.config import get_api_key

        current_key = get_api_key()
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

        stream = await client.chat.completions.create(**create_kwargs)

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
        max_tokens: int | None = None,
        tool_choice: str | None = None,
        citations: bool = False,
    ) -> dict:
        """Single non-streaming call that handles tools + structured output.

        Returns {"content": str, "tool_calls": list, "usage": dict}.
        When response_format is set and no tool calls, content is the raw
        structured JSON string (caller parses it).

        Args:
            max_tokens: Override instance max_tokens. Structured output calls
                should cap at 4096 (reasoning_effort="high" shares the budget).
            tool_choice: "none" to prevent tool calls, "auto" (default), etc.
        """
        import asyncio as _aio

        client = self._get_client()
        openai_messages = _langchain_messages_to_openai(messages)

        create_kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": max_tokens or self.max_tokens,
            "stream": False,
            "reasoning_effort": "high",
        }
        if tools:
            create_kwargs["tools"] = _langchain_tools_to_openai(tools)
            if tool_choice:
                create_kwargs["tool_choice"] = tool_choice
        if response_format:
            create_kwargs["response_format"] = response_format

        async def _call() -> dict:
            resp = await _aio.wait_for(
                client.chat.completions.create(**create_kwargs), timeout=60.0
            )

            choice = resp.choices[0]
            message = choice.message
            content = message.content or ""
            finish_reason = choice.finish_reason

            logger.debug(
                f"Mercury generate: finish_reason={finish_reason}, "
                f"content_len={len(content)}, "
                f"tokens={resp.usage.completion_tokens if resp.usage else '?'}"
            )

            # When no tools were requested, Mercury may still return
            # tool_calls if the message history contains tool call patterns.
            # Ignore spurious tool_calls — only content matters.
            effective_tool_calls = message.tool_calls if tools else None

            # Guard: Mercury sometimes returns empty content on rate limits
            # or overloaded state.  Raise explicitly so callers can retry.
            if not content.strip() and not effective_tool_calls:
                raise ValueError(
                    f"Mercury returned empty content "
                    f"(finish_reason={finish_reason}, "
                    f"spurious_tool_calls={bool(message.tool_calls)}) — "
                    "likely rate-limited or overloaded"
                )

            # Guard: if Mercury stopped due to length, the JSON is truncated
            # and will fail to parse. Raise explicitly so callers can retry.
            if finish_reason == "length" and response_format:
                raise ValueError(
                    f"Mercury response truncated (finish_reason=length, "
                    f"{len(content)} chars, "
                    f"{resp.usage.completion_tokens if resp.usage else '?'} tokens) — "
                    "hit max_tokens limit"
                )

            result: dict = {
                "content": content,
                "tool_calls": [],
                "usage": {
                    "input": (resp.usage.prompt_tokens or 0) if resp.usage else 0,
                    "output": (resp.usage.completion_tokens or 0) if resp.usage else 0,
                },
            }
            if effective_tool_calls:
                for tc in effective_tool_calls:
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
            "max_tokens": 4096,  # Structured output: cap tokens (reasoning shares budget)
            "stream": False,
            "reasoning_effort": "high",
            "temperature": 0.1,
        }
        if response_format:
            create_kwargs["response_format"] = response_format

        async def _call(effort: str = "high") -> dict:
            kw = {**create_kwargs, "reasoning_effort": effort}
            resp = await _aio.wait_for(client.chat.completions.create(**kw), timeout=30.0)
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
# AnthropicBackend — Anthropic native SDK (Haiku 4.5 / Sonnet / Opus)
# ---------------------------------------------------------------------------


class AnthropicBackend:
    """Uses anthropic.AsyncAnthropic for native Claude API (no OpenAI compat layer)."""

    def __init__(self, model: str, api_key: str, max_tokens: int):
        import anthropic as _anthropic

        self.model = model
        self.max_tokens = max_tokens
        self._client = _anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0)

    def _to_anthropic_messages(self, messages: list) -> tuple[str, list]:
        """Convert LangChain messages to Anthropic format.

        Returns (system_text, anthropic_messages). Consecutive ToolMessages are
        grouped into a single user message (Anthropic requires alternating roles).
        """
        system_parts: list[str] = []
        anthropic_msgs: list[dict] = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_parts.append(str(msg.content))
            elif isinstance(msg, HumanMessage):
                anthropic_msgs.append({"role": "user", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                if msg.tool_calls:
                    content: list[dict] = []
                    if msg.content:
                        content.append({"type": "text", "text": str(msg.content)})
                    for tc in msg.tool_calls:
                        args = tc["args"]
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except (json.JSONDecodeError, ValueError):
                                args = {}
                        content.append(
                            {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": args}
                        )
                    anthropic_msgs.append({"role": "assistant", "content": content})
                else:
                    anthropic_msgs.append({"role": "assistant", "content": str(msg.content)})
            elif isinstance(msg, ToolMessage):
                # Group consecutive ToolMessages into one user message
                if (
                    anthropic_msgs
                    and anthropic_msgs[-1]["role"] == "user"
                    and isinstance(anthropic_msgs[-1]["content"], list)
                    and anthropic_msgs[-1]["content"]
                    and anthropic_msgs[-1]["content"][0].get("type") == "tool_result"
                ):
                    anthropic_msgs[-1]["content"].append(
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": str(msg.content),
                        }
                    )
                else:
                    anthropic_msgs.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": msg.tool_call_id,
                                    "content": str(msg.content),
                                }
                            ],
                        }
                    )

        return "\n\n".join(system_parts), anthropic_msgs

    def _to_anthropic_tools(self, openai_tools: list | None) -> list[dict]:
        """Convert OpenAI function-calling format to Anthropic format."""
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in (openai_tools or [])
            if t.get("type") == "function"
        ]

    def _to_output_config(self, response_format: dict) -> dict:
        """Convert Mercury/OpenAI json_schema format to Anthropic output_config."""
        # Input:  {"type": "json_schema", "json_schema": {"name": ..., "strict": True, "schema": {...}}}
        # Output: {"format": {"type": "json_schema", "schema": {...}}}
        return {"format": {"type": "json_schema", "schema": response_format["json_schema"]["schema"]}}

    async def generate(
        self,
        messages: list,
        tools: list | None = None,
        response_format: dict | None = None,
        max_tokens: int | None = None,
        tool_choice: str | None = None,
        citations: bool = False,
    ) -> dict:
        """Single non-streaming call. Returns {"content", "tool_calls", "usage"}.

        citations=True: wraps last user message as document + question block for
        automatic source attribution (Pass 1 prose). Incompatible with response_format.
        """
        system_text, anthropic_msgs = self._to_anthropic_messages(messages)

        if citations and not response_format:
            # Citations path: wrap last user message as document + text question block
            last_user_idx = None
            for i in range(len(anthropic_msgs) - 1, -1, -1):
                if anthropic_msgs[i]["role"] == "user":
                    last_user_idx = i
                    break

            if last_user_idx is not None and isinstance(
                anthropic_msgs[last_user_idx]["content"], str
            ):
                raw = anthropic_msgs[last_user_idx]["content"]
                if "\n\n## Question\n" in raw:
                    parts = raw.split("\n\n## Question\n", 1)
                    retrieved_data = parts[0]
                    question = parts[1]
                else:
                    retrieved_data = ""
                    question = raw

                content_blocks: list[dict] = []
                if retrieved_data:
                    content_blocks.append(
                        {
                            "type": "document",
                            "source": {
                                "type": "text",
                                "media_type": "text/plain",
                                "data": retrieved_data,
                            },
                            "title": "Retrieved Data",
                            "citations": {"enabled": True},
                        }
                    )
                content_blocks.append({"type": "text", "text": question})
                anthropic_msgs[last_user_idx] = {"role": "user", "content": content_blocks}

            create_kwargs: dict = {
                "model": self.model,
                "messages": anthropic_msgs,
                "max_tokens": max_tokens or self.max_tokens,
            }
            if system_text:
                create_kwargs["system"] = system_text

            resp = await self._client.messages.create(**create_kwargs)
            text = "".join(b.text for b in resp.content if hasattr(b, "text") and b.type == "text")
            return {
                "content": text,
                "tool_calls": [],
                "usage": {
                    "input": resp.usage.input_tokens if resp.usage else 0,
                    "output": resp.usage.output_tokens if resp.usage else 0,
                },
            }

        # Standard path: tools and/or structured output
        anthropic_tools = self._to_anthropic_tools(
            _langchain_tools_to_openai(tools) if tools else None
        )
        create_kwargs = {
            "model": self.model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if system_text:
            create_kwargs["system"] = [
                {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}
            ]
        if anthropic_tools:
            create_kwargs["tools"] = anthropic_tools
            if tool_choice == "any":
                create_kwargs["tool_choice"] = {"type": "any"}
            elif tool_choice == "none":
                create_kwargs["tool_choice"] = {"type": "none"}
        if response_format:
            create_kwargs["output_config"] = self._to_output_config(response_format)

        resp = await self._client.messages.create(**create_kwargs)

        tool_calls_out: list[dict] = []
        text_out = ""
        for block in resp.content:
            if hasattr(block, "type"):
                if block.type == "tool_use":
                    tool_calls_out.append(
                        {
                            "id": block.id,
                            "name": block.name,
                            "args": json.dumps(block.input)
                            if isinstance(block.input, dict)
                            else str(block.input),
                        }
                    )
                elif block.type == "text":
                    text_out += block.text

        return {
            "content": text_out,
            "tool_calls": tool_calls_out,
            "usage": {
                "input": resp.usage.input_tokens if resp.usage else 0,
                "output": resp.usage.output_tokens if resp.usage else 0,
            },
        }

    async def stream(
        self, messages: list[BaseMessage], tools: list, enable_thinking: bool = True
    ) -> AsyncIterator[dict]:
        """Stream from Anthropic, yielding normalized StreamEvent dicts."""
        system_text, anthropic_msgs = self._to_anthropic_messages(messages)
        anthropic_tools = self._to_anthropic_tools(
            _langchain_tools_to_openai(tools) if tools else None
        )

        stream_kwargs: dict = {
            "model": self.model,
            "messages": anthropic_msgs,
            "max_tokens": self.max_tokens,
        }
        if system_text:
            stream_kwargs["system"] = [
                {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}
            ]
        if anthropic_tools:
            stream_kwargs["tools"] = anthropic_tools

        _input_tokens = 0
        async with self._client.messages.stream(**stream_kwargs) as stream:
            async for event in stream:
                if event.type == "message_start":
                    if hasattr(event, "message") and event.message.usage:
                        _input_tokens = event.message.usage.input_tokens
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield {"type": "content", "text": event.delta.text}
                    elif event.delta.type == "input_json_delta":
                        yield {
                            "type": "tool_call_chunk",
                            "index": event.index,
                            "id": None,
                            "name": None,
                            "args": event.delta.partial_json,
                        }
                elif event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        yield {
                            "type": "tool_call_chunk",
                            "index": event.index,
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "args": "",
                        }
                elif event.type == "message_delta":
                    if event.usage:
                        yield {
                            "type": "usage",
                            "input": _input_tokens,
                            "output": event.usage.output_tokens,
                        }

    async def complete(self, messages: list, response_format: dict | None = None) -> dict:
        """Non-streaming structured output (used by judge scorer)."""
        return await self.generate(
            messages,
            response_format=response_format,
            max_tokens=4096,
            tool_choice="none",
        )


# ---------------------------------------------------------------------------
# Backend factory — creates singleton backends keyed by model name
# ---------------------------------------------------------------------------

# NOTE: Safe while keys are derived from static env vars (~3 entries).
# If max_tokens/num_ctx ever become user-configurable, add an LRU eviction policy.
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
        model_name: The model to use (e.g. "qwen3.5:4b", "mercury-2", "claude-haiku-4-5").
        backend_type: "local" for OllamaBackend, "mercury" for MercuryBackend, "anthropic" for AnthropicBackend.
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
        elif backend_type == "anthropic":
            from pipeline.lyra.config import get_max_tokens

            api_key = os.getenv("LYRA_ANTHROPIC_API_KEY") or os.getenv("LYRA_API_KEY", "")
            _backends[key] = AnthropicBackend(
                model=model_name,
                api_key=api_key,
                max_tokens=max_tokens or get_max_tokens(),
            )
            logger.info(f"Created AnthropicBackend for {model_name}")
        else:
            from pipeline.lyra.config import get_api_key, get_max_tokens

            api_key = get_api_key()
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
