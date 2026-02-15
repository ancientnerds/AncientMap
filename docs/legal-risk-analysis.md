# Legal & Licensing Risk Analysis: AncientMap Lyra Pipeline

**Prepared:** 2026-02-09
**Scope:** YouTube transcript extraction, AI summarization, Wikipedia/Wikidata enrichment, Voyage AI embeddings, and publication of AI-generated archaeological news content.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [YouTube Terms of Service & Transcript Scraping](#2-youtube-terms-of-service--transcript-scraping)
3. [AI-Generated Content Copyright](#3-ai-generated-content-copyright)
4. [MiniMax M2.5 Commercial Use & Data Sovereignty](#4-minimax-m25-commercial-use--data-sovereignty)
5. [Derivative Works & Fair Use](#5-derivative-works--fair-use)
6. [Wikipedia & Wikidata Licensing](#6-wikipedia--wikidata-licensing)
7. [YouTube Creator Rights](#7-youtube-creator-rights)
8. [EU AI Act Disclosure Requirements](#8-eu-ai-act-disclosure-requirements)
9. [Voyage AI Licensing Concerns](#9-voyage-ai-licensing-concerns)
10. [Risk Mitigation Recommendations](#10-risk-mitigation-recommendations)
11. [Risk Matrix Summary](#11-risk-matrix-summary)

---

## 1. Executive Summary

This analysis identifies **ten distinct legal risk areas** for the AncientMap Lyra pipeline. The overall risk profile is **moderate**, with two areas of elevated concern: YouTube ToS compliance and the emerging case law around AI-generated summaries of copyrighted content. Several strong mitigating factors exist, including the project's educational/non-commercial purpose, the transformative nature of archaeological site extraction from video transcripts, and the niche subject matter that minimizes market substitution for original creators.

**Highest risks:**
- YouTube ToS violation through automated transcript extraction (contractual, not criminal)
- AI summary copyright claims under the evolving *Advance Local Media v. Cohere* line of cases

**Lowest risks:**
- Wikidata (CC0, no restrictions)
- MiniMax API commercial use (permitted, but weaker protections than Anthropic)
- Voyage AI embedding (technical processing, minimal legal surface)

---

## 2. YouTube Terms of Service & Transcript Scraping

### 2.1 What the ToS Says

YouTube's general Terms of Service contain an explicit prohibition on automated access:

> "You agree not to use or launch any automated system, including without limitation, 'robots,' 'spiders,' or 'offline readers,' that accesses the Service in a manner that sends more request messages to the YouTube servers in a given period of time than a human can reasonably produce."

The YouTube API Services Terms of Service (Section 3.1) further restrict access to only the means "described in the Agreement" and the YouTube API Developer Policies state:

> "You and your API clients must not scrape YouTube Applications or Google Applications, or obtain scraped YouTube data or content."

### 2.2 How the Lyra Pipeline Accesses YouTube

Based on review of `pipeline/lyra/transcript_fetcher.py`:

1. **RSS Feed access** (lines 31-104): Fetches YouTube's public Atom RSS feeds for channel video listings. This uses a standard HTTP GET with browser-like User-Agent headers.

2. **youtube-transcript-api** (lines 11, 107-147): Uses the third-party `youtube-transcript-api` Python library to fetch auto-generated captions. This library does NOT use the official YouTube Data API -- it scrapes YouTube's internal caption endpoints directly.

3. **yt-dlp metadata extraction** (lines 276-309): Uses `yt-dlp` to fetch video metadata (descriptions, tags) via `--dump-json --no-download`.

### 2.3 Legal Analysis

**The youtube-transcript-api library technically violates YouTube's ToS.** It bypasses the official API and directly accesses YouTube's internal caption delivery system. This is precisely the kind of automated access YouTube's ToS prohibits.

**However, the legal risk is nuanced:**

- **CFAA (Computer Fraud and Abuse Act):** After *Van Buren v. United States* (2021) and the Ninth Circuit's ruling in *hiQ v. LinkedIn*, accessing publicly available data on public websites is unlikely to violate the CFAA. The Supreme Court narrowed CFAA's "without authorization" to a "gates-up-or-down" inquiry -- if no technical barrier prevents access, there is no CFAA violation. YouTube transcripts are publicly accessible to any viewer.

- **Breach of Contract:** The more realistic risk is a breach of contract claim under YouTube's ToS. In the *hiQ v. LinkedIn* final settlement (2022), the court found that website user agreement provisions prohibiting scraping ARE enforceable as breach of contract claims, even though they don't create CFAA liability.

- **Practical enforcement:** YouTube's primary enforcement mechanism is technical (IP blocking, rate limiting), not legal action against small-scale users. The Lyra pipeline processes a limited number of archaeology-focused channels, not mass scraping.

- **Note on the official YouTube API:** The official YouTube Data API does NOT provide access to video transcripts/captions for videos you don't own. This gap is precisely why libraries like youtube-transcript-api exist.

### 2.4 Risk Rating: MODERATE-HIGH

| Factor | Assessment |
|--------|------------|
| ToS Violation | Yes -- automated transcript access violates YouTube ToS |
| Criminal liability (CFAA) | Very low -- public data, no technical barriers |
| Civil liability (breach of contract) | Low-moderate -- enforceable in theory, but YouTube would need to pursue action |
| Practical enforcement risk | Low -- small-scale, niche educational use |
| IP blocking risk | Moderate -- mitigated by proxy configuration in codebase |

---

## 3. AI-Generated Content Copyright

### 3.1 Current U.S. Legal Status (as of early 2026)

The U.S. Copyright Office published its definitive "Part 2" report on January 29, 2025, confirming:

- **Purely AI-generated content cannot be copyrighted.** The Copyright Act requires human authorship, as affirmed by the D.C. Circuit in *Thaler v. Perlmutter* (March 2025).

- **AI-assisted content CAN be copyrighted** where "a human author has determined sufficient expressive elements." This includes situations where a human makes creative arrangements, selections, or modifications of AI output.

- **Mere provision of prompts is NOT sufficient** to establish human authorship.

### 3.2 Implications for Lyra Pipeline

The Lyra pipeline generates several types of AI output:

| Output | File | Copyright Status |
|--------|------|-----------------|
| Video summaries (structured JSON) | `summarizer.py` | Likely NOT copyrightable -- automated extraction with minimal human creative input |
| News feed posts | `tweet_generator.py` | Possibly copyrightable if human editors curate/modify; otherwise likely not |
| Weekly articles | `article_generator.py` | Stronger copyright claim -- multi-step human-directed process with editorial choices |
| Site identifications | `site_identifier.py` | Factual data -- not copyrightable regardless of method |

### 3.3 Practical Impact

**The project cannot claim strong copyright protection over its AI-generated summaries and posts.** This means:
- Competitors could freely copy the generated news feed content
- The project cannot use copyright to prevent redistribution of its AI-generated text
- However, the aggregation, curation, and presentation may qualify for compilation copyright

### 3.4 Risk Rating: LOW

This is more of a **business risk** (inability to protect own content) than a **legal liability risk**. Nobody will sue the project for publishing uncopyrightable content.

---

## 4. MiniMax M2.5 Commercial Use & Data Sovereignty

> **Migration note (Feb 2026):** The Lyra pipeline migrated from Anthropic Claude (Haiku/Sonnet) to MiniMax M2.5 via the Anthropic-compatible API at `api.minimax.io`. The Anthropic SDK is still used as the client library. This section replaces the previous Anthropic analysis; see CHANGELOG.md for historical context.

### 4.1 Company Background

| Detail | Information |
|--------|-------------|
| **Company** | MiniMax (founded Dec 2021, Shanghai, China) |
| **International entity** | Nanonoble Pte. Ltd. (Singapore, est. 2024) |
| **IPO** | Hong Kong Stock Exchange, Jan 2026, raised HK$4.8B (~$620M) |
| **Key investors** | Alibaba, Tencent, MiHoYo, Hillhouse, Abu Dhabi Investment Authority |
| **US Entity List** | Added in 2025 as part of export controls targeting Chinese AI companies |
| **Active litigation** | Disney, Warner Bros., Universal, and 8 other studios sued MiniMax (Sep 2025) for "willful and brazen" copyright infringement via Hailuo AI video generator |

### 4.2 Terms of Service Analysis

**Output Ownership:** "As between you and us, and to the extent permitted by applicable laws, you retain your ownership rights in Client input and generated content." Commercial use of outputs is permitted.

**Data Usage for Training (Critical):** MiniMax's ToS state:

> "We may use the input and generated content to provide, maintain, develop, and improve our Services."

> "Our use or disclosure of Confidential Information for the purpose of improving algorithms or enhancing services does not constitute a breach of confidentiality obligations."

**Translation:** MiniMax explicitly reserves the right to use API inputs and outputs to train/improve their models, and has structured the ToS so this cannot be challenged as a confidentiality breach. Third-party reviews suggest a zero-retention opt-out may exist, but it is **not described in the published legal terms**.

**Deep synthesis marking:** The ToS requires users to "place a prominent mark in reasonable positions to inform the public of the use of deep synthesis technology" — a Chinese regulatory requirement included in the international ToS.

**Governing law:** Singapore law, with mandatory arbitration at the Singapore International Arbitration Centre (SIAC).

### 4.3 Indemnification (Comparison with Anthropic)

MiniMax does **not** offer copyright indemnification comparable to Anthropic's Copyright Shield:

| Protection | Anthropic (previous) | MiniMax (current) |
|------------|---------------------|-------------------|
| Output ownership | Customer owns outputs | Customer owns outputs |
| Training on API data | Never (default policy) | **ToS allows it** |
| Copyright Shield | Yes — covers authorized use | **No** |
| IP indemnification | Yes — defends against infringement claims | Narrow — only for MiniMax's own service IP |
| Data retention | 7 days, then auto-deleted | **Not disclosed** |
| DPA available | Yes (auto-included) | **Not published** |
| Certifications (public) | SOC 2 Type II, ISO 27001 | Claimed but **NDA-only** |

**MiniMax's indemnification is asymmetric:**
- **You indemnify MiniMax** against all claims related to your content, applications, or service use
- **MiniMax's limited indemnity** covers only claims that their service itself infringes IP — not claims about outputs generated from your data
- **Excluded from even this narrow indemnity:** claims involving your data, combining the service with third-party products, or continued use after receiving a cease notice

### 4.4 Data Sovereignty Concerns

**Data location:** MiniMax states API data is processed on servers in the United States. The operating entity is a Singapore company (Nanonoble Pte. Ltd.). However:

1. **Chinese parent company:** MiniMax is headquartered in Shanghai. The privacy policy does not explicitly guarantee data is not shared with Chinese affiliates.

2. **China's National Intelligence Law (2017):** Article 7 obliges Chinese companies and citizens to "support, assist, and cooperate with national intelligence efforts." While the scope is debated by legal scholars, this law could theoretically compel MiniMax to provide access to data.

3. **US Entity List:** MiniMax was added to the U.S. Department of Commerce Entity List in 2025. While this primarily restricts technology exports TO MiniMax, it signals US government concern about the company's ties to China's military-industrial ecosystem.

4. **Corporate structure opacity:** Nanonoble Pte. Ltd. was established in 2024 specifically for international operations. The degree of operational independence from the Shanghai parent is unclear.

### 4.5 Risk Analysis for Lyra Pipeline

The migration from Anthropic to MiniMax introduces several new risk vectors:

- **Training risk:** YouTube transcripts (copyrighted third-party content) may be used by MiniMax to train future models. This creates potential downstream copyright liability that Anthropic's "never train on API data" policy previously eliminated.

- **No copyright shield:** If a YouTube creator or rights holder files a copyright claim related to AI-generated summaries, MiniMax provides no defensive coverage. Under Anthropic, at least claims about the AI output itself (not customer-provided data) were covered.

- **Data sovereignty:** The involvement of a Chinese parent company may concern users, particularly those in government, academic, or defense-adjacent archaeology. The content processed (YouTube transcripts about archaeology) is low-sensitivity, but the principle matters for transparency.

- **Active copyright litigation:** Disney and 10 other major studios are currently suing MiniMax for copyright infringement. While this involves a different product (Hailuo AI video generator, not the M2.5 API), it reflects on the company's copyright compliance posture.

### 4.6 Risk Rating: MODERATE

The migration from Anthropic to MiniMax significantly weakens the project's legal protections:
- **Was LOW** under Anthropic (explicit no-training policy, copyright indemnification, GDPR DPA, public certifications)
- **Now MODERATE** under MiniMax (ToS allow training, no copyright shield, Chinese parent company, Entity List designation, unverified certifications)

The elevated risk is partially mitigated by: the low-sensitivity nature of archaeological content, the educational/non-commercial purpose of the project, and the fact that the content being processed (YouTube transcripts about ancient sites) is unlikely to be a target for data sovereignty concerns.

---

## 5. Derivative Works & Fair Use

### 5.1 Key Case Law (2025)

Three landmark cases established the emerging framework:

**Advance Local Media v. Cohere (November 2025):**
- Court ruled that AI-generated "substitutive summaries" -- even non-verbatim -- MAY infringe copyright when they replicate the original work's expressive structure and journalistic storytelling choices.
- Court found 75 examples of infringement including verbatim copying and close paraphrasing.
- Key quote: "It is not possible to determine infringement through a simple word count." What matters is whether summaries mirror the original's narrative structure, tone, and organizational framework.
- **This is the most directly relevant case to the Lyra pipeline.**

**New York Times v. Microsoft/OpenAI (March-April 2025):**
- Court dismissed claims that Copilot's "bullet-point abridgments" infringed articles, finding that "reorganized and skeletal summaries weren't substantially similar."
- Copyright infringement claims on other grounds survived.
- Case still in litigation as of February 2026.

**Bartz v. Anthropic / Kadrey v. Meta (June 2025):**
- Both courts found AI training on copyrighted works to be "quintessentially transformative" fair use (when lawfully acquired).
- These cases address training, not output-level infringement -- less directly applicable to the Lyra pipeline.

### 5.2 Fair Use Analysis for Lyra Pipeline

The four-factor fair use test applied to the project:

**Factor 1: Purpose and Character of Use**
- FAVORABLE: Educational/informational purpose (archaeological research platform)
- FAVORABLE: Highly transformative -- extracts specific archaeological site references and factual findings from entertainment/educational videos, reorganizes into structured data
- SOMEWHAT UNFAVORABLE: Published on a public website, though non-commercial

**Factor 2: Nature of the Copyrighted Work**
- FAVORABLE: YouTube videos are published, publicly available works
- NEUTRAL: Mix of factual (archaeological facts) and creative (presentation, narration) elements

**Factor 3: Amount and Substantiality of the Portion Used**
- FAVORABLE: The pipeline extracts only key topics and facts, not the entire creative expression
- FAVORABLE: Output is structured JSON data and brief bullet points, not narrative reproduction
- The summarizer (`summarizer.py`) extracts "key_topics" with "facts" arrays -- factual extraction rather than narrative reproduction

**Factor 4: Effect on the Market for the Original**
- STRONGLY FAVORABLE: Archaeological site data extracted from videos does not compete with or substitute for watching the original videos
- FAVORABLE: The news posts and summaries serve a fundamentally different purpose (mapping sites, not entertainment)
- FAVORABLE: The pipeline actually drives traffic TO the videos by attributing them as sources

### 5.3 Critical Distinction from Cohere

The Lyra pipeline differs from the *Advance Local Media v. Cohere* scenario in several important ways:

1. **Not summarizing news articles** -- it extracts factual archaeological data from video content, a different medium and purpose
2. **Extracting facts, not narrative structure** -- the output is structured data (site names, coordinates, periods), not paraphrased narrative
3. **Different market** -- no one watches archaeology YouTube videos as a substitute for reading archaeological site databases
4. **Attribution provided** -- the pipeline includes video attribution ("via Channel Name") in generated posts

### 5.4 Risk Rating: MODERATE

The fair use argument is reasonably strong, but the *Advance Local Media v. Cohere* precedent creates uncertainty. The key protective factor is that the pipeline extracts factual data (site names, dates, locations) rather than reproducing creative expression.

---

## 6. Wikipedia & Wikidata Licensing

### 6.1 Wikidata: CC0 (Public Domain)

All data in Wikidata is published under Creative Commons CC0 (public domain dedication). This means:

- Unrestricted commercial use without attribution
- No ShareAlike requirements
- No restrictions on derivative works
- Applies to all structured data: coordinates, entity IDs, property values

The Lyra pipeline uses Wikidata for site enrichment (`site_identifier.py`, lines 444-678) -- this is completely safe.

**Risk Rating: NONE**

### 6.2 Wikipedia: CC BY-SA 3.0

Wikipedia article text is licensed under CC BY-SA 3.0. The Lyra pipeline fetches Wikipedia content via two mechanisms:

1. **REST API summary** (`_fetch_wikipedia_summary`, line 681): Fetches article extracts/descriptions
2. **Mobile sections lead** (`_fetch_wikipedia_lead`, line 708): Fetches lead section text for metadata extraction

The fetched text is used in two ways:
- **Stored as site descriptions** in `contribution.description` (line 1106)
- **Processed by the LLM** to extract period and site_type metadata (line 1118)

### 6.3 CC BY-SA Compliance Analysis

**Attribution (BY) requirement:**
- The project's DisclaimerModal already lists Wikipedia under "CC BY-SA 3.0" in the Data Sources section
- The `site_identifier.py` stores `wikipedia_url` on enriched contributions, providing per-site attribution
- **Status: Largely compliant** -- the project credits Wikipedia and links back

**ShareAlike (SA) requirement:**
- The key question: Does AI processing of CC BY-SA content create a "derivative work" that must also be CC BY-SA?
- Creative Commons' own guidance (May 2025) states that "the application of copyright law to AI training is complex" and notes that CC license conditions have "limited application to machine reuse"
- The Open Future Foundation notes that key CC concepts like "adapted material" are "largely absent in AI training workflows"
- The project uses Wikipedia text as input to AI processing that extracts factual metadata (period, site_type) -- facts cannot be copyrighted
- Storing Wikipedia descriptions verbatim on site records IS a derivative work and should comply with CC BY-SA

**Practical compliance:**
- Site descriptions sourced from Wikipedia should be attributed
- The project already stores `wikipedia_url` per site
- The project's own content license is CC BY-SA 4.0, which is compatible with CC BY-SA 3.0 (forward-compatible)

### 6.4 Wikimedia Foundation's 2025 Position

In late 2025, the Wikimedia Foundation urged AI companies to use the paid Wikimedia Enterprise API rather than scraping. However, the REST API endpoints used by the Lyra pipeline are publicly available and intended for programmatic access -- they are not scraping.

### 6.5 Risk Rating: LOW

The main requirements are attribution (already present) and ShareAlike for stored descriptions (covered by the project's CC BY-SA 4.0 license). AI-extracted factual metadata (period, type) from Wikipedia text does not create a copyrightable derivative work.

---

## 7. YouTube Creator Rights

### 7.1 Copyright Ownership

YouTube creators own the copyright to their videos, including the spoken words. A transcript of spoken words is generally considered a derivative work of the video.

### 7.2 Could Creators Sue?

**Theoretical claims:**
- **Copyright infringement:** A creator could claim that summarizing their video without permission creates an unauthorized derivative work
- **Unfair competition:** A creator could argue the summaries compete with their content or reduce viewership
- **Breach of YouTube ToS (third-party beneficiary):** Creators could potentially argue they are third-party beneficiaries of YouTube's ToS prohibition on scraping

**Practical likelihood:**
- **Very low for this project.** The archaeology YouTube community is niche, and the pipeline effectively serves as free promotion by driving viewers back to videos.
- The pipeline includes attribution to channels and video titles.
- The project extracts archaeological facts (not copyrightable) rather than creative expression.
- YouTube's 2025 Partner Program update targets "inauthentic content" like AI commentary that doesn't add value -- but that applies to YouTube creators, not third-party websites.

**The strongest protection is the nature of the content:**
- Archaeological facts (site names, dates, locations, findings) are not copyrightable
- The creative expression of how those facts are presented in a video IS copyrightable
- The pipeline specifically extracts facts, not creative expression

### 7.3 Risk Rating: LOW-MODERATE

Low probability of a claim, but non-zero. The main vulnerability would be if a summary reproduced distinctive creative expression from a video rather than just factual content.

---

## 8. EU AI Act Disclosure Requirements

### 8.1 Timeline

- **February 2, 2025:** Prohibited AI practices and AI literacy obligations entered force
- **August 2, 2025:** GPAI model governance rules became applicable
- **August 2, 2026:** Full transparency rules including Article 50 enter force
- **December 2025:** First draft of the Code of Practice on AI-generated content transparency published
- **June 2026:** Final Code of Practice anticipated

### 8.2 Article 50 Requirements

When fully applicable (August 2026), Article 50 requires:

1. **AI-generated content must be identifiable** as AI-generated or AI-manipulated
2. **AI-generated text published to inform the public on matters of public interest** must be clearly labeled
3. The Code of Practice promotes a "multilayered approach" combining visible disclosures with machine-readable techniques (metadata, watermarking)

### 8.3 Applicability to Lyra Pipeline

**The Lyra pipeline publishes AI-generated text (news summaries, posts) on a public website. If the content addresses "matters of public interest" (archaeological findings could qualify), Article 50 disclosure would be required for EU users starting August 2026.**

Current status of the project:
- The DisclaimerModal mentions AI processing but does NOT explicitly label individual news items as AI-generated
- The PRIVACY.md mentions MiniMax AI usage but focuses on data processing, not content labeling

### 8.4 Risk Rating: LOW (currently), MODERATE (from August 2026)

The project should plan for EU AI Act compliance before August 2026. The required changes are straightforward: label AI-generated content clearly on each news item/post.

---

## 9. Voyage AI Licensing Concerns

### 9.1 Terms of Service Analysis

Voyage AI's ToS contains several notable provisions:

**Default data training license:** By default, customers grant Voyage AI a "worldwide, irrevocable, perpetual, royalty-free license" to use customer content for "training, improving, and otherwise further developing the Service."

**Opt-out available:** The PRIVACY.md confirms the project has opted out of data training via the Voyage AI dashboard, which provides zero-day retention.

**Commercial use of website vs API:** The website ToS states content is for "personal, non-commercial use only" -- but this appears to apply to the website content itself, not the API service. The paid API is a commercial product intended for business use.

**Indemnification is one-way:** Customers must indemnify Voyage AI, but Voyage AI provides no reverse indemnification for copyright claims related to embeddings.

### 9.2 Third-Party Content Concerns

The project sends third-party content (YouTube-derived summaries, Wikipedia descriptions) through Voyage AI for embedding. Key considerations:

- **Embeddings are mathematical vector representations**, not copies of the original text. An embedding cannot be reverse-engineered to recover the source text.
- **The legal surface is minimal** -- embedding is a technical transformation that creates a non-human-readable numerical representation.
- **With opt-out enabled**, Voyage AI deletes data immediately after processing, minimizing exposure.

### 9.3 MongoDB Acquisition

Voyage AI was acquired by MongoDB in February 2025. MongoDB holds SOC 2 Type II and ISO 27001 certifications, providing additional operational security assurances.

### 9.4 Risk Rating: VERY LOW

Embedding text into vectors does not create copies or derivative works in any legally meaningful sense. The main concern (training data usage) is mitigated by the opt-out.

---

## 10. Risk Mitigation Recommendations

### 10.1 Immediate Actions (High Priority)

**A. Add AI-generated content labels to news items.**
Every news feed post and article should display a clear label such as "AI-generated summary" or "Generated by AI from video transcript." This prepares for EU AI Act Article 50 (August 2026) and demonstrates good faith.

**B. Add explicit YouTube attribution with video links.**
Every news item derived from a YouTube video should include:
- Channel name (already present via `_format_attribution` in `tweet_generator.py`)
- Direct link to the original video with timestamp
- Language like "Based on content from [Channel Name]"

**C. Ensure summaries extract facts, not creative expression.**
Review the summarization prompts (`prompts/summary.txt`, `prompts/tweet_template.txt`) to ensure they instruct the LLM to extract factual archaeological information, not to paraphrase or reproduce the creator's narrative style. Add explicit instructions like: "Extract only verifiable archaeological facts. Do not reproduce the speaker's distinctive phrasing, narrative structure, or creative expression."

**D. Add a robots.txt respect mechanism.**
While the project uses RSS feeds (which are intended for machine consumption), the transcript and metadata fetching should respect any rate limits and include appropriate delays.

### 10.2 Medium Priority

**E. Wikipedia attribution per-site.**
When displaying site descriptions sourced from Wikipedia, include a visible attribution like "Description from Wikipedia (CC BY-SA 3.0)" with a link to the source article. The `wikipedia_url` is already stored -- it just needs to be displayed.

**F. Creator opt-out mechanism.**
Implement a simple way for YouTube creators to request their channels be excluded from the pipeline. A contact email or form would suffice. This significantly reduces the risk of adversarial claims.

**G. Review and document the commercial vs non-commercial nature.**
If the project is truly non-commercial (educational, no ads, no paid subscriptions), document this clearly. Non-commercial purpose strengthens fair use claims and may exempt from some licensing requirements.

### 10.3 Lower Priority (Best Practices)

**H. Monitor case law.**
The *Advance Local Media v. Cohere* case is still in litigation and could produce binding precedent on AI summaries. The *NYT v. OpenAI* case may also produce relevant fair use rulings.

**I. Consider official YouTube API for metadata.**
While the official API doesn't provide transcripts, using it for video metadata (titles, descriptions, thumbnails) would be ToS-compliant and reduce the overall scraping footprint.

**J. Maintain the PRIVACY.md and DisclaimerModal.**
Both are already comprehensive. Keep them updated as services and legal requirements evolve.

**K. Consider Wikimedia Enterprise API.**
If the project scales significantly, using the paid Wikimedia Enterprise API would demonstrate good faith toward the Wikimedia Foundation's data access preferences.

---

## 11. Risk Matrix Summary

| Risk Area | Severity | Probability | Overall Risk | Mitigating Factors |
|-----------|----------|-------------|--------------|-------------------|
| YouTube ToS violation (transcript scraping) | Medium | High | **MODERATE-HIGH** | Small scale, educational use, public data, no CFAA liability |
| AI summary copyright (Cohere precedent) | High | Low | **MODERATE** | Factual extraction, different medium, attribution, no market substitution |
| AI-generated content copyrightability | Low | N/A | **LOW** | Business risk only (cannot protect own content) |
| MiniMax commercial use & data sovereignty | Medium | Medium | **MODERATE** | ToS allow training on data, Chinese parent co., no copyright shield |
| YouTube creator lawsuits | Medium | Very Low | **LOW-MODERATE** | Educational purpose, attribution, drives traffic to originals |
| Wikipedia CC BY-SA compliance | Low | Low | **LOW** | Attribution present, compatible license, factual extraction |
| Wikidata licensing | None | None | **NONE** | CC0 public domain |
| EU AI Act (from Aug 2026) | Medium | High | **MODERATE** | Clear compliance path, 6 months to prepare |
| Voyage AI data concerns | Low | Very Low | **VERY LOW** | Opt-out enabled, embeddings are not copies |
| MiniMax indemnification gaps | Medium | Medium | **MODERATE** | No copyright shield; all IP liability on customer |

### Overall Project Risk: MODERATE

The project's strongest legal protections are:
1. Educational/non-commercial purpose
2. Extraction of non-copyrightable facts (archaeological sites, dates, locations)
3. Transformative use that serves a different market than the original videos
4. Attribution to original sources
5. Low-sensitivity nature of archaeological content processed through AI

The project's biggest vulnerabilities are:
1. Technical violation of YouTube's ToS through automated transcript access
2. Evolving case law on AI-generated summaries (the Cohere precedent)
3. No copyright indemnification from LLM provider (MiniMax offers no copyright shield)
4. MiniMax data sovereignty concerns (Chinese parent company, US Entity List, ToS allow training on API data)

---

## Sources

### YouTube ToS & Scraping
- [YouTube API Services Terms of Service](https://developers.google.com/youtube/terms/api-services-terms-of-service)
- [YouTube API Developer Policies](https://developers.google.com/youtube/terms/developer-policies)
- [YouTube ToS Explained - TLDRLegal](https://www.tldrlegal.com/license/youtube-terms-of-service)
- [Does YouTube Allow Scraping - ProxiesAPI](https://proxiesapi.com/articles/does-youtube-allow-scraping)
- [YouTube Transcription and Copyright - Insight7](https://insight7.io/youtube-transcription-and-copyright-what-you-need-to-know/)

### AI Copyright & Fair Use
- [Copyright and AI Part 2 - U.S. Copyright Office](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-2-Copyrightability-Report.pdf)
- [Copyright and AI - U.S. Copyright Office](https://www.copyright.gov/ai/)
- [Generative AI and Copyright Law - Congress.gov](https://www.congress.gov/crs-product/LSB10922)
- [AI-Generated Content and Copyright Law - BuiltIn](https://builtin.com/artificial-intelligence/ai-copyright)
- [Copyright Office New Report on AI Copyrightability - Manatt](https://www.manatt.com/insights/newsletters/copyright-office-releases-new-report-on-copyrightability-of-ai-works)

### Key 2025 Case Law
- [Court Rules AI News Summaries May Infringe Copyright (Advance Local v. Cohere) - Copyright Lately](https://copyrightlately.com/court-rules-ai-news-summaries-may-infringe-copyright/)
- [Advanced Local Media v. Cohere - Loeb & Loeb](https://www.loeb.com/en/insights/publications/2025/11/advanced-local-media-llc--v-cohere-inc)
- [The Year in AI Law: 2025 - Internet Lawyer Blog](https://www.internetlawyer-blog.com/the-year-in-ai-law-2025s-biggest-legal-cases-and-what-they-mean-for-2026/)
- [Mid-Year Review: AI Copyright Cases 2025 - Copyright Alliance](https://copyrightalliance.org/ai-copyright-case-developments-2025/)
- [Bartz v. Anthropic Settlement - Kluwer Copyright Blog](https://legalblogs.wolterskluwer.com/copyright-blog/the-bartz-v-anthropic-settlement-understanding-americas-largest-copyright-settlement/)
- [Bartz v. Anthropic: What Authors Need to Know - Authors Guild](https://authorsguild.org/advocacy/artificial-intelligence/what-authors-need-to-know-about-the-anthropic-settlement/)
- [Kadrey v. Meta Fair Use Ruling - Allgeyer ADR](https://daveadr.com/blog/fairuseandaitraining)
- [Fair Use and AI Training: Two Decisions - Skadden](https://www.skadden.com/insights/publications/2025/07/fair-use-and-ai-training)
- [Thomson Reuters v. ROSS - Carlton Fields](https://www.carltonfields.com/insights/publications/2025/use-of-copyrighted-works-in-ai-training-is-not-fair-use)
- [NYT v. Microsoft/OpenAI - BakerHostetler](https://www.bakerlaw.com/new-york-times-v-microsoft/)

### MiniMax Terms & Data Sovereignty
- [MiniMax Open Platform Terms of Service](https://platform.minimax.io/protocol/terms-of-service)
- [MiniMax API Privacy Policy](https://platform.minimax.io/protocol/privacy-policy)
- [MiniMax M2 Security Privacy Data Safety Guide 2025 - Skywork AI](https://skywork.ai/blog/llm/minimax-m2-security-privacy-data-safety-guide-2025/)
- [Disney, WBD, NBCU Sue AI Firm MiniMax - Variety](https://variety.com/2025/digital/news/disney-warner-bros-discovery-nbcu-lawsuit-minimax-chinese-ai-company-1236520395/)
- [U.S. Blacklists Over 50 Chinese AI Companies - CNBC](https://www.cnbc.com/2025/03/26/us-blacklists-50-chinese-companies-in-bid-to-curb-beijings-ai-chip-capabilities.html)
- [MiniMax Hong Kong IPO - CNBC](https://www.cnbc.com/2026/01/09/minimax-hong-kong-ipo-ai-tigers-zhipu.html)
- [China's National Intelligence Law - China Law Translate](https://www.chinalawtranslate.com/en/what-the-national-intelligence-law-says-and-why-it-doesnt-matter/)

### Anthropic Terms & Indemnification (Historical — previous LLM provider)
- [Anthropic Expanded Legal Protections](https://www.anthropic.com/news/expanded-legal-protections-api-improvements)
- [Anthropic Copyright Shield - Proskauer](https://www.proskauer.com/blog/anthropic-joins-the-party-offers-copyright-shield-to-enterprise-ai-customers)
- [Anthropic Landmark Settlement - Ropes & Gray](https://www.ropesgray.com/en/insights/alerts/2025/09/anthropics-landmark-copyright-settlement-implications-for-ai-developers-and-enterprise-users)
- [Bartz v. Anthropic Settlement - Copyright Alliance](https://copyrightalliance.org/participating-bartz-v-anthropic-settlement/)

### CFAA & Web Scraping Precedent
- [hiQ v. LinkedIn - Ninth Circuit - California Lawyers Association](https://calawyers.org/privacy-law/ninth-circuit-holds-data-scraping-is-legal-in-hiq-v-linkedin/)
- [hiQ v. LinkedIn Lessons Learned - ZwillGen](https://www.zwillgen.com/alternative-data/hiq-v-linkedin-wrapped-up-web-scraping-lessons-learned/)
- [Web Scraping and CFAA - White & Case](https://www.whitecase.com/insight-our-thinking/web-scraping-website-terms-and-cfaa-hiqs-preliminary-injunction-affirmed-again)

### Wikipedia & Creative Commons
- [CC Licenses and AI Training Legal Primer - Creative Commons](https://creativecommons.org/2025/05/15/understanding-cc-licenses-and-ai-training-a-legal-primer/)
- [Using CC-Licensed Works for AI Training - Creative Commons](https://creativecommons.org/using-cc-licensed-works-for-ai-training-2/)
- [Impact of ShareAlike on Generative AI - Open Future](https://openfuture.eu/publication/the-impact-of-share-alike-copyleft-licensing-on-generative-ai/)
- [Wikidata Licensing](https://www.wikidata.org/wiki/Wikidata:Licensing)
- [Wikipedia Urges AI Companies to Use Paid API - TechCrunch](https://techcrunch.com/2025/11/10/wikipedia-urges-ai-companies-to-use-its-paid-api-and-stop-scraping/)

### EU AI Act
- [EU AI Act - Article 50 Transparency Obligations](https://artificialintelligenceact.eu/article/50/)
- [EU AI Act Framework - European Commission](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)
- [Draft Code of Practice on AI Labelling - Jones Day](https://www.jonesday.com/en/insights/2026/01/european-commission-publishes-draft-code-of-practice-on-ai-labelling-and-transparency)
- [EU AI Act Key Compliance - Greenberg Traurig](https://www.gtlaw.com/en/insights/2025/7/eu-ai-act-key-compliance-considerations-ahead-of-august-2025)
- [EU AI Act 2026 Training Data and Copyright - Scalevise](https://scalevise.com/resources/eu-ai-act-2026-changes/)

### Voyage AI
- [Voyage AI Terms of Service](https://www.voyageai.com/tos)
- [Voyage AI Privacy Policy](https://www.voyageai.com/privacy)

### Copyright Office Reports
- [Copyright Office Part 3: Generative AI Training](https://www.copyright.gov/ai/Copyright-and-Artificial-Intelligence-Part-3-Generative-AI-Training-Report-Pre-Publication-Version.pdf)
- [Copyright Office Fair Use Guidance - Wiley](https://www.wiley.law/alert-Copyright-Office-Issues-Key-Guidance-on-Fair-Use-in-Generative-AI-Training)
- [Copyright Office Guidance - Debevoise](https://www.debevoisedatablog.com/2025/06/04/preliminary-copyright-office-guidance-on-fair-use-and-ai-provides-some-answers-but-questions-remain/)
