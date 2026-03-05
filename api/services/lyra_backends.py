"""
Unified LLM backend abstraction for Lyra.

All backends normalize output to the same StreamEvent dicts:
  {"type": "reasoning", "text": str}
  {"type": "content", "text": str}
  {"type": "tool_call_chunk", "index": int, "id": str|None, "name": str|None, "args": str}
  {"type": "usage", "input": int, "output": int}
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from typing import Any, Protocol

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
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


# ---------------------------------------------------------------------------
# OllamaBackend — raw openai.AsyncOpenAI (preserves reasoning field)
# ---------------------------------------------------------------------------


class OllamaBackend:
    """Wraps raw openai.AsyncOpenAI for Ollama, preserving the `reasoning` field."""

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
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key or "unused",
                timeout=300.0,
            )
        return self._client

    async def stream(
        self, messages: list[BaseMessage], tools: list, enable_thinking: bool = True
    ) -> AsyncIterator[dict]:
        """Stream from Ollama, preserving reasoning tokens.

        Args:
            enable_thinking: If False, uses Ollama's native API with think=false
                to skip chain-of-thought reasoning (faster responses, fewer tokens).

        Yields StreamEvent dicts.
        """
        if not enable_thinking:
            async for ev in self._stream_nothink(messages, tools):
                yield ev
            return

        async for ev in self._stream_openai(messages, tools):
            yield ev

    async def _stream_openai(self, messages: list[BaseMessage], tools: list) -> AsyncIterator[dict]:
        """Stream via OpenAI SDK — supports reasoning tokens and tool calls."""
        client = self._get_client()
        openai_messages = _langchain_messages_to_openai(messages)
        openai_tools = _langchain_tools_to_openai(tools) if tools else []

        kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        if self.num_ctx:
            kwargs["extra_body"] = {"num_ctx": self.num_ctx}
        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(**kwargs)

        async for chunk in response:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue
            delta = choice.delta

            # Reasoning tokens (Ollama/Qwen3 specific field)
            reasoning = getattr(delta, "reasoning", None) or ""
            if not reasoning and hasattr(delta, "model_extra") and delta.model_extra:
                reasoning = delta.model_extra.get("reasoning", "")
            if reasoning:
                yield {"type": "reasoning", "text": reasoning}

            # Content tokens
            if delta.content:
                yield {"type": "content", "text": delta.content}

            # Tool call chunks
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    yield {
                        "type": "tool_call_chunk",
                        "index": tc.index,
                        "id": tc.id,
                        "name": tc.function.name if tc.function else None,
                        "args": tc.function.arguments if tc.function else "",
                    }

            # Usage (final chunk)
            if chunk.usage:
                yield {
                    "type": "usage",
                    "input": chunk.usage.prompt_tokens or 0,
                    "output": chunk.usage.completion_tokens or 0,
                }

    async def _stream_nothink(
        self, messages: list[BaseMessage], tools: list
    ) -> AsyncIterator[dict]:
        """Stream via Ollama native API with think=false (OpenAI SDK ignores this param)."""
        import httpx

        openai_messages = _langchain_messages_to_openai(messages)
        openai_tools = _langchain_tools_to_openai(tools) if tools else []

        # Ollama native /api/chat uses slightly different field names
        body: dict = {
            "model": self.model,
            "messages": openai_messages,
            "think": False,
            "stream": True,
        }
        if self.num_ctx:
            body["options"] = {"num_ctx": self.num_ctx}
        if openai_tools:
            body["tools"] = openai_tools

        # Derive native API URL from the OpenAI-compat base_url
        # e.g. "http://host:11435/v1" -> "http://host:11435/api/chat"
        native_url = self.base_url.replace("/v1", "").rstrip("/") + "/api/chat"

        headers = {}
        if self.api_key and self.api_key != "unused":
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=300.0) as http:
            async with http.stream("POST", native_url, json=body, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    import json

                    data = json.loads(line)
                    msg = data.get("message", {})

                    # Content tokens
                    if msg.get("content"):
                        yield {"type": "content", "text": msg["content"]}

                    # Tool calls (complete, not chunked in native API)
                    if msg.get("tool_calls"):
                        for i, tc in enumerate(msg["tool_calls"]):
                            fn = tc.get("function", {})
                            yield {
                                "type": "tool_call_chunk",
                                "index": i,
                                "id": f"call_{i}",
                                "name": fn.get("name"),
                                "args": json.dumps(fn.get("arguments", {})),
                            }

                    # Usage (on done=true)
                    if data.get("done"):
                        yield {
                            "type": "usage",
                            "input": data.get("prompt_eval_count", 0),
                            "output": data.get("eval_count", 0),
                        }


# ---------------------------------------------------------------------------
# AnthropicBackend — LangChain ChatAnthropic (for MiniMax / native Anthropic)
# ---------------------------------------------------------------------------


class AnthropicBackend:
    """Wraps LangChain ChatAnthropic for MiniMax/native Anthropic."""

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
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from langchain_anthropic import ChatAnthropic

            is_native = not self.base_url or "anthropic.com" in self.base_url
            kwargs: dict = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "streaming": True,
                "api_key": self.api_key,
            }
            if is_native:
                kwargs["stream_usage"] = True
            if self.base_url:
                kwargs["anthropic_api_url"] = self.base_url
            self._llm = ChatAnthropic(**kwargs)
        return self._llm

    async def stream(
        self, messages: list[BaseMessage], tools: list, enable_thinking: bool = True
    ) -> AsyncIterator[dict]:
        """Stream from MiniMax/Anthropic via LangChain, yielding StreamEvent dicts."""
        llm = self._get_llm()
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        async for chunk in llm_with_tools.astream(messages):
            if isinstance(chunk, AIMessageChunk):
                # Token usage from chunks (Anthropic sends on final chunk)
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    um = chunk.usage_metadata
                    input_t = um.get("input_tokens", 0) or 0
                    output_t = um.get("output_tokens", 0) or 0
                    if input_t or output_t:
                        yield {"type": "usage", "input": input_t, "output": output_t}

                # Content: thinking blocks + text blocks
                if chunk.content:
                    text_content = chunk.content if isinstance(chunk.content, str) else ""
                    thinking_content = ""
                    if isinstance(chunk.content, list):
                        for block in chunk.content:
                            if isinstance(block, dict) and block.get("type") == "thinking":
                                thinking_content += block.get("thinking", "") or block.get(
                                    "text", ""
                                )
                            elif isinstance(block, dict) and block.get("type") == "text":
                                text_content += block.get("text", "")
                            elif isinstance(block, str):
                                text_content += block
                    if thinking_content:
                        yield {"type": "reasoning", "text": thinking_content}
                    if text_content:
                        yield {"type": "content", "text": text_content}

                # Tool call chunks
                if chunk.tool_call_chunks:
                    for tcc in chunk.tool_call_chunks:
                        yield {
                            "type": "tool_call_chunk",
                            "index": tcc.get("index"),
                            "id": tcc.get("id"),
                            "name": tcc.get("name"),
                            "args": tcc.get("args") or "",
                        }


# ---------------------------------------------------------------------------
# Backend factory — creates singleton backends keyed by model name
# ---------------------------------------------------------------------------

_backends: dict[str, LLMBackend] = {}


def get_backend(model_name: str, backend_type: str) -> LLMBackend:
    """Get or create a backend instance for the given model.

    Args:
        model_name: The model to use (e.g. "qwen3.5:4b", "MiniMax-M2.5").
        backend_type: "local" for OllamaBackend, "minimax" for AnthropicBackend.
    """
    key = f"{backend_type}:{model_name}"
    if key not in _backends:
        if backend_type == "local":
            num_ctx = int(os.getenv("LYRA_OLLAMA_NUM_CTX", "4096"))
            _backends[key] = OllamaBackend(
                model=model_name,
                base_url=os.getenv("LYRA_OLLAMA_BASE_URL", ""),
                api_key=os.getenv("LYRA_OLLAMA_API_KEY", ""),
                max_tokens=4096,
                num_ctx=num_ctx,
            )
            logger.info(f"Created OllamaBackend for {model_name}")
        else:
            api_key = os.getenv("LYRA_ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
            base_url = os.getenv("LYRA_ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic")
            from pipeline.lyra.config import get_max_tokens

            _backends[key] = AnthropicBackend(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=get_max_tokens(),
            )
            logger.info(f"Created AnthropicBackend for {model_name}")
    return _backends[key]
