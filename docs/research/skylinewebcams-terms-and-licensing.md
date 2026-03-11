# SkylineWebcams: Terms of Service, Licensing, and Embedding Policy Research

**Date:** 2026-03-09
**Status:** Complete
**Researcher:** Claude (Opus 4.6)

---

## Executive Summary

SkylineWebcams (operated by VisioRay S.r.l., Italy) has **restrictive terms** that explicitly prohibit unauthorized reproduction, restreaming, proxying, or embedding of their live video feeds. Only **webcam hosts** (businesses/individuals who purchased and installed a SkylineWebcams camera kit) may embed the live video feed on their own websites. Third parties may only embed a **static photogram** that refreshes every 5 minutes, using an official embed code obtained via the "Embed" sharing button on the webcam page. There is **no public API**. Proxying or restreaming their HLS feeds is **not permitted** and their system actively uses technical measures (obfuscated URLs, rotating session tokens, copyright-violation stream redirects) to prevent it.

**Bottom line for AncientMap:** Do NOT proxy, restream, or scrape SkylineWebcams HLS feeds. The legally safe options are: (1) link to their webcam pages, or (2) use the official 5-minute photogram embed code if one is provided for the specific camera.

---

## 1. Terms of Service Analysis

**Source:** https://www.skylinewebcams.com/en/terms-of-use.html

### Ownership and Copyright

- All content on SkylineWebcams is owned by **VisioRay S.r.l.** (except user-contributed content)
- Copyright: 2011-2026 VisioRay S.r.l.
- "Any unauthorized use of the Content by the User...is prohibited"
- Users uploading content to the platform surrender ownership: "uploaded material will become property of VisioRay that may, therefore, use it for any legitimate purpose"

### What Is Prohibited

The Terms of Use explicitly forbid:

1. **Downloading, reproducing, or transmitting** content without prior written authorization by VisioRay
2. **Commercial use** without VisioRay agreement: "it is forbidden to use SkylineWebcams to solicit business of commercial nature or in connection to commercial activity, if not in the cases and at the conditions established by VisioRay"
3. **Creating derivative works** from time-lapse videos: "time-lapse videos cannot be saved, published nor used to create derivative works"
4. **Sharing** is restricted to cases where "sharing links are available" through official channels only

### What Is Permitted

- **Viewing** all SkylineWebcams content (but cannot modify, adapt, or reproduce it)
- **Sharing via official links** when sharing options are provided
- **Embedding the 5-minute photogram** (available to all users via the "Embed" button)
- **Embedding live video** (restricted to webcam hosts ONLY)

### Contact for Permissions

- Email: info@visioray.com
- Phone: +39 0961 34495 (business hours)
- For commercial arrangements or special embedding rights, direct contact with VisioRay is required

---

## 2. Official Embed and API Options

### Public API

**There is NO public API.** SkylineWebcams does not offer any documented REST API, SDK, or programmatic access for third-party developers.

### Official Embed Options

There are exactly two official embed mechanisms:

#### Option A: 5-Minute Photogram (Available to Everyone)

- Click "Embed" among the sharing options under the live video on any webcam page
- Provides an HTML embed code (iframe) from `embed.skylinewebcams.com`
- Shows a **static image** that auto-refreshes every 5 minutes
- This is NOT a live video stream -- it is a periodically-refreshed snapshot

#### Option B: Live Video Embed (Webcam Hosts ONLY)

- Only available to businesses/individuals who host a SkylineWebcams camera
- Provides a live HLS video embed for their own camera on their own website
- Requires purchasing the SkylineWebcams kit (EUR 269 one-time) or a cloud streaming subscription (from EUR 100/month)

### Commercial Partnerships

SkylineWebcams offers a commercial product for webcam hosts:
- **Hardware kit:** EUR 269 (one-time, no monthly fees, free streaming for life)
- Includes: HD webcam, streaming infrastructure, website widget, brand logo on feed
- The host gets embed capability plus a listing on skylinewebcams.com
- Their promo page claims 50+ million active users and 3,000+ customers

---

## 3. Attribution Requirements

Based on the Terms of Use and FAQ:

