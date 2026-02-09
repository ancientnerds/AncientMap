# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please
report it responsibly.

### How to Report

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, please send a detailed report to:

**Use GitHub's [Private Vulnerability Reporting](../../security/advisories/new) feature.**

This allows you to report security issues privately without exposing them publicly.

### What to Include

Please include the following in your report:

1. **Description** of the vulnerability
2. **Steps to reproduce** the issue
3. **Potential impact** of the vulnerability
4. **Suggested fix** (if you have one)
5. **Your contact information** for follow-up questions

### What to Expect

- **Acknowledgment**: We will acknowledge receipt within 48 hours
- **Assessment**: We will assess the vulnerability within 7 days
- **Updates**: We will keep you informed of our progress
- **Resolution**: We aim to resolve critical issues within 30 days
- **Credit**: With your permission, we will credit you in our release notes

### Scope

The following are in scope for security reports:

- Authentication and authorization bypasses
- SQL injection, XSS, CSRF vulnerabilities
- Sensitive data exposure
- Remote code execution
- Server-side request forgery (SSRF)
- Insecure direct object references

### Out of Scope

- Denial of service attacks
- Social engineering attacks
- Physical attacks
- Issues in dependencies (report these to the dependency maintainers)
- Issues requiring unlikely user interaction

## Security Best Practices for Contributors

### Credentials

- **NEVER** commit API keys, passwords, or secrets to the repository
- Use environment variables for all sensitive configuration
- Use `.env` files locally (they are gitignored)
- Rotate any credentials that may have been exposed

### Code

- Use parameterized queries for all database operations
- Validate and sanitize all user input
- Use secure session management
- Implement proper CORS policies
- Keep dependencies updated

### Data

- Do not store sensitive user data unnecessarily
- Implement proper access controls
- Log security-relevant events
- Follow data protection regulations (GDPR, etc.)

## Security Features

This project implements multiple layers of security, hardened through three dedicated audit rounds.

### Authentication & Access Control

- **Admin PIN**: Required for site editing and administrative actions. Must be set via `ADMIN_PIN` environment variable (no default). Compared using `secrets.compare_digest()` (timing-safe)
- **Lyra Admin Key**: Bearer token authentication for the AI chat admin endpoint and radar cache-bust. Required via `LYRA_ADMIN_KEY` env var; endpoints return 503 if unconfigured
- **Cloudflare Turnstile**: Bot protection on all public-facing sensitive endpoints (chat, contributions, admin PIN verification)

### Network & Transport

- **X-Forwarded-For handling**: Only trusted when `TRUSTED_PROXY=1` env var is set (for deployments behind nginx/Caddy). Uses the rightmost header entry (proxy-appended) to prevent client spoofing
- **CORS**: Cross-origin requests restricted to configured allowed origins
- **HTTPS**: All production traffic encrypted via Cloudflare

### Input Validation & XSS Prevention

- **Pydantic models**: All API request bodies validated with strict types and constraints
- **Payload limits**: Lyra chat images capped at 5, conversation history at 50 messages, context IDs at 100 characters
- **Sites endpoint**: Query limit capped at 50,000 rows
- **OG share page**: Site IDs validated as UUID format; all URLs HTML-escaped before insertion into meta tags and JavaScript
- **SQL injection prevention**: Parameterized queries via SQLAlchemy throughout

### Rate Limiting & Resource Protection

- **Per-IP rate limiting**: 20 requests/hour on public Lyra chat (configurable via `LYRA_RATE_LIMIT`)
- **SSE stream timeout**: Maximum 5-minute connection duration per chat stream
- **In-memory rate bucket cleanup**: Expired entries pruned on each request

### AI Pipeline Security

- **Prompt injection guards**: All 11 LLM prompt files include explicit instructions to treat external content (YouTube transcripts, metadata, Wikidata results) as data only, not as instructions to follow
- **Tool error sanitization**: Internal exceptions from Lyra agent tool calls are replaced with generic messages before being sent to the LLM (prevents leaking stack traces, file paths, or database details to users)
- **Shared client pooling**: Single cached `anthropic.Anthropic()` instance reused across all pipeline modules (connection pooling, prompt cache hits)

### Infrastructure

- **Environment variables**: All secrets (API keys, database passwords, admin PINs) loaded from environment; never hardcoded or committed
- **Docker isolation**: API runs in isolated container; database persists in Docker volume
- **CI security scanning**: Automated Bandit (Python) and npm audit checks in GitHub Actions

## Dependency Security

We regularly audit our dependencies for known vulnerabilities:

```bash
# Python
pip-audit

# JavaScript
npm audit
```

If you notice outdated dependencies with known vulnerabilities, please open an
issue or submit a PR to update them.

## Acknowledgments

We thank the following individuals for responsibly disclosing security issues:

*No reports yet - be the first!*
