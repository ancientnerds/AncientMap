# Privacy Policy

**Last Updated:** 2026-01-28

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
- **Queries:** Processed in real-time, not permanently stored

### 4. Rate Limiting

- IP addresses are temporarily cached for rate limiting
- Automatically purged after the rate limit window expires
- Not linked to any personal information

## How We Use Data

1. **Providing the service:** Displaying archaeological sites on the map
2. **Improving the application:** Aggregate usage patterns help us prioritize features
3. **Security:** Rate limiting prevents abuse
4. **AI features:** Processing research queries in real-time

## Data Sharing

We do **NOT** sell, trade, or share your data with third parties except:

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

To exercise these rights, contact us at: ancientnerds@proton.me

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
- Cloudflare Turnstile for bot protection
- Rate limiting to prevent abuse
- No storage of sensitive personal data
- Regular security audits

## Children's Privacy

Our service is not directed at children under 13. We do not knowingly collect data from children.

## Changes to This Policy

We may update this policy periodically. Significant changes will be announced via:
- GitHub release notes
- Notice on the application

## Contact

For privacy-related inquiries:

- **Email:** ancientnerds@proton.me
- **GitHub Issues:** [Privacy-related issues](https://github.com/AncientNerds/AncientMap/issues)

## Open Source Transparency

This project is open source. You can audit our data handling practices by reviewing the source code:

- API routes: `/api/routes/`
- Data pipeline: `/pipeline/`
- Frontend: `/ancient-nerds-map/src/`
