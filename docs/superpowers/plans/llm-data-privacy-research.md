# LLM API Provider Data Privacy: Critical Research Report

**Date:** 2026-03-19
**Purpose:** Verified facts for a critical, skeptical presentation slide
**Methodology:** Official policy documents, transparency reports, regulatory actions, academic research, EFF analysis

---

## 1. ANTHROPIC (Claude API)

### Official Policy: API Data

**Core claim (from Anthropic Privacy Center, verified):**
> "By default, we will not use your inputs or outputs from our commercial products (e.g. Claude for Work, Anthropic API, Claude Gov, etc.) to train our models."

**Opt-in exception:**
> "If you explicitly report feedback or bugs to us (e.g. via our thumbs up/down feedback button), or otherwise choose to allow us to use your data, then we may use your chats and coding sessions to train our models."

**API data retention:**
- Before September 14, 2025: 30 days
- After September 14, 2025: **7 days**, then automatically deleted
- Safety-flagged content: retained **up to 2 years** (inputs/outputs) and **up to 7 years** (safety classification scores)
- Feedback data (thumbs up/down): retained **5 years**
- Organizations can opt in to 30-day retention via Data Processing Addendum
- Zero Data Retention agreements available for qualifying enterprise customers

### Official Policy: Consumer Products (Free/Pro/Max)

**Critical change -- August 2025:**
> "We will train new models using data from Free, Pro, and Max accounts when this setting is on (including when you use Claude Code from these accounts)."

- Default: training is ON (opt-out required)
- Deadline for existing users to choose: October 8, 2025
- Opted-in data retained up to **5 years** in de-identified form
- Even if you opt out, exceptions apply:
  > "Even if you opt out, we will use Materials for model training when: (1) you provide Feedback to us regarding any Materials, or (2) your Materials are flagged for safety review to improve our ability to detect harmful content, enforce our policies, or advance our safety research."

### What Does NOT Apply to API

The August 2025 consumer changes explicitly:
> "do not apply to services under our Commercial Terms, including Claude for Work, Claude for Government, Claude for Education, or API use, including via third parties such as Amazon Bedrock and Google Cloud's Vertex AI."

### Trust and Safety Monitoring

Even with zero-training policy, Anthropic runs trust and safety classifiers on ALL inputs/outputs. If flagged, content is retained 2-7 years regardless of your tier.

---

## 2. OPENAI

### Official Policy: API Data

**Core claim (from OpenAI developer docs, verified):**
> "Data sent to the OpenAI API is not used to train or improve OpenAI models (unless you explicitly opt in to share data with us)."

This policy became effective **March 1, 2023**. Before that date, OpenAI DID train on API data by default.

**API data retention:**
- Default: **30 days** for abuse monitoring logs
- Zero Data Retention (ZDR): available but requires **prior approval by OpenAI** and acceptance of additional requirements -- not self-service
- Modified Abuse Monitoring (MAM): excludes customer content from abuse logs while retaining platform capabilities
- Application state (threads, files, vector stores): retained **until deletion**

**Important ZDR limitations:**
- Requests using extended prompt caching are NOT ZDR-eligible
- Skills running in OpenAI-hosted containers cannot be used with ZDR enabled

### Consumer Products (ChatGPT Free/Plus)

- Training on conversations is **ON by default**
- Users can opt out in Settings > Data Controls > "Improve the model for everyone"
- In 2025, OpenAI announced a monitoring system that scans ChatGPT conversations for harmful content, escalating to human reviewers authorized to read chats and report users to law enforcement

### Historical Note

The TechCrunch headline from March 2023 tells the story:
> "Addressing criticism, OpenAI will no longer use customer data to train its models by default"

This means before March 2023, they absolutely did use API data for training. The policy change was reactive, not proactive.

### GDPR Enforcement

**December 2024:** Italy's Garante fined OpenAI **EUR 15 million** for:
- Using personal data to train ChatGPT "without having an adequate legal basis"
- Violating "the principle of transparency and the related information obligations towards users"
- Failing to implement adequate age verification
- Failing to report a March 2023 breach that exposed chat histories and payment information of ChatGPT Plus subscribers

