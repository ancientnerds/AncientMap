# Inception Labs Mercury API -- Complete Reference Documentation

> **Compiled**: 2026-03-09
> **Note**: The official docs site (docs.inceptionlabs.ai) returns 403 to automated fetchers.
> This reference was assembled from the llms.txt index, OpenRouter model pages,
> third-party articles (DataCamp, COEY, The Decoder, DigitalApplied, AnalyticsVidhya),
> the mercury-client SDK, the OpenClaw GitHub issue #26952, Artificial Analysis,
> Benchable.ai, and web search snippets that extracted content from the docs site.

---

## Table of Contents

1. [Models, Endpoints, and Pricing](#1-models-endpoints-and-pricing)
2. [Chat Completions](#2-chat-completions)
3. [API Parameters](#3-api-parameters)
4. [Streaming and Diffusion](#4-streaming-and-diffusion)
5. [Structured Outputs](#5-structured-outputs)
6. [Tool Use (Function Calling)](#6-tool-use-function-calling)
7. [Rate Limits](#7-rate-limits)
8. [Error Codes](#8-error-codes)
9. [Authentication](#9-authentication)
10. [SDK and Client Libraries](#10-sdk-and-client-libraries)

---

## 1. Models, Endpoints, and Pricing

### Available Models

| Model ID | Type | Context Window | Max Output | Input Price (per 1M tokens) | Output Price (per 1M tokens) | Cached Input (per 1M tokens) |
|---|---|---|---|---|---|---|
| `mercury-2` | Reasoning dLLM | 128,000 | 50,000 | $0.25 | $0.75 | $0.025 |
| `mercury` | General dLLM | 128,000 | 32,000 | $0.25 | $1.00 | $0.025 |
| `mercury-coder` | Code-focused dLLM | 128,000 | 32,000 | $0.25 | $1.00 | -- |
| `mercury-edit` | Code editing dLLM | 128,000 | 32,000 | $0.25 | $0.75 | -- |

### Base URL

```
https://api.inceptionlabs.ai/v1
```

### Endpoints

| Endpoint | Description | Supported Models |
|---|---|---|
| `/v1/chat/completions` | Chat completions (OpenAI-compatible) | mercury-2, mercury, mercury-coder |
| `/v1/fim/completions` | Fill-in-the-middle completions | mercury-coder, mercury-edit |
| `/v1/apply/completions` | Code apply/edit completions | mercury-edit |
| `/v1/edit/completions` | Code edit completions | mercury-edit |

### Key Model Facts

- **Mercury 2** (released 2026-02-20): First reasoning diffusion LLM. Generates and refines multiple tokens in parallel. Achieves ~1,000 tokens/sec on H100 GPUs, ~1,196 tokens/sec on Blackwell GPUs. Supports tunable reasoning levels, native tool use, and schema-aligned JSON output.
- **Mercury** (released 2025-06-26): Original diffusion LLM. 5-10x faster than GPT-4.1 Nano and Claude 3.5 Haiku.
- **Mercury Coder**: Coding-focused variant. Up to 1,100 tokens/sec on H100 GPUs.
- **Mercury Edit**: Specialized for code editing tasks (apply-edit workflows).

### Availability

- **Direct API**: api.inceptionlabs.ai
- **OpenRouter**: openrouter.ai/inception/mercury-2
- **AWS**: Amazon Bedrock Marketplace, SageMaker JumpStart
- **Azure**: Azure AI Foundry
- **Chat Interface**: chat-mercury2.inceptionlabs.ai (free, no account required)

---

## 2. Chat Completions

The API is OpenAI-compatible. You can use existing OpenAI client libraries or direct REST calls.

### curl Example

```bash
curl https://api.inceptionlabs.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $INCEPTION_API_KEY" \
  -d '{
    "model": "mercury-2",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What is a diffusion language model?"}
    ],
    "max_tokens": 10000
  }'
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-inception-api-key",
    base_url="https://api.inceptionlabs.ai/v1"
)

response = client.chat.completions.create(
    model="mercury-2",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is a diffusion language model?"}
    ],
    max_tokens=10000
)

print(response.choices[0].message.content)
```

### Streaming Example

```python
stream = client.chat.completions.create(
    model="mercury-2",
    messages=[
        {"role": "user", "content": "Explain quantum computing"}
    ],
    max_tokens=10000,
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Message Roles

The messages array supports standard OpenAI roles:
- `"system"` -- System instructions
- `"user"` -- User messages
- `"assistant"` -- Assistant responses (for conversation history)
- `"tool"` -- Tool call results (when using function calling)

---

## 3. API Parameters

### Standard Parameters (OpenAI-compatible)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `model` | string | *required* | Model identifier: `"mercury-2"`, `"mercury"`, `"mercury-coder"`, `"mercury-edit"` |
| `messages` | array | *required* | Array of message objects with `role` and `content` |
| `max_tokens` | integer | varies | Maximum number of tokens to generate in the response |
| `temperature` | float | 1.0 | Controls randomness. Values like 0.0 for deterministic output |
| `top_p` | float | 1.0 | Nucleus sampling parameter |
| `stop` | string or array | null | Stop sequence(s) to halt generation |
| `stream` | boolean | false | Whether to stream the response |
| `stream_options` | object | null | Options for streaming, e.g. `{"include_usage": true}` |
| `tools` | array | null | Array of tool/function definitions |
| `tool_choice` | string/object | "auto" | Controls tool calling behavior: `"auto"`, `"required"`, `"none"`, or specific function |
| `response_format` | object | null | Structured output format specification |
| `n` | integer | 1 | Number of completions to generate |

### Mercury-Specific Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `diffusing` | boolean | true (for mercury-2) | Controls whether the model uses diffusion-based parallel generation. When `true`, generates tokens in parallel via iterative denoising. When `false`, forces standard autoregressive mode (negates speed advantages). |
| `reasoning_effort` | string | "medium" | Controls reasoning depth. Values: `"none"`, `"low"`, `"medium"`, `"high"`. Higher values = more diffusion refinement passes = better quality but slower and more expensive. Only supported by `mercury-2`. |
| `include_reasoning` | boolean | false | Whether to include the model's reasoning/thinking process in the response. Only supported by `mercury-2`. |

### Using Mercury-Specific Parameters with OpenAI SDK

Since `diffusing` and `reasoning_effort` are not standard OpenAI parameters, pass them via `extra_body`:

```python
response = client.chat.completions.create(
    model="mercury-2",
    messages=[
        {"role": "user", "content": "Explain the Riemann hypothesis"}
    ],
    max_tokens=10000,
    extra_body={
        "diffusing": True,
        "reasoning_effort": "high"
    }
)
```

### Direct REST Call with Mercury Parameters

```bash
curl https://api.inceptionlabs.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $INCEPTION_API_KEY" \
  -d '{
    "model": "mercury-2",
    "messages": [
      {"role": "user", "content": "Explain the Riemann hypothesis"}
    ],
    "max_tokens": 10000,
    "diffusing": true,
    "reasoning_effort": "high"
  }'
```

### Reasoning Effort Behavior

| Level | Behavior | Use Case |
|---|---|---|
| `"none"` | No reasoning, fastest output | Simple lookups, reformatting |
| `"low"` | Minimal refinement passes | Simple Q&A, obvious answers |
| `"medium"` | Balanced refinement (default) | General conversation, moderate complexity |
| `"high"` | Maximum refinement passes | Complex reasoning, nuanced analysis, math |

Example: When asked "should I walk or drive to a car wash 2 blocks away?"
- **Low**: "Walk, it's close."
- **High**: Considers whether the car wash is drive-through (walking is illogical) or self-service (walking may be viable), producing a more contextually accurate answer.

---

## 4. Streaming and Diffusion

### Standard Streaming

Standard streaming works identically to OpenAI's streaming API. Set `"stream": true` and receive Server-Sent Events (SSE) with incremental deltas.

```python
stream = client.chat.completions.create(
    model="mercury-2",
    messages=[{"role": "user", "content": "Write a poem about the sea"}],
    max_tokens=2000,
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Diffusion Streaming

When `diffusing` is set to `true` (the default for mercury-2), the model uses its native diffusion-based generation. In streaming mode with diffusion enabled, the model streams blocks of tokens that are progressively refined:

1. The model generates a rough draft of the full response in parallel
2. It then iteratively denoises and refines the output over multiple steps (typically 8-20 passes)
3. During streaming, intermediate "noisy" drafts are sent as chunks, showing the refinement process

**Key billing detail**: The noisy/intermediate tokens returned during diffusion streaming are NOT counted for billing. You only pay for the final refined output tokens.

```python
# Diffusion streaming -- visualize the refinement process
response = client.chat.completions.create(
    model="mercury-2",
    messages=[{"role": "user", "content": "What is quantum computing?"}],
    max_tokens=1000,
    stream=True,
    extra_body={
        "diffusing": True
    }
)

for chunk in response:
    if chunk.choices[0].delta and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Direct REST -- Diffusion Streaming

```bash
curl https://api.inceptionlabs.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $INCEPTION_API_KEY" \
  -d '{
    "model": "mercury-2",
    "messages": [
      {"role": "user", "content": "What is quantum computing?"}
    ],
    "max_tokens": 1000,
    "stream": true,
    "diffusing": true
  }'
```

### How Diffusion Differs from Autoregressive Streaming

| Aspect | Autoregressive (diffusing=false) | Diffusion (diffusing=true) |
|---|---|---|
| Token generation | Sequential, one at a time | Parallel, full draft refined iteratively |
| Streaming behavior | Token-by-token deltas | Block-by-block refinement |
| Speed | Standard (~100-150 tok/s) | ~1,000+ tok/s |
| Intermediate tokens | All tokens are final | Noisy tokens refined progressively |
| Billing | All streamed tokens counted | Only final tokens counted |
| Adaptive steps | N/A | 8 steps for simple, 16-20 for complex |
| KV Cache | Required (grows with context) | Not needed (KV-cache free) |

### Performance Characteristics

- **Time to First Token (TTFT)**: ~3.0-3.5 seconds (slower than autoregressive competitors)
- **Output Throughput**: ~629-1,196 tokens/second (depending on GPU)
- **End-to-End Latency**: ~1.7 seconds for typical responses
- A 2,500-token article generates in under 2.5 seconds vs. 20-30 seconds for autoregressive models

---

## 5. Structured Outputs

Mercury supports structured output via the `response_format` parameter, following the OpenAI-compatible format. Mercury 2 supports schema-aligned JSON output natively.

### JSON Mode (Simple)

```python
response = client.chat.completions.create(
    model="mercury-2",
    messages=[
        {"role": "system", "content": "Respond in JSON format."},
        {"role": "user", "content": "List 3 programming languages with their year of creation"}
    ],
    max_tokens=1000,
    response_format={"type": "json_object"}
)

print(response.choices[0].message.content)
# {"languages": [{"name": "Python", "year": 1991}, ...]}
```

### JSON Schema Mode (Strict)

```python
response = client.chat.completions.create(
    model="mercury-2",
    messages=[
        {"role": "user", "content": "Extract the key entities from: 'Apple released the iPhone 16 in September 2024 for $799'"}
    ],
    max_tokens=1000,
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "entity_extraction",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "product": {"type": "string"},
                    "date": {"type": "string"},
                    "price": {"type": "number"}
                },
                "required": ["company", "product", "date", "price"],
                "additionalProperties": False
            }
        }
    }
)
```

### curl -- Structured Output

```bash
curl https://api.inceptionlabs.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $INCEPTION_API_KEY" \
  -d '{
    "model": "mercury-2",
    "messages": [
      {"role": "user", "content": "List the planets in our solar system"}
    ],
    "max_tokens": 2000,
    "response_format": {
      "type": "json_schema",
      "json_schema": {
        "name": "planets",
        "strict": true,
        "schema": {
          "type": "object",
          "properties": {
            "planets": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "name": {"type": "string"},
                  "order_from_sun": {"type": "integer"},
                  "type": {"type": "string", "enum": ["terrestrial", "gas_giant", "ice_giant"]}
                },
                "required": ["name", "order_from_sun", "type"],
                "additionalProperties": false
              }
            }
          },
          "required": ["planets"],
          "additionalProperties": false
        }
      }
    }
  }'
```

### OpenAI Python SDK with Pydantic (beta parse)

Since the API is OpenAI-compatible, you can use the `beta.chat.completions.parse()` method with Pydantic models:

```python
from pydantic import BaseModel
from openai import OpenAI

client = OpenAI(
    api_key="your-inception-api-key",
    base_url="https://api.inceptionlabs.ai/v1"
)

class Step(BaseModel):
    explanation: str
    output: str

class MathReasoning(BaseModel):
    steps: list[Step]
    final_answer: str

response = client.beta.chat.completions.parse(
    model="mercury-2",
    messages=[
        {"role": "system", "content": "You are a math tutor. Show your work step by step."},
        {"role": "user", "content": "What is 25 * 37?"}
    ],
    response_format=MathReasoning
)

result = response.choices[0].message.parsed
print(result.final_answer)
```

### Supported response_format Types

| Type | Description |
|---|---|
| `{"type": "text"}` | Default. Unstructured text output. |
| `{"type": "json_object"}` | Forces valid JSON output. Requires "JSON" in system/user message. |
| `{"type": "json_schema", "json_schema": {...}}` | Forces output to conform to a specific JSON schema. |

### Quality Notes on Structured Output

Per third-party testing:
- **Strong performance (90-95% accuracy)**: JSON/structured outputs, translation, summarization, standard code patterns
- **Weaker performance (85-90% accuracy)**: Complex multi-step reasoning, long-form creative writing
- Mercury 2 handles schema-constrained JSON reliably for: query planning, tool argument generation, structured state passing between steps, verification pipelines where deterministic formatting matters

### Lessons Learned (from AncientMap Lyra implementation, Mar 2026)

Validated against 48 end-to-end tests with Mercury as both chat LLM and LLM judge:

| Lesson | Detail |
|--------|--------|
| **`reasoning_effort="high"` shares `max_tokens` budget** | Reasoning and completion tokens come from the same pool. With `max_tokens=1024`, reasoning consumed ~900 tokens leaving 0 for JSON output → empty response. **Fix**: Use `max_tokens=4096` for structured output calls. |
| **Cap `max_tokens` for `complete()` vs streaming** | Streaming uses large `max_tokens` (32000) for long responses, but passing that to non-streaming `complete()` with `reasoning_effort="high"` exhausts the output token rate limit. **Fix**: `min(self.max_tokens, 4096)`. |
| **Temperature per call type** | `temperature=0.1` for structured output formatting and LLM judge scoring (deterministic). Default `0.75` for creative chat streaming. Don't use the same temperature for everything. |
| **Zero parse failures with `strict: true`** | `response_format: json_schema` with `strict: true` produced valid JSON 100% of the time across 48 calls — far better than assistant prefill or regex extraction. |
| **Model names can go defunct without warning** | `mercury-coder-small-beta` stopped working mid-development. Always verify model availability with a curl test before committing to a model name. |
| **LLM judge with structured output** | Using Mercury with `response_format: json_schema` as an LLM judge eliminated 30% JSON parse failures that occurred with free-form judge output from other models. |
| **Key pool rotation** | Round-robin across multiple API keys with 60s cooldown per exhausted key prevented rate limiting across 48 sequential judge calls. |

---

## 6. Tool Use (Function Calling)

Mercury supports OpenAI-compatible tool/function calling on the `/v1/chat/completions` endpoint.

### Defining Tools

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit"
                    }
                },
                "required": ["location"]
            }
        }
    }
]
```

### Making a Tool Call Request

```python
response = client.chat.completions.create(
    model="mercury-2",
    messages=[
        {"role": "user", "content": "What's the weather like in Paris?"}
    ],
    tools=tools,
    tool_choice="auto"
)

message = response.choices[0].message

if message.tool_calls:
    for tool_call in message.tool_calls:
        print(f"Function: {tool_call.function.name}")
        print(f"Arguments: {tool_call.function.arguments}")
        # tool_call.function.arguments is a JSON string
```

### Handling Tool Call Responses

```python
import json

# Step 1: Initial request
messages = [{"role": "user", "content": "What's the weather in Paris?"}]

response = client.chat.completions.create(
    model="mercury-2",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)

assistant_message = response.choices[0].message

# Step 2: If the model wants to call a tool
if assistant_message.tool_calls:
    # Add assistant's response to messages
    messages.append(assistant_message)

    for tool_call in assistant_message.tool_calls:
        # Execute the function (your implementation)
        args = json.loads(tool_call.function.arguments)
        result = get_weather(args["location"], args.get("unit", "celsius"))

        # Add tool result to messages
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result)
        })

    # Step 3: Get final response with tool results
    final_response = client.chat.completions.create(
        model="mercury-2",
        messages=messages,
        tools=tools
    )
    print(final_response.choices[0].message.content)
```

### curl -- Tool Use

```bash
curl https://api.inceptionlabs.ai/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $INCEPTION_API_KEY" \
  -d '{
    "model": "mercury-2",
    "messages": [
      {"role": "user", "content": "What is the weather in Paris?"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get the current weather in a given location",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {
                "type": "string",
                "description": "City and state"
              },
              "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"]
              }
            },
            "required": ["location"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }'
```

### tool_choice Options

| Value | Behavior |
|---|---|
| `"auto"` | Model decides whether to call a tool or respond directly |
| `"required"` | Model must call at least one tool |
| `"none"` | Model must not call any tools |
| `{"type": "function", "function": {"name": "get_weather"}}` | Force a specific function call |

### Mercury Client SDK -- Tool Use

```python
from mercury_client import MercuryClient
from mercury_client.models import Tool, FunctionDefinition

client = MercuryClient()

tools = [
    Tool(
        type="function",
        function=FunctionDefinition(
            name="get_weather",
            description="Get current weather for a location",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        )
    )
]

response = client.chat_completion(
    messages=[{"role": "user", "content": "What's the weather in Paris?"}],
    tools=tools,
    tool_choice="auto"
)
```

---

## 7. Rate Limits

Specific rate limit numbers are not publicly documented in detail. What is known:

- **Free tier**: New API keys come with 10 million free tokens.
- Rate limits are enforced. Exceeding them returns HTTP 429 with a `Retry-After` header.
- The mercury-client SDK includes built-in exponential backoff retry with configurable `RetryConfig`.
- For production usage and higher rate limits, contact support@inceptionlabs.ai or apply via platform.inceptionlabs.ai.

### Error Response for Rate Limiting

```json
{
  "error": {
    "message": "Rate limit exceeded. Please wait before trying again.",
    "type": "rate_limit_error",
    "code": 429
  }
}
```

---

## 8. Error Codes

The API returns standard HTTP error codes:

| Code | Error | Description |
|---|---|---|
| 400 | Bad Request | Invalid request parameters |
| 401 | Authentication Error | Invalid or missing API key |
| 403 | Forbidden | API key lacks required permissions |
| 404 | Not Found | Invalid endpoint or model |
| 429 | Rate Limit Exceeded | Too many requests; respect `Retry-After` header |
| 500 | Server Error | Internal server error |
| 503 | Service Unavailable | Server overloaded or under maintenance |

### Mercury Client SDK Error Types

```python
from mercury_client.exceptions import (
    AuthenticationError,      # 401
    RateLimitError,           # 429 -- has .retry_after attribute
    ServerError,              # 500
    EngineOverloadedError     # 503
)
```

---

## 9. Authentication

All API requests require a Bearer token in the Authorization header.

### Getting an API Key

1. Sign up at https://platform.inceptionlabs.ai
2. Generate an API key from the dashboard
3. New keys include 10 million free tokens

### Usage

**Header format**:
```
Authorization: Bearer YOUR_INCEPTION_API_KEY
```

**Environment variable** (recommended):
```bash
export INCEPTION_API_KEY="sk_your_api_key_here"
```

**OpenAI SDK**:
```python
client = OpenAI(
    api_key=os.environ["INCEPTION_API_KEY"],
    base_url="https://api.inceptionlabs.ai/v1"
)
```

### Data Policy

- No training on prompts
- No data/prompt retention

---

## 10. SDK and Client Libraries

### OpenAI Python SDK (Recommended)

The API is fully OpenAI-compatible. Use the standard OpenAI SDK:

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-inception-api-key",
    base_url="https://api.inceptionlabs.ai/v1"
)
```

### Mercury Client SDK (Third-Party)

A dedicated Python SDK (by hamzaamjad):

```bash
pip install mercury-api-client
```

```python
from mercury_client import MercuryClient

