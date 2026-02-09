# Privacy Policy

**Last Updated:** 2026-02-09

## Overview

Ancient Nerds Map ("we", "our", or "the project") is committed to protecting your privacy. This document explains what data we collect, how we use it, and your rights regarding that data.

## Data We Collect

### 1. Archaeological Site Data

- **Source:** Aggregated from 100+ publicly available archaeological databases
- **Content:** Site names, locations (coordinates), descriptions, time periods, site types
- **Purpose:** Core functionality of the map application
- **Retention:** Permanent (public archaeological records)

### 2. Usage Analytics (Optional)

When enabled, we may collect:
- Page views and feature usage (anonymized)
- Geographic region (country-level only)
- Browser type and device category

**We do NOT collect:**
- Personal identifying information
- IP addresses (beyond rate limiting)
- Location data from your device
- Browsing history outside our application

### 3. AI Chat Feature (PIN-Protected)

If you use the AI research assistant:
- **Session data:** Temporary conversation history (deleted after session)
- **PIN validation:** Used only for access control, not stored
- **Queries:** Processed in real-time via the Anthropic Claude API, not permanently stored on our servers
- **Anthropic retention:** API request logs are retained by Anthropic for 7 days for abuse prevention, then automatically deleted
- **Training:** Your queries are **never used to train AI models** (Anthropic API policy)

### 4. Rate Limiting

- IP addresses are temporarily cached for rate limiting
- Automatically purged after the rate limit window expires
- Not linked to any personal information

## AI Pipeline & Third-Party Data Processing

Our automated news pipeline and AI research assistant process **publicly available archaeological data** (YouTube video content, site names, descriptions). No user personal data is sent to these services.

### Anthropic Claude API

- **Models used:** Claude Haiku 4.5 (summarization, verification, site identification, chat), Claude Sonnet 4.5 (post generation, escalation review)
- **Data sent:** YouTube video content, archaeological site names, summary text, news posts for verification, chat queries
- **Training:** API data is **never used for model training**. This is Anthropic's default policy for all API customers — no opt-out required.
- **Retention:** Inputs and outputs are retained for **7 days** then automatically deleted.
- **Data location:** Processed in the US, EU, Asia, and Australia. Stored in the **United States**.
- **Certifications:** SOC 2 Type II, ISO 27001:2022, ISO/IEC 42001:2023
- **GDPR:** Data Processing Addendum with Standard Contractual Clauses is automatically included in their Commercial Terms.
- **Features used:** Structured outputs (JSON schema), extended thinking, prompt caching (ephemeral) — all subject to the same 7-day retention policy.
- **More info:** [Anthropic Privacy Center](https://privacy.claude.com/)

### Voyage AI (Embeddings & Reranking)

- **Models used:** voyage-4 / voyage-4-large (embeddings), rerank-2.5-lite (reranking)
- **Data sent:** Archaeological site descriptions and news item text for semantic embedding; queries and document text for reranking
- **Training opt-out:** We have **opted out of data training** via the Voyage AI dashboard. This revokes their license to use our data for model improvement.
- **Retention:** With opt-out enabled, data is deleted **immediately after processing** (zero-day retention).
- **Parent company:** MongoDB (acquired Voyage AI in Feb 2025). MongoDB holds SOC 2 Type II and ISO 27001.
- **More info:** [Voyage AI Privacy Policy](https://www.voyageai.com/privacy), [Voyage AI Terms of Service](https://www.voyageai.com/tos)

### Qdrant (Vector Database)

- **Deployment:** **Self-hosted** on our infrastructure (Docker container, v1.13.2)
- **Telemetry:** Disabled (`QDRANT__TELEMETRY_DISABLED=true`)
- **Data sovereignty:** All vector data (embeddings, metadata) stays on our servers. No data is sent to Qdrant's servers.
- **More info:** [Qdrant Security Docs](https://qdrant.tech/documentation/guides/security/)

### Data Flow Summary

| Service | Data Sent | Used for Training? | Retention | Location |
|---------|-----------|-------------------|-----------|----------|
| Anthropic Claude API | Transcripts, site names, queries | **Never** | 7 days | US |
| Voyage AI | Site/news text for embedding | **No** (opted out) | Immediate deletion | US |
| Qdrant | Vector embeddings | N/A (self-hosted) | We control | Our VPS |

## How We Use Data

1. **Providing the service:** Displaying archaeological sites on the map
2. **News pipeline:** Extracting and summarizing archaeological news from public YouTube channels
3. **AI features:** Processing research queries in real-time
4. **Improving the application:** Aggregate usage patterns help us prioritize features
5. **Security:** Rate limiting prevents abuse

## Data Sharing

We do **NOT** sell, trade, or share your data with third parties except:

- **Anthropic:** AI processing of archaeological content and chat queries (see above)
- **Voyage AI:** Embedding archaeological text for semantic search (see above)
- **Mapbox:** Map tiles are loaded from Mapbox (see their [privacy policy](https://www.mapbox.com/legal/privacy))
- **Cloudflare:** We use Cloudflare for security and CDN services
- **Legal requirements:** If required by law

## Your Rights (GDPR Compliance)

If you are in the European Union, you have the right to:

1. **Access:** Request a copy of any personal data we hold about you
2. **Rectification:** Request correction of inaccurate data
3. **Erasure:** Request deletion of your data ("right to be forgotten")
4. **Portability:** Receive your data in a machine-readable format
5. **Object:** Object to processing of your data
6. **Withdraw consent:** Withdraw any previously given consent

To exercise these rights, contact us at: ancient.nerds@protonmail.com

**Note on AI sub-processors:** Anthropic provides a GDPR-compliant DPA with Standard Contractual Clauses, automatically included in their API terms. Voyage AI does not currently publish a separate DPA.

## Cookies

We use minimal cookies:

| Cookie | Purpose | Duration |
|--------|---------|----------|
| Session | Maintain AI chat session | Session only |
| Preferences | Remember UI settings | 1 year |

We do **NOT** use tracking cookies or third-party advertising cookies.

## Data Security

We implement appropriate security measures including:

- HTTPS encryption for all data in transit
- API keys stored as environment variables, never in client-side code
- Qdrant vector database self-hosted with telemetry disabled
- Cloudflare Turnstile for bot protection
- Rate limiting to prevent abuse
- No storage of sensitive personal data
- Regular security audits
- Open source codebase for full transparency

## Children's Privacy

Our service is not directed at children under 13. We do not knowingly collect data from children.

## Changes to This Policy

We may update this policy periodically. Significant changes will be announced via:
- GitHub release notes
- Notice on the application

## Contact

For privacy-related inquiries:

- **Email:** ancient.nerds@protonmail.com
- **GitHub Issues:** [Privacy-related issues](https://github.com/AncientNerds/AncientMap/issues)

## YouTube Creator Opt-Out

If you are a YouTube creator and would like your channel excluded from our news pipeline, please contact us at ancient.nerds@protonmail.com with the subject "Channel Opt-Out" and your channel name or URL. We will remove your channel within 7 days.

## Open Source Transparency

This project is open source. You can audit our data handling practices by reviewing the source code:

- API routes: `/api/routes/`
- Data pipeline: `/pipeline/`
- AI pipeline: `/pipeline/lyra/`
- RAG agent: `/api/services/lyra_agent.py`
- Embeddings: `/api/services/lyra_embeddings.py`
- Frontend: `/ancient-nerds-map/src/`
