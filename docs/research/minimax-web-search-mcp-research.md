# MiniMax Web Search MCP & M2.7 API Research

**Date:** 2026-03-30
**Status:** Complete

---

## 1. MiniMax Web Search MCP -- How It Works

MiniMax provides **two distinct MCP server implementations** for web search:

### A. Coding Plan / Token Plan MCP (`minimax-coding-plan-mcp`)

This is the official MCP server bundled with your Token Plan subscription. It provides two tools:

- **`web_search`** -- Searches the web via MiniMax's own search API
- **`understand_image`** -- Analyzes images using MiniMax's vision model

**Key detail:** This MCP server calls MiniMax's **proprietary search endpoint** directly. It does NOT use third-party services (no Serper, no Jina). Your Token Plan API key (`sk-cp-...`) authenticates directly against MiniMax's servers.

**API Endpoint Called:**
```
POST {MINIMAX_API_HOST}/v1/coding_plan/search
```

**Request Format:**
```json
{
  "q": "search query string"
}
```

**Headers:**
```
Content-Type: application/json
Authorization: Bearer sk-cp-YOUR_TOKEN_PLAN_KEY
```

**Installation & Configuration (for Claude Code / Cursor / etc.):**
```json
{
  "mcpServers": {
    "MiniMax": {
      "command": "uvx",
      "args": ["minimax-coding-plan-mcp", "-y"],
      "env": {
        "MINIMAX_API_KEY": "sk-cp-YOUR_KEY",
        "MINIMAX_API_HOST": "https://api.minimax.io"
      }
    }
  }
}
```

**Transport:** stdio (default, local) or SSE (network/cloud deployment).

**Package:** `minimax-coding-plan-mcp` v0.0.4 on PyPI (MIT license).

### B. MiniMax Search MCP (`minimax_search`)

A separate open-source MCP server from MiniMax that uses **third-party APIs**:

- **Serper API** (Google Search) for web search
- **Jina Reader** for web page content extraction
- **MiniMax LLM** for content comprehension

This requires three separate API keys (`SERPER_API_KEY`, `JINA_API_KEY`, `MINIMAX_API_KEY`). This is NOT what you get with the Token Plan -- it's a standalone tool.

---

## 2. Web Search Response Format (Structured Data)

The Coding Plan MCP's `web_search` tool returns **structured JSON** with the following schema:

```json
{
  "base_resp": {
    "status_code": 0,
    "status_msg": "success"
  },
  "organic": [
    {
      "title": "Article Title",
      "link": "https://example.com/article",
      "snippet": "Brief excerpt of the page content...",
      "date": "2026-03-25"
    }
  ],
  "related_searches": [
    { "query": "related search suggestion 1" },
    { "query": "related search suggestion 2" }
  ]
}
```

**Fields in each organic result:**
| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Page/article title |
| `link` | string | Full URL |
| `snippet` | string | Excerpt (truncated to ~200 chars in formatted output) |
| `date` | string | Publication date |

**Error codes in `base_resp.status_code`:**
| Code | Meaning |
|------|---------|
| 0 | Success |
| 1004 | Invalid API key (wrong key type or region mismatch) |
| 2038 | Real-name verification required |

**Formatted output** (what the MCP client receives): Numbered organic results with title, URL, snippet, and date, followed by a "Related Searches" section with numbered suggestions.

---

## 3. MiniMax OpenAI-Compatible API

### Base URL
```
https://api.minimax.io/v1
```

For Anthropic SDK compatibility:
```
https://api.minimax.io/anthropic
```

### Chat Completions Endpoint
```
POST https://api.minimax.io/v1/chat/completions
```

### Authentication
```bash
export OPENAI_BASE_URL=https://api.minimax.io/v1
export OPENAI_API_KEY=sk-api-YOUR_PAY_AS_YOU_GO_KEY
# OR for Token Plan:
export OPENAI_API_KEY=sk-cp-YOUR_TOKEN_PLAN_KEY
```

### Available Models (all 204,800 token context)
| Model | Speed | Notes |
|-------|-------|-------|
| MiniMax-M2.7 | 60 tps | Latest, recursive self-improvement |
| MiniMax-M2.7-highspeed | 100 tps | Faster variant, identical results |
| MiniMax-M2.5 | 60 tps | Previous generation |
| MiniMax-M2.5-highspeed | 100 tps | Faster variant |
| MiniMax-M2.1 | 60 tps | Programming focus |
| MiniMax-M2.1-highspeed | 100 tps | Faster variant |
| MiniMax-M2 | -- | Original agentic model |

### Python Example
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.minimax.io/v1",
    api_key="sk-cp-YOUR_KEY"
)