- **For photogram embeds:** The official embed code from the "Embed" button includes SkylineWebcams branding automatically
- **For linking:** When sharing links, the URL itself provides attribution to SkylineWebcams
- **For any authorized use:** VisioRay requires "prior written authorization" for any reproduction, which presumably would come with specific attribution terms
- **No Creative Commons or open license** -- all content is proprietary to VisioRay S.r.l.

The terms do NOT specify a particular attribution format for authorized uses -- they simply require that all use be authorized, and unauthorized use is prohibited.

---

## 4. Proxying / Restreaming HLS Feeds: Explicitly NOT Allowed

### Legal Position

Proxying or restreaming SkylineWebcams HLS feeds is **prohibited** under their Terms of Use:

- "it is forbidden to download, reproduce or transmit Content of the Website without prior written authorization by VisioRay"
- There is no exception for caching, proxying, or reformatting the stream

### Technical Anti-Restreaming Measures

SkylineWebcams has implemented active technical measures to prevent stream extraction:

1. **Obfuscated stream URLs:** The page source contains `livee.m3u8` (note the extra 'e') instead of `live.m3u8`. Requesting the intentionally misspelled endpoint redirects to a stream labeled `copyright_violation`

2. **Rotating session tokens:** The HLS stream URL format is:
   ```
   https://hd-auth.skylinewebcams.com/live.m3u8?a={session_token}
   ```
   The `?a=` parameter is a session token that:
   - Is embedded in page JavaScript and must be extracted per-session
   - Expires after approximately 1 minute
   - Requires cookies to refresh
   - Changes with each new page load

3. **Origin header requirement:** Stream requests require `Origin: https://www.skylinewebcams.com`

4. **Copyright trap stream:** Incorrectly formed requests are redirected to a "copyright_violation" stream -- evidence that VisioRay actively monitors and deters unauthorized access

### Community Reverse-Engineering (for reference, NOT recommended)

