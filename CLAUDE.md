# Claude Code Instructions for AncientMap

## Code Quality Standards

### NO FALLBACK CODE
**Do NOT add fallback logic, defensive coding, or "graceful degradation" when fixing bugs.**

When something doesn't work:
1. Find the ACTUAL root cause
2. Fix it properly or mark the connector as `available = False` with a clear reason
3. If an API is dead/changed/protected - say so directly, don't wrap it in try/catch that returns empty

Bad:
```python
# Try multiple endpoints and fallback
for endpoint in ["/api/v1", "/api/v2", "/old-api"]:
    try:
        response = await self.rest.get(endpoint)
        if response:
            return self._parse_response(response)
    except:
        continue
return []  # Silent failure
```

Good:
```python
# This endpoint works - verified on 2024-01-15
response = await self.rest.get("/api/v2/search")
return self._parse_response(response)
```

Or if it doesn't work:
```python
available = False
unavailable_reason = "API deprecated in 2021, no replacement available"
```

### Testing APIs
Before implementing a connector, actually test the API with curl to verify:
- The endpoint exists
- The response format matches what we expect
- There's no bot protection blocking requests

### Connector Status
If a connector cannot work due to:
- Bot protection (Cloudflare, Anubis)
- Deprecated/shutdown API
- Requires authentication we don't have

Mark it as `available = False` with `unavailable_reason` explaining why. Don't write fake code that silently returns empty results.