response = client.chat.completions.create(
    model="MiniMax-M2.7",
    messages=[{"role": "user", "content": "Hello"}],
    extra_body={"reasoning_split": True}  # optional: separate thinking
)
```

### Key Parameters
- **temperature**: Range (0.0, 1.0], recommended 1.0
- **reasoning_split**: Boolean -- separates thinking into `reasoning_details` field
- **stream**: Boolean for streaming
- **tool_calls**: Supported (function calling / tool use)
- **response_format**: Supported

### Unsupported Parameters
`presence_penalty`, `frequency_penalty`, `logit_bias`, image/audio inputs via chat, `n > 1`

### Response Format
Standard OpenAI format with extensions:
```json
{
  "choices": [{
    "message": {
      "content": "response text",
      "reasoning_details": "thinking content (when reasoning_split=true)",
      "tool_calls": [...]
    }
  }]
}
```

---

## 4. M2.7 Context Window

- **Context window:** 204,800 tokens (~200K)
- **Maximum output:** 131,072 tokens (~128K)
- **Reasoning model:** Uses extended thinking / chain-of-thought
- **Important:** Reasoning tokens share the `max_tokens` budget. The model may terminate early when approaching context capacity.
- **Recommended total budget:** Up to 200,000 input+output tokens per conversation for best efficiency.

---

## 5. MCP Documentation

### Official Documentation
- **Token Plan MCP Guide:** https://platform.minimax.io/docs/token-plan/mcp-guide
- **Token Plan Overview:** https://platform.minimax.io/docs/token-plan/intro
- **M2.7 Usage Tips:** https://platform.minimax.io/docs/token-plan/best-practices
- **OpenAI-Compatible API:** https://platform.minimax.io/docs/api-reference/text-openai-api

### GitHub Repositories
- **Coding Plan MCP (official):** https://github.com/MiniMax-AI/MiniMax-Coding-Plan-MCP
- **MiniMax Search (standalone):** https://github.com/MiniMax-AI/minimax_search
- **MiniMax MCP (TTS/image/video):** https://github.com/MiniMax-AI/MiniMax-MCP

### PyPI Package
- **Package:** `minimax-coding-plan-mcp` v0.0.4
- **Install:** `pip install minimax-coding-plan-mcp`

---

## 6. Token Plan API Access

### Plan Evolution
On March 23, 2026, MiniMax upgraded its "Coding Plan" to the "Token Plan" -- expanding from text-only to all-modal access (text, speech, image, video, music) under a single subscription and API key.

### API Key Types
| Key Format | Type | Usage |
|------------|------|-------|
| `sk-cp-...` | Token Plan (subscription) | Fixed monthly fee, request quotas |
| `sk-api-...` | Pay-as-you-go | Per-token billing, no quotas |

**These keys are NOT interchangeable.** A Token Plan key cannot be used with pay-as-you-go endpoints and vice versa.

### Token Plan Tiers

| Feature | Starter ($10/mo) | Plus ($20/mo) | Max ($50/mo) |
|---------|-------------------|---------------|--------------|
| M2.7 requests / 5hrs | 1,500 | 4,500 | **15,000** |
| Speech 2.8 (chars/day) | -- | 4,000 | 11,000 |
| Image-01 (images/day) | -- | 50 | 120 |
| Hailuo video (gens/day) | -- | -- | 2 |
| Music-2.5 (songs/day) | -- | -- | 4 |
| Web Search MCP | Yes | Yes | Yes |
| Image Understanding MCP | Yes | Yes | Yes |

### Rate Limiting
- **M2.7:** Rolling 5-hour window (e.g., Max plan = 15,000 requests per 5-hour window)
- **Other models (speech, image, video, music):** Daily quotas
- **No per-second rate limit documented** -- the 5-hour window is the primary throttle

### High-Speed Plans
Also available: Plus-Highspeed and Ultra-Highspeed variants with higher quotas (Ultra-Highspeed: 30,000 requests/5hrs).

### Checking Remaining Quota
```
GET https://api.minimaxi.com/v1/api/openplatform/coding_plan/remains
Authorization: Bearer sk-cp-YOUR_KEY
```
(Note: endpoint path still uses `coding_plan` naming despite rebrand to Token Plan.)

---

## Key Findings for AncientMap Integration

### Relevance Assessment

The MiniMax web search MCP is primarily designed as a **coding assistant tool** (for IDE integrations like Cursor, Claude Code, etc.). For the AncientMap project's use case (adding web search citations to Lyra responses), there are two paths:

1. **Direct API call to `/v1/coding_plan/search`**: Could be called from Python code using the Token Plan key. Returns structured results with title, link, snippet, date. This is the simplest integration path.

2. **Use MiniMax M2.7 with tool calling**: Have M2.7 invoke web search as a tool during response generation. This would require building the tool-calling loop yourself.

### Comparison with Current Approach
The project currently has web search disabled pending citation accuracy issues (per git history: `feat: hide web search toggle -- disabled pending citation accuracy`). The MiniMax search API returns structured results that include URLs and snippets, which could be used for citation generation. However, the search endpoint is tied to a Token Plan subscription key and is designed for coding workflows, not general-purpose web search.

### Cost Consideration
With the Max plan at $50/month and 15,000 requests per 5-hour window, the search API is effectively unlimited for the project's needs (Lyra pipeline runs periodically, not continuously). The search calls would be included in the subscription -- no per-query cost.