OpenAI called the fine "disproportionate" and is appealing.

---

## 3. GOOGLE (Gemini API)

### Official Policy (from Gemini API Additional Terms of Service, verified)

**Paid Services:**
> "Google doesn't use your prompts (including associated system instructions, cached content, and files such as images, videos, or documents) or responses to improve our products."

**Unpaid Services (Free Tier / AI Studio):**
> "Google uses the content you submit to the Services and any generated responses to provide, improve, and develop Google products and services and machine learning technologies."

**Explicit warning for free tier:**
> "Do not submit sensitive, confidential, or personal information to the Unpaid Services."

**Paid tier logging:**
> "For Paid Services, Google logs prompts and responses for a limited period of time, solely for the purpose of detecting violations of the Prohibited Use Policy."

No specific retention duration published for paid tier abuse logs.

### Multi-Product Data Merging

Stanford HAI researchers found that for Google (and Meta, Microsoft, Amazon), "user interactions also routinely get merged with information gleaned from other products consumers use on those platforms -- search queries, sales/purchases, social media engagement."

---

## 4. THE SKEPTICAL ANGLE

### 4.1 Can We Verify These Claims?

**Third-party audits exist but are limited in scope:**
- All three providers (Anthropic, OpenAI, Google) have completed **SOC 2 Type II** audits
- OpenAI's most recent SOC 2 report covers January - June 2025, covering Security, Availability, Confidentiality, and Privacy Trust Services Criteria
- Anthropic has completed independent SOC 2 Type II audit of Claude's infrastructure

**Critical limitation:** SOC 2 audits verify that CONTROLS EXIST and are OPERATING. They do NOT independently verify that every API call's data is actually excluded from training pipelines. The audit scope is defined by the company itself.

### 4.2 Transparency Reports and Government Access

**Anthropic:**
- Publishes semi-annual Government Requests Reports (Jan-Jun 2024, Jul-Dec 2024, Jan-Jun 2025)
- Policy: will not disclose user info "except in accordance with valid legal process (e.g., a validly issued subpoena or warrant)"
- Exception: emergencies involving "imminent physical harm or death"

**OpenAI:**
- Publishes semi-annual reports on government requests for user data
- National Security Letters received: **0-249** in both H1 2024 and H1 2025 (the band itself is mandated by US law -- they cannot give exact numbers)
- Requires warrant for content data, subpoena for non-content metadata

**The 0-249 band problem:** US law forces companies to report NSL/FISA requests in bands of 250. So "0-249" could mean zero requests or 249 requests. This is by legal design -- it is impossible for users to know the true number.

### 4.3 The "Not Training" vs "Not Seeing" Distinction

This is the most critical point for the presentation:

1. **"We don't train on your data"** means the data is excluded from model training pipelines
2. It does NOT mean:
   - Your data is not transmitted to their servers (it is)
   - Your data is not processed by their infrastructure (it is)
   - Your data is not logged temporarily (it is -- 7-30 days)
   - Your data is not readable by safety reviewers (it can be, if flagged)
   - Your data is immune from legal process (it is not)
   - Your data is not stored in memory/cache during processing (it is)

**EFF's framing (December 2025):**
> "If a company stores a lot of data about its users, law enforcement will eventually seek it out."

They specifically warned about bulk surveillance techniques like geofence warrants and keyword searches being applied to AI chat logs.

### 4.4 The August 2025 Coordinated Backtrack

In August 2025, all three major providers simultaneously shifted consumer privacy defaults:
- **Anthropic**: Made training opt-OUT (was previously not training on consumer data)
- **Google**: Similar opt-out policies for Gemini consumer
- **OpenAI**: New monitoring system scanning all ChatGPT conversations

Public sentiment tracking (427,042 social conversations, Aug 1 - Sep 2 2025): only **22% positive** reaction.

This does NOT affect API tiers, but it demonstrates that privacy promises can and do change when business incentives shift.

### 4.5 Has Any Provider Been Caught Violating Their Own Policy?

