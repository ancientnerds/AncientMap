# Fair Queuing for Shared LLM Inference: Research Report

**Date:** 2026-03-05
**Context:** AncientNerds.com free AI chat (Lyra), single VPS, Qwen3.5 multi-model (4B+0.8B), sequential inference
**Existing code:** `api/services/rate_limiter.py` (sliding window, IP-based, Redis+in-memory)

---

## Table of Contents

1. [Rate Limiting Algorithm Selection](#1-rate-limiting-algorithm-selection)
2. [Fair Queuing in Open-Source LLM Projects](#2-fair-queuing-in-open-source-llm-projects)
3. [Queue Position UX](#3-queue-position-ux)
4. [Per-User Quota with Anonymous Users](#4-per-user-quota-with-anonymous-users)
5. [Burst Allowance Patterns](#5-burst-allowance-patterns)
6. [Graceful Degradation](#6-graceful-degradation)
7. [Recommended Architecture for AncientNerds](#7-recommended-architecture-for-ancientnerds)

---

## 1. Rate Limiting Algorithm Selection

### The Problem: LLM Inference Is Not a Normal API

Standard rate limiting algorithms were designed for APIs where requests complete in
milliseconds. LLM inference on a single Qwen3.5 multi-model (4B+0.8B) instance takes 30-200 seconds per
request with zero concurrency. This fundamentally changes the calculus:

- **Token bucket** allows bursts, but a "burst" of 3 LLM requests means 6-10 minutes
  of exclusive GPU time. The burst tolerance that helps web APIs feels abusive here.
- **Leaky bucket** enforces a constant drain rate, which maps naturally to sequential
  inference (one request exits the "bucket" at a time), but offers no flexibility.
- **Sliding window** tracks actual usage over a rolling period, providing the most
  accurate picture of per-user consumption.

### Algorithm Comparison for Sequential LLM Inference

| Algorithm | Burst Handling | Memory Cost | Fairness | Complexity | Best For |
|-----------|---------------|-------------|----------|------------|----------|
| Token Bucket | Allows configurable bursts | O(1) per user | Moderate — greedy users drain bucket fast | Low | APIs where bursts are legitimate |
| Leaky Bucket | No bursts, constant rate | O(1) per user | High — enforced uniformity | Low | Steady-state throughput control |
| Sliding Window Log | No bursts beyond limit | O(n) per user (stores timestamps) | Highest — exact count | Medium | When accuracy matters, low user count |
| Sliding Window Counter | Approximate burst smoothing | O(1) per user | High — weighted approximation | Low | High-scale approximation |

### Recommendation: Sliding Window Log (what you already have)

The existing `RateLimiter` in `api/services/rate_limiter.py` already implements a
**sliding window log** for the in-memory path (stores timestamps, filters by window).
This is the correct choice for this use case because:

1. **User count is small.** A niche archaeology site will have at most dozens of
   concurrent users. The O(n) memory cost of storing timestamps is negligible.
2. **Accuracy matters more than throughput.** With only one inference slot, every
   request is precious. Approximate algorithms waste capacity or unfairly block users.
3. **The window is long.** For "3 messages per hour" style quotas, a sliding window
   log with ~3 timestamps per user is trivially cheap.
4. **No burst tolerance desired.** The owner wants "3 messages then wait" — no bursts
   beyond the quota. Token bucket's burst feature is a liability here.

However, the existing limiter needs enhancement for the queuing scenario. The current
`_chat_limiter = RateLimiter(max_requests=15, window_seconds=60)` is a rapid-fire
protection (15 req/min), not a fair-use quota limiter. You need two layers:

- **Layer 1 (existing):** Rapid-fire protection — 15 req/min, IP-based. Catches bots.
- **Layer 2 (new):** Fair-use quota — e.g., 5 messages per 2-hour rolling window,
  per-session. This is the one users see and understand.

### Key Insight from Research

The article "Rate Limiting and Backpressure for LLM APIs" (dasroot.net, Feb 2026)
emphasizes that LLM rate limiting should be **token-aware** — one user sending a
200-token prompt is fundamentally different from one sending 20,000 tokens. For
Qwen3.5 multi-model (4B+0.8B) where all requests are roughly similar archaeology questions, this matters
less, but if you add features like "analyze this image" or long document analysis,
consider weighting by estimated inference time.

---

## 2. Fair Queuing in Open-Source LLM Projects

### Ollama (closest to your setup)

Ollama is the most relevant comparison since it often runs single-model inference on
consumer hardware.

**Queue behavior:**
- `OLLAMA_MAX_QUEUE` (default: 512) controls maximum queued requests
- `OLLAMA_NUM_PARALLEL` (default: 1) controls concurrent inference — for 11GB RAM
  with Qwen3.5 multi-model (4B+0.8B), this should be 1
- Requests exceeding `NUM_PARALLEL` are queued FIFO (first-in, first-out)
- When queue exceeds `MAX_QUEUE`, new requests get HTTP 503

**Fairness:** Ollama has NO per-user fairness. It is pure FIFO. A single user can
submit 100 requests and block everyone else. This is explicitly what you want to
avoid.

**Takeaway:** Ollama's queueing is a starting point but must be wrapped with
per-user fairness logic at the application layer.

### vLLM (production-grade, instructive patterns)

vLLM is designed for GPU servers and supports continuous batching, but its fairness
research is directly applicable:

**Scheduling policies:**
- Default: FCFS (first-come-first-served) — same problem as Ollama
- RFC (Resource Fairness Criterion): Tracks cumulative GPU time per tenant
- UFC (User Fairness Criterion): Tracks maximum inter-token latency per user
- Priority scheduling: Requests can carry numerical priority; vLLM reorders both
  running and waiting queues by priority
- **Priority decay** pattern: User A's requests get priorities 0, 1, 2, 3
  respectively — each subsequent request from the same user gets lower priority

**Equinox** (2025 research paper) achieves 13% better fairness than FCFS by using a
dual-counter framework. The key insight: fairness should be measured by *maximum time
any user waits between tokens*, not by aggregate throughput.

**Takeaway:** The priority decay pattern is directly applicable — if a user has 3
messages in the queue, their 3rd message should have the lowest priority so other
users' first messages get served first.

### HuggingFace Text Generation Inference (TGI)

TGI's architecture is relevant for understanding the gateway pattern:

**Architecture:** Router (webserver) buffers client requests, creates batches, sends
gRPC calls to model server. The router is where fairness logic lives.

**Key insight from HuggingFace blog on request queueing:**

> "The key idea is: prioritize requests from different users in our own component
> and not in the inference backend! Typically, you can't change the order of
> requests once they have been sent to the inference engine, so you have to bring
> them in the right order while they are still in the LLM-Server, where we have
> full control."

This means: **do not rely on Ollama's queue for fairness.** Implement a fair queue
in FastAPI, upstream of the Ollama call, and only forward one request at a time.

**Fairness strategies from HuggingFace research:**

| Strategy | How It Works | Applicability |
|----------|-------------|---------------|
| Request-count fair | Round-robin through per-user queues | Perfect for your case |
| Processing-time fair | Prioritize shorter requests | Hard to estimate generation length |
| Priority decay | User's Nth request gets priority N | Excellent anti-hogging |
| Time-per-token threshold | Throttle when TPOT > 150ms | N/A for sequential inference |

### OpenRouter Free Tier (commercial reference)

OpenRouter's approach to free-tier rate limiting:

- **50 requests/day** and **20 requests/minute** for free users
- Three-dimensional control: RPS, RPM, RPD
- During peak times, free-tier users face additional provider rate limiting
- DDoS protection via Cloudflare
- Users with $10+ balance get 1000 calls/day (incentive to upgrade)
- No queue position visibility — just 429 errors

**Takeaway:** The "X per day + X per minute" two-layer approach is standard. The
incentive structure (more quota for paying users) is worth considering if you add
a donation tier.

---

## 3. Queue Position UX

### Best Practices from Nielsen Norman Group (NN/g)

NN/g's "13 Best Practices for Virtual Queues" provides the gold standard for queue UX.
The most relevant practices for an LLM chat queue:

**Must-have elements:**

1. **Show position + estimated wait time.** Display "You are #3 in queue. Estimated
   wait: ~2 minutes" — users need both the relative position AND an absolute time
   estimate.

2. **Auto-refresh without manual page reload.** SSE or WebSocket to push queue
   position updates. Include a timestamp showing when the status last updated to
   reassure users the system is working. Never require the user to refresh.

3. **Explain what happens if they leave.** State explicitly: "You can close this tab.
   Your message will still be processed and the response will be waiting when you
   return" — or if that is not the case, say so.

4. **Preview what comes next.** While waiting, show "Lyra is gathering archaeological
   data for your question..." with contextual information about what the AI does
   (searches databases, checks news, etc.).

5. **Communicate queue closure clearly.** If the queue is full (e.g., 10 people
   waiting), say "The queue is currently full. Your message will be queued when a
   spot opens" rather than a cryptic error.

**Nice-to-have elements:**

6. **Notification when ready.** "We'll play a sound when your response is ready" —
   useful if users switch tabs.

7. **Entertainment while waiting.** Show a random archaeology fact, a "did you know"
   card, or a site-of-the-day while the user waits. This is uniquely suited to an
   archaeology site with 750K+ entries.

8. **Quota visibility.** Show "2 of 5 free messages remaining today" persistently
   in the chat UI, not just when the limit is hit.

### Real-World Queue UX Examples

**ChatGPT (2026):** When hitting rate limits, ChatGPT silently downgrades to a
lighter model (GPT-5.2 Mini) rather than queueing. The user keeps chatting but gets
less capable responses. No queue is shown.

**Claude.ai (2026):** Shows a "Usage limit reached" message with a countdown timer
showing when the 5-hour rolling window resets. No queue — just a hard stop with a
timer.

**Midjourney:** Shows "/imagine" queue position as "Position #7 in queue" with
real-time updates. Users see their job move through the queue. This is the closest
analogy to your situation.

**Vercel's AI SDK:** Provides a `useChat` hook with built-in queue position support
via SSE events.

### Recommended UX Flow for AncientNerds

```
User sends message
    |
    v
[Quota check: messages remaining?]
    |
    |-- No --> Show: "You've used all 5 free messages for this period.
    |          Next message available in 47 minutes."
    |          Option: "Switch to MiniMax backend (no queue)"
    |
    |-- Yes --> [Queue position check]
                |
                |-- Position 0 (immediate) --> Start inference, show streaming
                |
                |-- Position 1-5 --> Show: "Lyra is busy helping someone else.
                |                    You're #2 in queue (~1 min wait).
                |                    Did you know? [random archaeology fact]"
                |                    [Auto-updates via SSE every 5 seconds]
                |
                |-- Position 6+ --> Show: "The queue is long right now.
                                    Estimated wait: ~8 minutes.
                                    Try the MiniMax backend for instant responses."
```

---

## 4. Per-User Quota with Anonymous Users

### The Identity Problem

Anonymous users on a free archaeology site present a unique challenge. You need to
identify "the same user" across requests without requiring login, while being
resistant to trivial circumvention.

### Identification Methods Ranked by Suitability

#### 1. Turnstile Token + Server-Side Session (RECOMMENDED)

**How it works:**
- User solves Turnstile challenge (invisible/managed mode)
- Server validates token via Cloudflare Siteverify API
- On successful validation, server issues an **opaque session ID** (UUID) via
  `Set-Cookie` (HttpOnly, SameSite=Strict)
- All subsequent chat requests include this session cookie
- Rate limiting is keyed on the session ID
- Session cookie has a 24h expiry; clearing cookies resets the session

**Properties:**
- Turnstile token is single-use and expires in 5 minutes — it cannot be used as
  a persistent identifier itself
- The session cookie IS the identifier, but it can only be obtained by passing
  Turnstile (bot protection)
- Clearing cookies gives a new session (intentional — this is a free tier, not
  a paywall)
- Turnstile's `idempotency_key` parameter prevents token replay attacks

**Why this is the right choice:**
- Turnstile is already in the stack
- No fingerprinting JS libraries needed (privacy-friendly)
- No login required
- The "clear cookies to reset" escape valve is acceptable for a free service
  (the effort of solving Turnstile again + losing conversation history is enough
  friction to prevent most abuse)

#### 2. IP Address (SUPPLEMENT, NOT PRIMARY)

**Problems:**
- CGNAT: Multiple users behind the same carrier IP (mobile networks, universities)
- VPNs: One user, many IPs
- IPv6 rotation: ISPs rotate /64 prefixes

**Use as:** Secondary defense layer only. Apply a generous per-IP limit (e.g., 20
messages/hour) that only triggers for actual abuse, not normal usage from shared IPs.

#### 3. Device Fingerprinting (OVERKILL)

WorkOS Radar and similar services use 20+ browser signals (canvas, WebGL, fonts,
screen resolution, etc.) to create persistent device fingerprints. This is:
- Privacy-invasive (may violate GDPR expectations for a free archaeology site)
- Requires a JS fingerprinting library (adds weight and complexity)
- Arms race with browsers actively fighting fingerprinting
- Disproportionate for the threat model (this is not a financial service)

**Verdict:** Not recommended. The Turnstile + session cookie approach provides
sufficient identification for a free archaeology chat.

#### 4. Cloudflare Privacy Pass / Anonymous Credentials (FUTURE)

Cloudflare's 2025 "Private Rate Limiting" blog describes Privacy Pass tokens that
are unforgeable and unlinkable — users get N tokens per period, each token allows
one request, but the server cannot correlate tokens to specific users. This is the
privacy-ideal solution but:
- Requires Cloudflare Workers integration
- Still in limited availability
- Overkill for current scale

### Recommended Multi-Layer Identification

```
Layer 1: Turnstile validation (bot protection)
    |
    v
Layer 2: Session cookie (per-user quota, primary key)
    |
    v
Layer 3: IP address (abuse catchall, generous limit)
```

### Handling the "Cookie Clearing" Escape Valve

Users who clear cookies to get a new session will:
1. Need to solve Turnstile again (mild friction)
2. Lose their conversation history (meaningful cost for engaged users)
3. Get a fresh quota (the "exploit")

This is acceptable because:
- The target user is a casual archaeology enthusiast, not a determined adversary
- The total server capacity is ~30 messages/hour anyway — even 3 people abusing
  the system would be noticeable and could be IP-throttled
- Adding more friction (login, fingerprinting) would drive away legitimate users
  more than it would stop abusers

---

## 5. Burst Allowance Patterns

### Industry Survey of Burst/Cooldown Structures

| Service | Free Tier Structure | Window Type | What Happens at Limit |
|---------|-------------------|-------------|----------------------|
| **ChatGPT** (2026) | 10 messages per 5-hour rolling window | Rolling | Silent downgrade to GPT-5.2 Mini |
| **Claude.ai** (2026) | ~15-40 messages per 5-hour rolling window | Rolling | Hard stop with countdown timer |
| **Perplexity** (2026) | Unlimited Quick + 3 Pro searches/day | Fixed daily | Downgrade to Quick search only |
| **OpenRouter** (2026) | 50 requests/day, 20/minute | Fixed daily + per-minute | HTTP 429 error |
| **Midjourney** (free trial) | 25 total image generations | Lifetime cap | Must subscribe |
| **Google Gemini** (free) | ~50 messages/day, varies by model | Rolling | Error message with retry time |

### The "3 Messages Then Wait" Pattern

This pattern (small burst, then cooldown) is actually the most common approach for
resource-constrained free tiers. The key design decisions:

**Window size matters enormously:**
- 3 per hour: Very restrictive. User sends 3 questions, waits 60 minutes. Frustrating
  for someone genuinely exploring the site.
- 3 per 30 minutes: More reasonable. User can have a short conversation, then takes a
  natural break.
- 5 per 2 hours: Allows a meaningful session while preventing hogging. This is closest
  to the ChatGPT and Claude patterns scaled down.

**Rolling vs fixed window:**
- **Rolling window (recommended):** "3 messages in any 60-minute sliding window."
  More fair — the user's oldest message "expires" from the window as time passes.
  Prevents the boundary-burst problem where a user sends 3 messages at 11:59pm and
  3 more at 12:01am (6 messages in 2 minutes with a fixed daily window).
- **Fixed window:** "3 messages per hour, resets on the hour." Simpler to implement
  and communicate, but has the boundary burst problem.

The existing `RateLimiter` class already implements sliding window. This is correct.

### Recommended Burst Structure for AncientNerds

**Proposal: 5 messages per 2-hour rolling window for the local model**

Rationale:
- At ~1-2 minutes per inference, 5 messages = 5-10 minutes of GPU time per user
  per 2-hour window
- With a 2-hour window, the total theoretical capacity is ~30 messages/hour
  (sequential at ~2 min each), serving ~6 concurrent users at full quota
- 5 messages is enough for: greeting + 2 archaeology questions + 2 follow-ups
- The 2-hour window means a user who burns all 5 immediately waits at most 2 hours
  for the first one to expire (and they trickle back in after that)

**With MiniMax fallback: No limit (or a generous 50/day)**

Since MiniMax is a paid API with its own rate limits, the per-user limit should be
much more generous. This creates a natural incentive: use the local model for a few
deep questions, use MiniMax for browsing chat.

### Communication Pattern

Show remaining quota proactively, not reactively:

```
[In chat header, always visible:]
"Local AI: 3 of 5 messages remaining (resets gradually)"

[When 1 message remaining:]
"Last free message for now. Next available in ~24 minutes.
 Tip: Switch to the cloud AI backend for unlimited chat."

[When 0 remaining:]
"Local AI messages used up. Next available in 18 minutes.
 [Switch to Cloud AI]  [Wait for local AI]"
```

---

## 6. Graceful Degradation

### What Happens When the Queue Is Full

For a single-inference-slot system, the queue can fill up quickly. The degradation
strategy should have clear tiers:

**Tier 1: Normal operation (queue 0-2)**
- User submits message, gets immediate or near-immediate processing
- Show "Lyra is thinking..." with streaming response
- No special messaging needed

**Tier 2: Short queue (queue 3-5)**
- User submits message, enters queue
- Show position + estimated wait + archaeology fun fact
- Auto-update position via SSE
- Offer: "Want an instant response? Switch to cloud AI"
- Play notification sound when response ready (if user switches tabs)

**Tier 3: Long queue (queue 6-10)**
- User submits message, enters queue with warning
- Show: "The local AI is busy. Estimated wait: ~8 minutes."
- Prominently offer MiniMax alternative: "Get an answer now with our cloud AI"
- If user chooses to wait, keep them in queue with updates

**Tier 4: Queue full (queue > 10)**
- Reject with clear message: "The local AI queue is full (10 people waiting).
  Please try again in a few minutes or use the cloud AI."
- Do NOT silently queue with a 20-minute wait — that is worse than rejection
- Show a "Notify me when a slot opens" option (via browser notification)

### The MiniMax Fallback Strategy

This is an excellent degradation path because it is not a lesser experience — it is
a different backend with its own tradeoffs:

| Aspect | Local (Qwen3.5 multi-model (4B+0.8B)) | MiniMax (Cloud) |
|--------|-------------------|-----------------|
| Speed | 30-200s | 2-10s |
| Cost to operator | Free (VPS compute) | Per-token API cost |
| Privacy | Data stays on server | Data sent to MiniMax API |
| Quality | 8B model, good for archaeology | Larger model, more general |
| Availability | Single slot, queueable | High availability |

Frame it as a user choice, not a downgrade:
- "Local AI: Private, archaeology-specialized. Limited availability."
- "Cloud AI: Faster, powered by MiniMax. Your question leaves our server."

### Anti-Patterns to Avoid

1. **Do NOT silently switch backends.** ChatGPT's silent downgrade from GPT-5.2 to
   GPT-5.2 Mini is widely criticized. Users should know which backend they are using.

2. **Do NOT show vague error messages.** "Something went wrong" or "Try again later"
   without context is the worst UX. Always explain: what happened, when it will
   resolve, and what the user can do now.

3. **Do NOT queue indefinitely.** A 30-minute wait for a chat message is abandonment.
   Set a maximum queue time (e.g., 10 minutes) and offer alternatives before that.

4. **Do NOT punish users for being patient.** If someone waits in queue, their
   response should be delivered — do not expire their queue position while they wait.

---

## 7. Recommended Architecture for AncientNerds

### System Design

```
                                  +-------------------+
                                  |   Frontend (SSE)  |
                                  |                   |
                                  | - Queue position  |
                                  | - Quota display   |
                                  | - Backend toggle  |
                                  +--------+----------+
                                           |
                                           v
+------------------------------------------+------------------------------------------+
|                            FastAPI Application Layer                                  |
|                                                                                      |
|  +------------------+    +-------------------+    +---------------------+             |
|  | Turnstile Guard  |--->| Session Manager   |--->| Quota Checker       |             |
|  | (bot protection) |    | (cookie-based)    |    | (sliding window)    |             |
|  +------------------+    +-------------------+    +----------+----------+             |
|                                                              |                       |
|                                               +--------------+--------------+        |
|                                               |                             |        |
|                                               v                             v        |
|                                  +-----------+----------+    +-------------+------+  |
|                                  | Fair Queue Manager   |    | MiniMax Direct     |  |
|                                  | (asyncio.Queue)      |    | (no queue needed)  |  |
|                                  | - Per-user fairness  |    +--------------------+  |
|                                  | - Round-robin dequeue|                             |
|                                  | - Position tracking  |                             |
|                                  | - SSE updates        |                             |
|                                  +-----------+----------+                             |
|                                              |                                       |
|                                              v                                       |
|                                  +-----------+----------+                             |
|                                  | Ollama Client        |                             |
|                                  | (1 concurrent req)   |                             |
|                                  +----------------------+                             |
+--------------------------------------------------------------------------------------+
```

### Component Details

#### 1. Session Manager (new)

```python
# Concept — not production code

class SessionManager:
    """Issue and validate session cookies after Turnstile verification."""

    def create_session(self, turnstile_token: str, client_ip: str) -> str:
        """Validate Turnstile, create session, return session_id."""
        # 1. Call Cloudflare Siteverify API
        # 2. Generate UUID session_id
        # 3. Store session_id -> {created_at, ip, message_count: 0}
        # 4. Return session_id (caller sets cookie)

    def get_session(self, session_id: str) -> dict | None:
        """Look up session. Returns None if expired/invalid."""
```

#### 2. Fair Queue Manager (new)

The critical new component. Instead of FIFO, implements round-robin across users:

```python
# Concept — key data structures

class FairQueueManager:
    """Round-robin fair queue for sequential LLM inference."""

    def __init__(self, max_queue_size: int = 10):
        self.max_queue_size = max_queue_size
        # Per-user queues: session_id -> deque of pending requests
        self.user_queues: dict[str, deque[QueuedRequest]] = {}
        # Round-robin order
        self.user_order: deque[str] = deque()
        # Currently processing
        self.active_request: QueuedRequest | None = None
        # Event for signaling queue changes
        self.queue_changed = asyncio.Event()

    async def enqueue(self, session_id: str, request: ChatRequest) -> QueueEntry:
        """Add request to user's queue. Returns QueueEntry with position + Event."""
        # If this user already has 2 requests queued, reject (anti-spam)
        # Add to user's personal queue
        # Add user to round-robin order (if not already present)
        # Return QueueEntry that the caller can await

    async def dequeue_next(self) -> QueuedRequest:
        """Get next request using round-robin across user queues."""
        # Round-robin: advance to next user in user_order
        # Pop from their queue
        # If their queue is now empty, remove from user_order
        # Return the request

    def get_position(self, session_id: str, request_id: str) -> int:
        """Calculate queue position for a specific request."""
        # Simulate round-robin dequeue order to determine position
```

**Why round-robin, not FIFO:**
If User A submits 3 requests and User B submits 1 request:
- FIFO order: A1, A2, A3, B1 (User B waits for all of A's requests)
- Round-robin: A1, B1, A2, A3 (User B's request is served 2nd, not 4th)

#### 3. Queue Position SSE Stream (new)

```python
# Concept — SSE endpoint for queue updates

@router.get("/queue/{request_id}/status")
async def queue_status_stream(request_id: str):
    """SSE stream that pushes queue position updates."""
    async def generate():
        while True:
            entry = queue_manager.get_entry(request_id)
            if entry is None:
                yield sse_event("expired", {"message": "Request not found"})
                return
            if entry.status == "processing":
                yield sse_event("processing", {"message": "Lyra is working..."})
                return
            if entry.status == "complete":
                yield sse_event("complete", {"response_url": f"/queue/{request_id}/result"})
                return

            position = queue_manager.get_position(entry.session_id, request_id)
            estimated_wait = position * 90  # ~90 seconds average per request
            yield sse_event("queued", {
                "position": position,
                "estimated_wait_seconds": estimated_wait,
                "fun_fact": get_random_archaeology_fact(),
            })
            await asyncio.sleep(5)  # Update every 5 seconds

    return StreamingResponse(generate(), media_type="text/event-stream")
```

#### 4. Quota Configuration

```python
# Recommended quota tiers

QUOTAS = {
    "local": {
        "max_messages": 5,
        "window_seconds": 7200,     # 2-hour rolling window
        "max_queued_per_user": 2,   # Max 2 pending requests per user
        "max_queue_total": 10,      # Total queue capacity
    },
    "minimax": {
        "max_messages": 50,
        "window_seconds": 86400,    # 24-hour rolling window
        "max_queued_per_user": 1,   # No queueing needed (fast)
        "max_queue_total": 0,       # Direct execution
    },
}
```

### Frontend Integration Points

The `LyraChatModal.tsx` currently handles streaming responses via SSE. The new queue
system would add a pre-streaming phase:

1. **Send message** -> POST /lyra/chat (returns `{status: "queued", request_id, position}` or `{status: "processing"}`)
2. **If queued** -> Connect to GET /queue/{request_id}/status (SSE)
3. **Show queue UI** -> Position, wait time, fun fact, "switch to cloud" button
4. **When status=processing** -> Transition to existing streaming UI
5. **Quota display** -> GET /lyra/quota returns `{remaining: 3, window_resets_in: 2847, total: 5}`

### What NOT to Build

1. **Redis is optional.** The in-memory path in the existing rate limiter is fine
   for a single-server deployment. Redis adds operational complexity for zero benefit
   at this scale.

2. **No WebSocket needed.** SSE (which is already used for chat streaming) is
   sufficient for queue position updates. WebSocket adds bidirectional complexity
   that is not needed.

3. **No distributed queue.** No Kafka, RabbitMQ, Celery. An `asyncio.Queue` in
   the FastAPI process is correct for single-server, single-worker deployment.

4. **No user accounts for the free tier.** The Discord OAuth login is already
   available for users who want credits and achievements. The free anonymous tier
   should remain frictionless.

5. **No fingerprinting libraries.** FingerprintJS or similar add privacy concerns
   and JavaScript weight for marginal anti-abuse benefit.

---

## Sources

### Rate Limiting Algorithms
- [From Token Bucket to Sliding Window: Pick the Perfect Rate Limiting Algorithm](https://api7.ai/blog/rate-limiting-guide-algorithms-best-practices) — API7.ai
- [Rate Limiting and Backpressure for LLM APIs](https://dasroot.net/posts/2026/02/rate-limiting-backpressure-llm-apis/) — dasroot.net (Feb 2026)
- [Token Bucket vs Leaky Bucket: Pick the Perfect Rate Limiting Algorithm](https://api7.ai/blog/token-bucket-vs-leaky-best-rate-limiting-algorithm) — API7.ai
- [Denial of Wallet: Cost-Aware Rate Limiting for Generative AI Applications](https://handsonarchitects.com/blog/2025/denial-of-wallet-cost-aware-rate-limiting-part-2/) — Hands-on Architects
- [Sliding Window Rate Limiting - Design and Implementation](https://arpitbhayani.me/blogs/sliding-window-ratelimiter/) — Arpit Bhayani
- [How to Implement Sliding Window Rate Limiting in Python](https://oneuptime.com/blog/post/2026-01-21-sliding-window-rate-limiting-python/view) — OneUptime (Jan 2026)

### LLM Fair Queuing
- [Efficient Request Queueing - Optimizing LLM Performance](https://huggingface.co/blog/tngtech/llm-performance-request-queueing) — HuggingFace/TNG Technology
- [Equinox: Holistic Fair Scheduling in Serving LLMs](https://arxiv.org/html/2508.16646) — arXiv (2025)
- [vLLM Priority Scheduling RFC](https://github.com/vllm-project/vllm/issues/6077) — GitHub
- [vLLM SJF Scheduling RFC](https://github.com/vllm-project/vllm/issues/29406) — GitHub
- [How Ollama Handles Parallel Requests](https://www.glukhov.org/post/2025/05/how-ollama-handles-parallel-requests/) — Rost Glukhov (2025)
- [Ollama FAQ - Concurrency](https://docs.ollama.com/faq) — Ollama docs
- [TGI Architecture](https://huggingface.co/docs/text-generation-inference/en/architecture) — HuggingFace

### Queue UX
- [Virtual Queues: 13 Best Practices for Managing the Wait](https://www.nngroup.com/articles/virtual-queue-best-practices/) — Nielsen Norman Group
- [The UX of Waiting](https://medium.com/design-bootcamp/the-ux-of-waiting-247c1d19c11d) — Bootcamp/Medium
- [Design Principles for Effective Digital Queue Management](https://nemo-q.com/blog/design-principles-digital-queue-management/) — Nemo-Q

### Anonymous User Identification
- [Anonymous credentials: rate-limiting bots without compromising privacy](https://blog.cloudflare.com/private-rate-limiting/) — Cloudflare (2025)
- [How to Secure Public APIs Without Authentication in 2025](https://cybersierra.co/blog/secure-public-apis-2025/) — CyberSierra
- [How WorkOS Radar does rate limiting with device fingerprinting](https://workos.com/blog/how-workos-radar-does-rate-limiting-with-device-fingerprinting) — WorkOS
- [Cloudflare Turnstile Server-Side Validation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/) — Cloudflare docs
- [Rate limiting best practices](https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/) — Cloudflare WAF docs
- [Everlasting Anonymous Rate-Limited Tokens](https://eprint.iacr.org/2025/1030.pdf) — ePrint/IACR (2025)

### Burst/Quota Patterns
- [ChatGPT Free Tier FAQ](https://help.openai.com/en/articles/9275245-chatgpt-free-tier-faq) — OpenAI
- [ChatGPT Message Limits in 2026](https://makesaasbetter.com/chatgpt-message-limit/) — MakeSaasBetter
- [Claude AI Message Limit: Free vs Pro](https://aionx.co/claude-ai-reviews/claude-ai-message-limit/) — AIonX
- [Understanding usage and length limits](https://support.claude.com/en/articles/11647753-understanding-usage-and-length-limits) — Anthropic
- [Perplexity Pricing and Plans](https://www.finout.io/blog/perplexity-pricing-in-2026) — Finout
- [OpenRouter Rate Limits](https://openrouter.ai/docs/api/reference/limits) — OpenRouter docs
- [OpenRouter Free Policy Adjustments](https://www.oreateai.com/blog/indepth-analysis-of-openrouters-free-policy-adjustments-daily-quota-changes-and-response-strategies/d450d1aa56b67882c0100e68510fac55) — Oreate AI

### Graceful Degradation
- [Building AI That Never Goes Down: The Graceful Degradation Playbook](https://medium.com/@mota_ai/building-ai-that-never-goes-down-the-graceful-degradation-playbook-d7428dc34ca3) — MOTA AI
- [How to Implement Graceful Degradation in LLM Frameworks](https://markaicode.com/implement-graceful-degradation-llm-frameworks/) — MarkAICode
- [Rate Limiting AI APIs with Async Middleware in FastAPI 2026](https://dasroot.net/posts/2026/02/rate-limiting-ai-apis-async-middleware-fastapi-redis/) — dasroot.net
- [Using Asyncio queues in the implementation of SSE](https://medium.com/@Rachita_B/lookout-for-these-cryptids-while-working-with-server-sent-events-43afabb3a868) — Medium

### FastAPI Implementation
- [Rate Limiting in FastAPI: Essential Protection for ML API Endpoints](https://fullstackdatascience.com/blogs/rate-limiting-in-fastapi-essential-protection-for-ml-api-endpoints-d5xsqw) — Full Stack Data Science
- [Async Streaming Responses in FastAPI](https://dasroot.net/posts/2026/03/async-streaming-responses-fastapi-comprehensive-guide/) — dasroot.net (Mar 2026)
- [Python Rate Limiting for APIs: Implementing Robust Throttling in FastAPI](https://www.techbuddies.io/2025/12/13/python-rate-limiting-for-apis-implementing-robust-throttling-in-fastapi/) — TechBuddies
