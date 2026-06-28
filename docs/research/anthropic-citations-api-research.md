# Anthropic Citations API - Research Report

**Date:** 2026-03-28
**Purpose:** Exact API format for building inline [N] web citations in chat responses

---

## 1. How to Enable Citations

Citations are enabled **per-document** or **per-search-result**, NOT as a top-level API parameter. You set `"citations": {"enabled": true}` on each content block that should be citable.

**Supported models:** All active models EXCEPT Haiku 3.

**Incompatibility:** Citations CANNOT be used with Structured Outputs (`output_config.format` / `output_format`). Returns 400 error.

---

## 2. Three Distinct Citation Systems

There are actually THREE ways to get citations, and they use different content block types and produce different citation formats:

### System A: Document Citations (for your own documents)

Content block type: `"type": "document"`

Source types:
- `"type": "text"` (plain text, sentence-chunked)
- `"type": "base64"` (PDFs, page-chunked)
- `"type": "content"` (custom chunks, no auto-chunking)
- `"type": "file"` (Files API reference)

Citation response types:
- `char_location` (plain text)
- `page_location` (PDFs)
- `content_block_location` (custom content)

### System B: Search Result Citations (for RAG with URLs) -- THIS IS WHAT YOU WANT

Content block type: `"type": "search_result"`

Citation response type: `search_result_location` (includes `source` URL and `title`)

### System C: Web Search Tool Citations (automatic, encrypted)

Tool type: `"web_search_20250305"` or `"web_search_20260209"`

Citation response type: `web_search_result_location` (includes `url`, `title`, `encrypted_index`)

---

## 3. System B Deep Dive: Search Result Citations (for inline [N] web citations)

This is the system designed for RAG applications where you want citations pointing back to URLs.

### Request Format - Search Result Block

```json
{
  "type": "search_result",
  "source": "https://example.com/article",
  "title": "Article Title",
  "content": [
    {
      "type": "text",
      "text": "The actual content of the search result..."
    }
  ],
  "citations": {
    "enabled": true
  }
}
```

Required fields:
| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Must be `"search_result"` |
| `source` | string | The source URL or identifier |
| `title` | string | Descriptive title for the search result |
| `content` | array | Array of `{"type": "text", "text": "..."}` blocks |

Optional fields:
| Field | Type | Description |
|-------|------|-------------|
| `citations` | object | `{"enabled": true}` |
| `cache_control` | object | `{"type": "ephemeral"}` |

### Two Ways to Provide Search Results

**Method 1: As top-level content in user messages (pre-fetched data)**

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 1024,
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "search_result",
          "source": "https://docs.company.com/api-reference",
          "title": "API Reference - Authentication",
          "content": [
            {
              "type": "text",
              "text": "All API requests must include an API key in the Authorization header."
            }
          ],
          "citations": {"enabled": true}
        },
        {
          "type": "search_result",
          "source": "https://docs.company.com/quickstart",
          "title": "Getting Started Guide",
          "content": [
            {
              "type": "text",
              "text": "To get started: 1) Sign up, 2) Generate API key, 3) Install SDK."
            }
          ],
          "citations": {"enabled": true}
        },
        {
          "type": "text",
          "text": "How do I authenticate API requests?"
        }
      ]
    }
  ]
}
```

**Method 2: As tool_result content (dynamic RAG via tool calls)**

```python
# Define your search tool
knowledge_base_tool = {
    "name": "search_knowledge_base",
    "description": "Search the knowledge base",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}

# When Claude calls the tool, return SearchResultBlockParam objects
tool_result = [
    SearchResultBlockParam(
        type="search_result",
        source="https://example.com/page1",
        title="Page Title",
        content=[
            TextBlockParam(type="text", text="Content from the page...")
        ],
        citations={"enabled": True},
    ),
]