**Direct policy violations:** No confirmed case of a provider being caught training on API data after promising not to.

**Adjacent violations:**
- OpenAI fined EUR 15M by Italy for training on personal data without legal basis (consumer product, not API)
- OpenAI failed to report a data breach exposing chat histories and payment data
- The Italian DPA also found OpenAI violated transparency obligations

**The absence of evidence problem:** We cannot verify a negative. The fact that no one has been caught does not prove compliance -- it may simply reflect the difficulty of detection.

### 4.6 National Security Letters and Gag Orders

- Companies CAN be compelled to hand over data under National Security Letters
- They CANNOT disclose that they received such a letter (gag order)
- No major AI company currently maintains a warrant canary
- The NSL reporting band of "0-249" is deliberately uninformative by legal design

### 4.7 The Anthropic-DOD Conflict (January-March 2026)

The Pentagon demanded unrestricted access to Anthropic's AI technology. Anthropic refused, citing restrictions against mass surveillance and autonomous weapons. The DoD terminated the $200M contract and ordered all military contractors to stop using Anthropic products.

**EFF's assessment:**
> "The state of your privacy is being decided by contract negotiations between giant tech companies and the U.S. government" -- two entities with poor records protecting civil liberties.

> Privacy protections "shouldn't depend on the decisions of a few powerful people." Congress must enact proper legal restrictions rather than depending on CEO choices, which is "not a sustainable or reliable solution to build our rights on."

---

## 5. PRACTICAL TRUST HIERARCHY

### Tier 1: Local/Self-Hosted (Zero Trust Required)
- Data never leaves your machine
- No policy promises needed
- No government subpoena risk (for the provider)
- Trade-off: smaller models, more hardware cost, no cutting-edge capabilities

### Tier 2: API with DPA/ZDR (Trust but Verify)
- Data transmitted and processed on provider servers
- Not used for training (stated policy)
- Retained 7-30 days for abuse monitoring (or 0 with ZDR)
- Subject to legal process
- SOC 2 audited (limited scope)
- Safety-flagged content retained years regardless
- Provider: Anthropic API (7 days) < OpenAI API (30 days) < OpenAI ZDR (0 days, requires approval)

### Tier 3: Paid Consumer (Trust and Hope)
- Data used for training BY DEFAULT (opt-out required)
- Opt-out available but has exceptions (feedback, safety flags)
- Longer retention (up to 5 years if training enabled)
- Human reviewers may read flagged conversations
- All three providers shifted defaults against users in August 2025

### Tier 4: Free Consumer (Assume Everything is Read)
- Data actively used for training
- Google explicitly warns: "Do not submit sensitive, confidential, or personal information"
- No meaningful privacy expectations
- Longest retention periods

---

## 6. COMPARISON TABLE

| Aspect | Anthropic API | OpenAI API | Google Gemini Paid | Free Tiers (All) |
|---|---|---|---|---|
| Trains on data? | No (flat policy) | No (since Mar 2023) | No | YES (default) |
| Opt-out needed? | N/A | N/A (opt-in available) | N/A | Yes (manual) |
| Retention | 7 days | 30 days (ZDR: 0*) | "limited period" | Indefinite/5yr |
| Safety-flag retention | 2-7 years | Not specified | Not specified | Same or worse |
| ZDR available? | Yes (enterprise) | Yes (requires approval) | Not documented | No |
| SOC 2 audited? | Yes (Type II) | Yes (Type II) | Yes (Google Cloud) | Same infra |
| Transparency report? | Yes (semi-annual) | Yes (semi-annual) | Google-wide | Same |
| NSL-resistant? | No | No | No | No |
| GDPR fined? | No | Yes (EUR 15M, Italy) | No (for Gemini) | N/A |

*ZDR = Zero Data Retention. OpenAI ZDR requires prior approval and has feature limitations.

---

## 7. KEY QUOTES FOR SLIDES

**The promise:**
> "By default, we will not use your inputs or outputs from our commercial products to train our models." -- Anthropic Privacy Center