- The **yt-dlp** project (GitHub issue #7115) has an open/unmerged patch for extracting SkylineWebcams streams. The extractor must handle the `livee` -> `live` URL rewriting and token extraction.
- The **Home Assistant integration** (timmaurice/skyline-webcams) performs dynamic stream extraction for personal/local use. It includes a disclaimer: "This integration is not affiliated with or endorsed by SkylineWebcams."
- Neither project has received a public DMCA takedown as of this research date, but absence of enforcement is not the same as permission.

### Legal Risk Assessment

| Action | Risk Level | Notes |
|--------|-----------|-------|
| Link to webcam page | **None** | Fully permitted |
| Use official photogram embed | **None** | Officially supported |
| iframe their full page | **Low-Medium** | Not officially supported but loads their UI/ads |
| Extract HLS tokens server-side | **High** | Violates ToS, circumvents technical protection |
| Proxy/restream HLS feeds | **Very High** | Clear ToS violation, copyright infringement |
| Cache and serve their thumbnails | **Medium-High** | Reproduction without authorization |

---

## 5. Robots.txt and Page Source Analysis

### Robots.txt

**Source:** https://www.skylinewebcams.com/robots.txt

```
User-agent: AwarioRssBot
Disallow: /

User-agent: AwarioSmartBot
Disallow: /

User-agent: *
(no Disallow rules)
```

**Analysis:**
- Only two specific bots (AwarioRssBot, AwarioSmartBot) are explicitly blocked
- All other crawlers/bots have no restrictions
- There is **no `Disallow` for stream endpoints** or embed pages
- However, robots.txt compliance is about crawling/indexing, not about content reuse rights. The permissive robots.txt does NOT grant permission to reuse stream content.

### Page Source (Colosseum webcam example)

Key findings from the page source of a webcam page:

1. **Schema.org VideoObject markup:** Pages include structured data defining content as a live broadcast. No explicit embed permission metadata is present.

2. **Stream construction in JavaScript:**
   ```javascript
   'livee.m3u8?a=f0v5345q879pfcdagnifvphpa5'
   ```
   The stream URL is constructed client-side within a Clappr video player plugin.

3. **Copyright notice in footer:**
   ```
   Copyright 2011 - 2026 VisioRay S.r.l.
   ```

4. **No `X-Frame-Options` or CSP frame-ancestors restriction observed** -- meaning iframing the full page is not technically blocked (but is not officially endorsed either).

5. **No reference to `embed.skylinewebcams.com`** in standard webcam page source -- the embed subdomain appears to be used only for the official photogram embed widget.

---

## 6. Comparison with Other Webcam Providers

| Feature | SkylineWebcams | Windy Webcams | YouTube Live | NPS API |
|---------|---------------|---------------|-------------|---------|
| Public API | No | Yes (free tier) | Yes (quota) | Yes (free) |
| Embed allowed | Photogram only* | Yes (with attribution) | Yes (standard iframe) | N/A (static images) |
| Live video embed | Host-only | Via Windy player | YouTube player | No video |
| Archaeological coverage | Excellent (20+ sites) | Good (nearby search) | Variable | US parks only |
| Attribution required | Yes (built into embed) | Yes (credit Windy) | Yes (YouTube ToS) | Public domain |
| Restreaming allowed | No | No (API only) | No (YouTube ToS) | Yes (public domain) |

*Photogram = static image refreshing every 5 minutes

---

## 7. Recommendations for AncientMap

### DO (Safe and Permitted)

1. **Link to SkylineWebcams pages** from site detail panels. This is always safe.
   ```
   "Watch live: Colosseum webcam on SkylineWebcams"
   -> https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/colosseo.html
   ```

2. **Use the official photogram embed** where available. Visit each webcam page, click "Embed", and use the provided iframe code. This gives a 5-minute-refresh image in an official widget.

3. **Contact VisioRay directly** (info@visioray.com) to explore a partnership or licensing arrangement if live video embedding is desired. They may offer terms for a heritage/educational project.

### DO NOT (Prohibited or Risky)

1. **Do NOT proxy their HLS streams** through our backend. This violates their ToS, circumvents their technical protection measures, and could expose the project to legal action.

2. **Do NOT scrape session tokens** to construct stream URLs server-side. The `copyright_violation` redirect trap demonstrates they actively monitor for this.

3. **Do NOT hotlink their CDN thumbnails** (e.g., `cdn.skylinewebcams.com/live{id}.jpg`) without authorization. While these URLs exist, using them in our application constitutes unauthorized reproduction.

4. **Do NOT iframe their full webcam pages** as a primary integration strategy. While not technically blocked, it loads their entire UI, ads, and tracking in our context without authorization.

### RECOMMENDED ARCHITECTURE

For the AncientMap webcam feature, the recommended approach for SkylineWebcams content:

```
Database: site_webcams table
  source = 'skyline'
  external_id = camera slug
  player_url = full SkylineWebcams page URL (for "Watch Live" link)
  embed_url = official photogram embed URL if available

Frontend: Site detail panel
  - Show "Live Webcam" section
  - If embed_url exists: render official photogram iframe
  - Always show "Watch live on SkylineWebcams" link to player_url
  - Use Windy API thumbnails for preview images instead of Skyline CDN
```

This approach respects their terms while still providing value to users.

---

## Sources

- SkylineWebcams Terms of Use: https://www.skylinewebcams.com/en/terms-of-use.html
- SkylineWebcams FAQ: https://www.skylinewebcams.com/en/support/faq.html
- SkylineWebcams robots.txt: https://www.skylinewebcams.com/robots.txt
- SkylineWebcams Promo/Commercial: https://www.skylinewebcams.com/promo.html
- SkylineWebcams Live Streaming Service: https://www.skylinewebcams.com/services/live-streaming.html
- SkylineWebcams Privacy Policy: https://www.skylinewebcams.com/en/privacy-policy.html
- yt-dlp Issue #7115 (stream extraction): https://github.com/yt-dlp/yt-dlp/issues/7115
- youtube-dl Issue #12221 (site support request): https://github.com/ytdl-org/youtube-dl/issues/12221
- Home Assistant Integration: https://github.com/timmaurice/skyline-webcams
- Colosseum webcam page source: https://www.skylinewebcams.com/en/webcam/italia/lazio/roma/roma-colosseo.html
- Embed subdomain: http://embed.skylinewebcams.com/