# Send back as tool_result
final_response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "original question"},
        {"role": "assistant", "content": response.content},
        {
            "role": "user",
            "content": [
                ToolResultBlockParam(
                    type="tool_result",
                    tool_use_id=tool_use_block.id,
                    content=tool_result,  # search_result blocks go here
                )
            ],
        },
    ],
)
```

### Response Format for Search Result Citations

```json
{
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "To authenticate API requests, you need to include an API key"
    },
    {
      "type": "text",
      "text": "in the Authorization header",
      "citations": [
        {
          "type": "search_result_location",
          "source": "https://docs.company.com/api-reference",
          "title": "API Reference - Authentication",
          "cited_text": "All API requests must include an API key in the Authorization header",
          "search_result_index": 0,
          "start_block_index": 0,
          "end_block_index": 0
        }
      ]
    },
    {
      "type": "text",
      "text": ". The rate limits are 1,000 requests per hour for standard tier.",
      "citations": [
        {
          "type": "search_result_location",
          "source": "https://docs.company.com/api-reference",
          "title": "API Reference - Authentication",
          "cited_text": "Rate limits: 1000 requests per hour for standard tier, 10000 for premium",
          "search_result_index": 0,
          "start_block_index": 0,
          "end_block_index": 0
        }
      ]
    }
  ]
}
```

### Citation Fields (search_result_location)

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"search_result_location"` |
| `source` | string | The source URL from the original search result |
| `title` | string/null | The title from the original search result |
| `cited_text` | string | The exact text being cited |
| `search_result_index` | integer | 0-based index of the search result |
| `start_block_index` | integer | Starting position in the content array |
| `end_block_index` | integer | Ending position in the content array |

---

## 4. Web Search Tool Citations (System C)

When using the built-in `web_search` tool, citations are **always enabled automatically**. You do NOT control the content -- Anthropic fetches it and encrypts it.

### Request

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 1024,
  "messages": [{"role": "user", "content": "Who is Claude Shannon?"}],
  "tools": [{
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
    "allowed_domains": ["example.com"],
    "blocked_domains": ["spam.com"]
  }]
}
```

### Response Structure

```json
{
  "role": "assistant",
  "content": [
    {"type": "text", "text": "I'll search for that."},
    {
      "type": "server_tool_use",
      "id": "srvtoolu_01WYG3...",
      "name": "web_search",
      "input": {"query": "claude shannon birth date"}
    },
    {
      "type": "web_search_tool_result",
      "tool_use_id": "srvtoolu_01WYG3...",
      "content": [
        {
          "type": "web_search_result",
          "url": "https://en.wikipedia.org/wiki/Claude_Shannon",
          "title": "Claude Shannon - Wikipedia",
          "encrypted_content": "EqgfCioIARgBIiQ3YTAw...",
          "page_age": "April 30, 2025"
        }
      ]
    },
    {"type": "text", "text": "Based on the search results, "},
    {
      "type": "text",
      "text": "Claude Shannon was born on April 30, 1916",
      "citations": [
        {
          "type": "web_search_result_location",
          "url": "https://en.wikipedia.org/wiki/Claude_Shannon",
          "title": "Claude Shannon - Wikipedia",
          "encrypted_index": "Eo8BCioIAhgBIiQyYjQ0...",
          "cited_text": "Claude Elwood Shannon (April 30, 1916 - February 24, 2001)..."
        }
      ]
    }
  ]
}
```

### Web Search Citation Fields (web_search_result_location)

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"web_search_result_location"` |
| `url` | string | URL of the cited source |
| `title` | string | Title of the cited source |
| `encrypted_index` | string | Opaque reference for multi-turn (must pass back) |
| `cited_text` | string | Up to 150 chars of cited content |

**Key difference from search_result_location:** Web search citations use `url` (not `source`) and `encrypted_index` (not `search_result_index`/`start_block_index`/`end_block_index`).

---

## 5. Can Citations Work WITH Web Search Tool Results?

**Yes, but they are two different systems that produce different citation types.**