client = MercuryClient(api_key="sk_your_key")

# Sync
response = client.chat_completion(
    messages=[{"role": "user", "content": "Hello"}],
    model="mercury-2"
)

# Async
from mercury_client import AsyncMercuryClient
async with AsyncMercuryClient() as client:
    response = await client.chat_completion(...)

# Streaming
for chunk in client.chat_completion_stream(
    messages=[{"role": "user", "content": "Write a story"}],
    max_tokens=1000
):
    if chunk.choices[0].delta and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# FIM (Fill-in-the-Middle)
response = client.fim_completion(
    prompt="def fibonacci(",
    suffix=" return a + b",
    max_tokens=100
)
```

### Other Integrations

- **LangChain**: Works via OpenAI-compatible adapter
- **LiteLLM**: Works via OpenAI-compatible adapter
- **AISuite**: Native support
- **Mastra** (TypeScript): Native provider support
- **OpenRouter**: Available as `inception/mercury-2`

---

## Appendix A: Mercury 2 Benchmarks

| Benchmark | Mercury 2 | Claude 4.5 Haiku (Reasoning) | Gemini 3 Flash (Reasoning) |
|---|---|---|---|
| **E2E Latency** | 1.7s | 23.4s | 14.4s |
| **GPQA Diamond** | 74 | 67 | 90 |
| **LiveCodeBench** | 67 | 62 | 91 |
| **SciCode** | 38 | 43 | 51 |
| **IFBench** | 71 | 54 | 78 |
| **AIME 2025** | 91 | 84 | 78 |
| **TAU** | 53 | 55 | 80 |

### Artificial Analysis Rankings (out of 134 models)

- Intelligence: #23 (score: 33)
- Speed: #1 (629.2 tok/s)
- Coding: score 30.6

### Benchable.ai Results

| Benchmark | Accuracy | Rank |
|---|---|---|
| Hallucinations | 98.0% | 98/317 |
| Reasoning | 96.0% | 46/342 |
| Email Classification | 97.0% | 233/418 |
| Instruction Following | 53.6% | 210/418 |
| General Knowledge | 8.0% | 376/421 |
| Coding | 67.0% | 301/406 |
| Mathematics | 58.0% | 212/272 |
| Ethics | 94.0% | 314/412 |

---

## Appendix B: Diffusion Architecture Notes

### How Diffusion LLMs Work

Unlike autoregressive models that predict tokens sequentially (next token -> next token -> next), Mercury uses a discrete diffusion approach:

1. **Masked Diffusion**: Uses a discrete token corruption process optimized for language (not continuous embeddings like image diffusion models)
2. **Parallel Generation**: Generates a rough draft of the full response concurrently
3. **Iterative Denoising**: Refines the draft through multiple passes (typically 8-20 steps)
4. **Adaptive Steps**: 8 steps for simple outputs, 16-20 for complex tasks
5. **KV-Cache Free**: Eliminates the memory bottleneck of growing KV caches in autoregressive models

### Strengths

- Extreme throughput (~1,000 tok/s)
- Cost-effective for batch workloads
- Keeps GPUs busy with larger work chunks
- No sequential decoding bottleneck

### Weaknesses

- Higher Time to First Token (~3.0-3.5s vs ~0.5-1.0s for autoregressive)
- Output length must be pre-estimated internally (no natural stop token in the diffusion sense)
- Reasoning depth constrained by simultaneous token processing
- Immature ecosystem with fewer production patterns

### When to Use Diffusion vs Autoregressive

| Use Case | Recommended Mode |
|---|---|
| Real-time chat requiring snappy responses | Diffusion (`diffusing: true`) |
| Voice assistants with low-latency requirements | Diffusion |
| Batch processing (10,000+ documents) | Diffusion |
| Complex multi-step reasoning | Autoregressive (`diffusing: false`) or `reasoning_effort: "high"` |
| Token-by-token streaming UX | Autoregressive (`diffusing: false`) |
| Long-form creative writing | Autoregressive |

---

## Appendix C: Source URLs

### Official

- Docs site: https://docs.inceptionlabs.ai (403 to automated fetchers)
- Platform/API keys: https://platform.inceptionlabs.ai
- Chat (free): https://chat-mercury2.inceptionlabs.ai
- Blog: https://www.inceptionlabs.ai/blog/introducing-inception-api
- Models page: https://www.inceptionlabs.ai/models
- llms.txt: https://docs.inceptionlabs.ai/llms.txt

### Third-Party References

- OpenRouter Mercury 2: https://openrouter.ai/inception/mercury-2
- Artificial Analysis: https://artificialanalysis.ai/models/mercury-2
- Benchable.ai: https://benchable.ai/models/inception/mercury-2
- DataCamp Tutorial: https://www.datacamp.com/tutorial/mercury-2-tutorial
- COEY Analysis: https://coey.com/resources/blog/2026/02/24/inception-labs-mercury-2-makes-text-ai-feel-live-and-thats-the-point/
- The Decoder: https://the-decoder.com/inception-launches-mercury-2-the-first-diffusion-based-language-reasoning-model/
- DigitalApplied Guide: https://www.digitalapplied.com/blog/inception-labs-mercury-2-diffusion-llm-speed-guide
- AnalyticsVidhya: https://www.analyticsvidhya.com/blog/2026/02/mercury-2-the-ai-model-that-feels-instant/
- Mercury Client SDK: https://github.com/hamzaamjad/mercury-client
- OpenClaw Issue #26952: https://github.com/openclaw/openclaw/issues/26952
- AWS Blog: https://aws.amazon.com/blogs/machine-learning/mercury-foundation-models-from-inception-labs-are-now-available-in-amazon-bedrock-marketplace-and-amazon-sagemaker-jumpstart/
- Mastra Docs: https://mastra.ai/models/providers/inception