**The caveat:**
> "Even if you opt out, we will use Materials for model training when [...] your Materials are flagged for safety review." -- Anthropic Consumer Terms

**The historical lesson:**
> "Addressing criticism, OpenAI will no longer use customer data to train its models by default." -- TechCrunch, March 2023 (meaning they used to)

**The enforcement:**
> OpenAI used personal data to train ChatGPT "without having an adequate legal basis and violated the principle of transparency." -- Italian Garante, December 2024 (EUR 15M fine)

**The skeptic's view:**
> "The state of your privacy is being decided by contract negotiations between giant tech companies and the U.S. government." -- Electronic Frontier Foundation, March 2026

**The researcher's warning:**
> All six leading U.S. AI companies "routinely collect user conversations to train and improve their systems, often without explicit consent." -- Stanford HAI, October 2025

**The uncomfortable truth:**
> "If a company stores a lot of data about its users, law enforcement will eventually seek it out." -- Electronic Frontier Foundation, December 2025

---

## 8. SOURCES

### Official Policy Documents
- Anthropic Privacy Policy: https://www.anthropic.com/legal/privacy
- Anthropic Consumer Terms: https://www.anthropic.com/legal/consumer-terms
- Anthropic Privacy Center (training): https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training
- Anthropic Privacy Center (retention): https://privacy.claude.com/en/articles/10023548-how-long-do-you-store-my-data
- Anthropic Privacy Center (org retention): https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data
- Anthropic Consumer Terms Update (Aug 2025): https://www.anthropic.com/news/updates-to-our-consumer-terms
- OpenAI Data Controls: https://developers.openai.com/api/docs/guides/your-data
- OpenAI Data Training Policy: https://openai.com/policies/how-your-data-is-used-to-improve-model-performance/
- Google Gemini API Terms: https://ai.google.dev/gemini-api/terms

### Transparency Reports
- Anthropic Gov Requests (H1 2024): https://assets.anthropic.com/m/670b32af84ad8a00/original/Anthropic-Government-Requests-Report-Jan-June-2024.pdf
- OpenAI Gov Requests (H1 2024): https://cdn.openai.com/trust-and-transparency/report-2024h1-government-requests-for-user-data.pdf
- OpenAI Gov Requests (H1 2025): https://cdn.openai.com/trust-and-transparency/report-2025h1-government-requests-for-user-data.pdf
- OpenAI Trust Portal: https://trust.openai.com/

### Third-Party Analysis
- EFF: AI Chatbot Surveillance (Dec 2025): https://www.eff.org/deeplinks/2025/12/ai-chatbot-companies-should-protect-your-conversations-bulk-surveillance
- EFF: Anthropic-DOD Conflict (Mar 2026): https://www.eff.org/deeplinks/2026/03/anthropic-dod-conflict-privacy-protections-shouldnt-depend-decisions-few-powerful
- Stanford HAI: AI Chatbot Privacy Risks (Oct 2025): https://hai.stanford.edu/news/be-careful-what-you-tell-your-ai-chatbot
- TechCrunch: Anthropic Training Choice (Aug 2025): https://techcrunch.com/2025/08/28/anthropic-users-face-a-new-choice-opt-out-or-share-your-data-for-ai-training/
- TechCrunch: OpenAI Policy Change (Mar 2023): https://techcrunch.com/2023/03/01/addressing-criticism-openai-will-no-longer-use-customer-data-to-train-its-models-by-default/

### Regulatory Actions
- Italy Fines OpenAI EUR 15M (Dec 2024): https://www.euronews.com/next/2024/12/20/italys-privacy-watchdog-fines-openai-15-million-after-probe-into-chatgpt-data-collection
- SOC 2 Comparative Analysis: https://www.tdcommons.org/dpubs_series/7951/

### Critical Commentary
- AI Data Privacy 2026 - The Privacy Trap: https://drainpipe.io/ai-data-privacy-2026-the-ai-privacy-trap/
- Anthropic Policy Analysis (Lexology): https://www.lexology.com/library/detail.aspx?g=619e126a-e78e-475d-97d9-d6067f1505b6