### Scenario A: Use web_search tool and get automatic citations

- You get `web_search_result_location` citations with `url`, `title`, `encrypted_index`
- The `encrypted_content` in search results is opaque -- you cannot read or modify it
- Citations are always enabled for web search (no opt-in needed)
- In multi-turn, you must pass back `encrypted_content` and `encrypted_index` verbatim

### Scenario B: Do your own search, pass results as search_result blocks

- You get `search_result_location` citations with `source`, `title`, `search_result_index`
- You control the content -- pass whatever text you want
- You must set `citations.enabled = true` on each block
- The `source` field is your URL -- it comes back in citations unchanged

### Scenario C: Combine both in one request

The docs mention `RequestSearchResultBlock` in the incompatibility warning alongside Document blocks, suggesting they CAN coexist with web search tool in the same request. Web search results get `web_search_result_location` citations; your search_result blocks get `search_result_location` citations.

---

## 6. Building Inline [N] Citations: Implementation Strategy

For your use case (inline [N] web citations in a chat response), **System B (search_result blocks)** is the right approach:

```python
# 1. Do your own web search (via your own search API, Qdrant, etc.)
# 2. Package results as search_result blocks with URLs

search_results = []
for i, result in enumerate(your_search_results):
    search_results.append({
        "type": "search_result",
        "source": result["url"],       # This URL comes back in citations
        "title": result["title"],       # This title comes back in citations
        "content": [
            {"type": "text", "text": result["snippet"]}
        ],
        "citations": {"enabled": True}
    })

# 3. Send to Claude
response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=2048,
    messages=[{
        "role": "user",
        "content": search_results + [
            {"type": "text", "text": user_question}
        ]
    }]
)

# 4. Parse response: build [N] references
sources = {}  # url -> index
output_parts = []

for block in response.content:
    if block.type == "text":
        text = block.text
        if hasattr(block, 'citations') and block.citations:
            for citation in block.citations:
                url = citation.source
                title = citation.title
                if url not in sources:
                    sources[url] = {"index": len(sources) + 1, "title": title, "url": url}
                text += f" [{sources[url]['index']}]"
        output_parts.append(text)

final_text = "".join(output_parts)
# Append reference list
for info in sorted(sources.values(), key=lambda x: x["index"]):
    final_text += f"\n[{info['index']}] {info['title']} - {info['url']}"
```

---

## 7. Token Cost Notes

- `cited_text` does NOT count toward output tokens
- `cited_text` does NOT count toward input tokens when passed back in multi-turn
- Enabling citations adds slight input token overhead (system prompt additions + chunking)
- Web search: $10 per 1,000 searches + standard token costs
- Web search result content counts as input tokens

---

## 8. Streaming Support

For streaming, citations arrive as `citations_delta` events:

```
event: content_block_delta
data: {"type": "content_block_delta", "index": 0,
       "delta": {"type": "citations_delta",
                 "citation": {
                     "type": "search_result_location",
                     "source": "https://...",
                     "title": "...",
                     "cited_text": "...",
                     "search_result_index": 0,
                     "start_block_index": 0,
                     "end_block_index": 0
                 }}}
```

---

## 9. Summary of All Citation Types

| Citation Type | Source Block Type | Key Fields | Use Case |
|---|---|---|---|
| `char_location` | `document` (text) | `document_index`, `start_char_index`, `end_char_index` | Plain text docs |
| `page_location` | `document` (PDF) | `document_index`, `start_page_number`, `end_page_number` | PDF docs |
| `content_block_location` | `document` (content) | `document_index`, `start_block_index`, `end_block_index` | Custom chunks |
| `search_result_location` | `search_result` | `source` (URL), `title`, `search_result_index`, `start_block_index`, `end_block_index` | RAG with URLs |
| `web_search_result_location` | `web_search_result` (auto) | `url`, `title`, `encrypted_index` | Built-in web search |
