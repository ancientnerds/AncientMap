# EU AI Act Compliance Analysis for AncientMap

**Date:** 2026-03-19
**Status:** Research complete. Article 50 obligations apply from August 2, 2026.

---

## Executive Summary

AncientMap uses LLM APIs (Claude, Mercury) to generate news articles, run a RAG chatbot (Lyra), auto-discover archaeological sites, and produce weekly digest articles. Under the EU AI Act, this project is classified as **limited risk** (not high-risk) and is primarily subject to **Article 50 transparency obligations**, which take effect **August 2, 2026**. The **AI literacy obligation** (Article 4) is already in effect since February 2, 2025, though enforcement begins August 2, 2026.

No feature of AncientMap falls under the high-risk or prohibited categories. No opt-out mechanism is required by the Act. The main compliance burden is **disclosure and labeling**.

---

## 1. Risk Classification

### AncientMap's classification: LIMITED RISK

The EU AI Act uses four risk tiers:

| Tier | Examples | AncientMap? |
|------|----------|-------------|
| **Prohibited** (Art. 5) | Social scoring, manipulative AI, real-time biometric surveillance | No |
| **High-Risk** (Art. 6, Annex III) | Biometrics, critical infrastructure, employment, education, law enforcement, migration, credit scoring | No |
| **Limited Risk** (Art. 50) | Chatbots, AI-generated content, deepfakes | **Yes** |
| **Minimal Risk** | Spam filters, video game AI | No |

**Why not high-risk:** Annex III lists eight high-risk domains: (1) biometrics, (2) critical infrastructure, (3) education/vocational training, (4) employment/worker management, (5) essential services/benefits, (6) law enforcement, (7) migration/border control, (8) democratic processes. Archaeological site mapping, news generation, and chatbots about archaeology do not fall into any of these categories.

**Why limited risk:** AncientMap deploys AI systems that directly interact with users (Lyra chatbot) and generates text content published to inform the public (news articles, digests). Both triggers place it squarely under Article 50.

---

## 2. AncientMap's Role: Provider or Deployer?

### Definitions (Article 3)

- **Provider:** "A natural or legal person...that develops an AI system...and places it on the market or puts the AI system into service under its own name or trademark."
- **Deployer:** "A natural or legal person...using an AI system under its authority except where the AI system is used in the course of a personal non-professional activity."

### AncientMap is BOTH a provider and a deployer

AncientMap integrates Claude and Mercury APIs into its own product (Lyra chatbot, article pipeline) and offers them under its own name. Per legal analysis:

- **As a deployer** of Claude/Mercury: AncientMap uses third-party AI systems under its own authority. This triggers Article 50(4) obligations for AI-generated text disclosure.
- **As a provider** of Lyra (the chatbot): AncientMap develops and puts into service an AI system that directly interacts with natural persons. This triggers Article 50(1) obligations.
- **As a provider** of the article pipeline: AncientMap develops a system that generates synthetic text content. This triggers Article 50(2) obligations for machine-readable marking.

Key precedent: Companies that "integrate existing AI models into their own products and offer them under their own name" are considered providers of the resulting AI system, even if they did not train the underlying model.

The RAG layer, prompt engineering, and custom pipeline logic in Lyra may constitute "substantial modifications" that further cement provider status.

---

## 3. Article 50 Obligations: What Exactly Must AncientMap Do?

### 3.1 Article 50(1) -- Chatbot Disclosure (Lyra)

**Full text:** "Providers shall ensure that AI systems intended to directly interact with natural persons are designed and developed in such a way that the natural persons concerned are informed that they are interacting with an AI system, unless this is obvious from the point of view of a natural person who is reasonably well-informed, observant and circumspect, taking into account the circumstances and the context of use."

**What this means for AncientMap:**
- Lyra MUST disclose to users that they are interacting with an AI system
- The disclosure must happen "at the latest at the time of the first interaction" (Art. 50(5))
- It must be "clear and distinguishable" and accessible per Directive (EU) 2019/882
- **Exception:** Only if it would be "obvious" to a reasonable person -- given that Lyra is named like a character and conversationally responds, it is NOT obvious that it is AI
- **Required action:** Display a clear notice before or at the start of any Lyra conversation stating it is an AI system

### 3.2 Article 50(2) -- Machine-Readable Marking (Article Pipeline)

**Full text:** "Providers of AI systems, including general-purpose AI systems, generating synthetic audio, image, video or text content, shall ensure that the outputs of the AI system are marked in a machine-readable format and detectable as artificially generated or manipulated."

**What this means for AncientMap:**
- All AI-generated articles, digests, and text content must be marked in a machine-readable format
- The marking must be "effective, interoperable, robust and reliable" considering technical limitations
- For text specifically, the Code of Practice suggests: digitally signed provenance certificates (since watermarking degrades text quality)
- C2PA metadata standards are the emerging reference standard
- **Required action:** Embed machine-readable markers or metadata in AI-generated articles indicating AI origin

### 3.3 Article 50(4) -- AI-Generated Text Disclosure (News Articles, Digests)

**Full text:** "Deployers of an AI system that generates or manipulates text which is published with the purpose of informing the public on matters of public interest shall disclose that the text has been artificially generated or manipulated."

**The "matters of public interest" question:**
The Act does not define "matters of public interest." Legal commentary suggests it covers news, informational, and editorial content intended to inform the public on significant issues. Archaeological news articles and weekly digests about archaeological discoveries likely qualify, as they are published with the purpose of informing the public about cultural heritage and scientific findings.

**The editorial review exception:**
The disclosure obligation does NOT apply "where the AI-generated content has undergone a process of human review or editorial control and where a natural or legal person holds editorial responsibility for the publication of the content."

Both conditions must be met cumulatively:
1. The content underwent human review or editorial control, AND
2. A natural or legal person holds editorial responsibility

**IMPORTANT:** The Code of Practice is narrowing this exception. Organizations must maintain:
- A documented editorial workflow with identified responsible persons
- Records demonstrating actual human oversight (not just a checkbox)
- Audit-ready documentation of the review process

**What this means for AncientMap:**
- **Option A (simpler):** Label all AI-generated articles with a visible disclosure like "This article was generated with the assistance of AI" -- this satisfies Article 50(4) directly
- **Option B (editorial exception):** If a human reviews and edits every article before publication AND assumes formal editorial responsibility, the disclosure is not required -- but this requires documented workflows and audit readiness

**Recommendation:** Option A is far simpler and more defensible. Just label the content.

### 3.4 Article 50(5) -- Timing and Accessibility

"Information referred to in paragraphs 1 to 4 shall be provided to the natural persons concerned in a clear and distinguishable manner at the latest at the time of the first interaction or exposure. The information shall conform with the applicable accessibility requirements."

---

## 4. AI Literacy Requirement (Article 4)

### Status: IN EFFECT since February 2, 2025

**Full text:** "Providers and deployers of AI systems shall take measures to ensure, to the best of their extent, a sufficient level of AI literacy of their staff and other persons dealing with the operation and use of AI systems on their behalf, taking into account their technical knowledge, experience, education and training and the context the AI systems are to be used in, and considering the persons or groups of persons on whom the AI systems are to be used."

**What this means for AncientMap:**
- Anyone operating or developing the AI pipeline (you, any contributors, contractors) must have a sufficient level of AI literacy
- "Sufficient" is proportionate to the risk level -- for limited-risk systems, this is a lighter requirement
- No specific training format is mandated -- can be self-directed learning, documentation, workshops
- The European Commission states: "The AI Office will not impose strict requirements" and emphasizes "necessary flexibility"

**Practical compliance:**
- Document that team members understand how the AI systems work, their limitations, and appropriate use
- For a small project/solo developer already building with AI APIs, baseline literacy is inherently met
- Enforcement begins August 2, 2026, but the obligation is already legally in force

---

## 5. Timeline: What Applies When?

| Date | What Takes Effect | Relevant to AncientMap? |
|------|-------------------|------------------------|
| **Feb 2, 2025** | Prohibited AI practices banned; AI literacy (Art. 4) applies | Yes -- AI literacy already in effect |
| **Aug 2, 2025** | GPAI model rules; governance bodies; national penalty laws | Indirectly (Claude/Mercury providers must comply) |
| **Aug 2, 2026** | Article 50 transparency; high-risk system rules; full enforcement begins | **Yes -- primary compliance deadline** |
| **Aug 2, 2027** | High-risk AI embedded in regulated products | No |

### Current status (March 2026):
- AI literacy: **In effect** (enforcement starts Aug 2026)
- Article 50 transparency: **Not yet in effect** -- applies from August 2, 2026
- Code of Practice: Final version expected June 2026, ahead of August enforcement
- You have approximately **4.5 months** to implement compliance measures

---

## 6. Penalties for Non-Compliance (Article 99)

### Fine structure:

| Violation Type | Standard Fine | SME/Startup Fine |
|----------------|---------------|------------------|
| **Prohibited AI** (Art. 5) | Up to 35M EUR or 7% worldwide turnover (higher) | Lower of 35M EUR or 7% turnover |
| **Other obligations** incl. Art. 50 | Up to 15M EUR or 3% worldwide turnover (higher) | Lower of 15M EUR or 3% turnover |
| **Misleading info** to authorities | Up to 7.5M EUR or 1% worldwide turnover (higher) | Lower of 7.5M EUR or 1% turnover |

### SME/startup protection:
For SMEs including startups, the calculation is inverted: the fine is **whichever is LOWER** of the fixed amount or the percentage. This means a startup with 100K EUR annual revenue faces a maximum of 3K EUR (3% of 100K) for Article 50 violations, not 15M EUR.

### Mitigating factors considered:
- Nature, gravity, and duration of the infringement
- Intentional vs. negligent conduct
- Actions taken to mitigate damage
- Prior violations
- Size and market position of the offender
- Financial benefit from the violation
- Cooperation with authorities
- Whether the offender is a natural person or undertaking

### Practical risk assessment for AncientMap:
Given AncientMap is a small project/startup with minimal revenue, penalties would be calculated on the lower SME scale. The most likely enforcement scenario would be a warning or corrective order before any fine, particularly for transparency violations where the fix is straightforward (add labels).

---

## 7. Opt-Out Mechanisms

### The EU AI Act does NOT require:
- An opt-out mechanism for AI-generated content
- A human alternative to the chatbot
- User ability to refuse AI interaction
- User consent before AI processing (that is GDPR territory, separate from the AI Act)

### What IS required:
- **Disclosure** that content is AI-generated (for matters of public interest)
- **Notification** that users are interacting with an AI system (for chatbots)
- These are transparency obligations, not consent mechanisms

### GDPR considerations (separate from AI Act):
If AncientMap processes personal data of EU users (analytics, user accounts, etc.), GDPR applies independently. The AI Act explicitly states it does not affect GDPR obligations.

---

## 8. Practical Compliance Checklist for AncientMap

### Priority 1: Before August 2, 2026 (MANDATORY)

- [ ] **Lyra chatbot disclosure:** Add a clear, visible notice at the start of every Lyra conversation: "You are interacting with Lyra, an AI assistant. Responses are generated by artificial intelligence and may contain inaccuracies."
- [ ] **Article labels:** Add a visible disclosure on all AI-generated articles and digests: "This article was generated with the assistance of AI" or similar clear wording
- [ ] **Machine-readable marking:** Add metadata to AI-generated content indicating AI origin (consider C2PA standard or custom metadata fields in your JSON/HTML output)
- [ ] **AI literacy documentation:** Document that team members understand the AI systems used, their capabilities, and limitations (even a brief internal document suffices for a small project)

### Priority 2: Recommended Best Practices

- [ ] **Transparency page:** Create a page explaining how AI is used in the project (which models, for what purposes, limitations)
- [ ] **Content taxonomy:** Distinguish between "fully AI-generated" and "AI-assisted" content in your metadata (the Code of Practice draws this distinction)
- [ ] **Editorial workflow documentation:** If you choose to use the editorial review exception for any content, document the review process with identified responsible persons
- [ ] **Source attribution:** Already good practice -- note when site data was AI-discovered vs. manually curated

### Priority 3: Nice to Have

- [ ] **Provenance certificates:** Implement C2PA-compatible provenance metadata for generated articles
- [ ] **Feedback mechanism:** Allow users to report issues with AI-generated content
- [ ] **Version tracking:** Track which AI model version generated each piece of content

---

## 9. Specific Guidance by AncientMap Feature

### Lyra Chatbot
- **Classification:** Limited risk, Article 50(1)
- **Required:** Disclose AI nature before/at first interaction
- **Not required:** Human alternative, opt-out, consent mechanism
- **Implementation:** Banner/notice in chat UI: "Lyra is an AI assistant powered by large language models. It may produce inaccurate information."

### News Article Pipeline (from YouTube transcripts)
- **Classification:** Limited risk, Article 50(2) + 50(4)
- **Required:** Machine-readable AI marking + visible disclosure if published on matters of public interest
- **Editorial exception available:** If articles are human-reviewed before publication with documented workflow
- **Implementation:** Add "AI-generated" label and metadata tag to each article

### Archaeological Site Auto-Discovery
- **Classification:** Minimal risk (internal data processing, not user-facing AI interaction)
- **Required:** Nothing specific under Article 50 (no direct user interaction, no published text)
- **Note:** The AI classification of sites is a tool output, not a published assertion -- no labeling needed for the mapping itself

### Weekly Digest Articles
- **Classification:** Limited risk, Article 50(2) + 50(4)
- **Required:** Same as news articles -- visible disclosure + machine-readable marking
- **Implementation:** Same approach as news articles

---

## 10. What AncientMap Does NOT Need to Worry About

1. **High-risk AI compliance** -- archaeological mapping is not in Annex III
2. **Conformity assessments** -- only for high-risk systems
3. **Registration in EU database** -- only for high-risk systems
4. **Fundamental rights impact assessments** -- only for high-risk systems deployed by public bodies
5. **GPAI model obligations** -- these apply to Anthropic (Claude) and Inception Labs (Mercury), not to AncientMap as an API consumer
6. **Deepfake rules** -- AncientMap does not generate synthetic images/audio/video of real people
7. **Biometric/emotion recognition rules** -- not applicable
8. **Opt-out mechanisms** -- not required by the AI Act

---

## Sources

### Official EU Sources
- [EU AI Act Article 50 - AI Act Service Desk (European Commission)](https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-50)
- [Guidelines and Code of Practice on transparent AI systems - European Commission](https://digital-strategy.ec.europa.eu/en/faqs/guidelines-and-code-practice-transparent-ai-systems)
- [Code of Practice on marking and labelling of AI-generated content](https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content)
- [AI Literacy - Questions & Answers - European Commission](https://digital-strategy.ec.europa.eu/en/faqs/ai-literacy-questions-answers)
- [Implementation Timeline - EU AI Act](https://artificialintelligenceact.eu/implementation-timeline/)
- [Annex III: High-Risk AI Systems](https://artificialintelligenceact.eu/annex/3/)
- [Article 99: Penalties](https://artificialintelligenceact.eu/article/99/)
- [Article 3: Definitions](https://artificialintelligenceact.eu/article/3/)
- [Article 4: AI Literacy](https://artificialintelligenceact.eu/article/4/)

### Legal Analysis
- [WilmerHale: Limited-Risk AI -- A Deep Dive Into Article 50](https://www.wilmerhale.com/en/insights/blogs/wilmerhale-privacy-and-cybersecurity-law/20240528-limited-risk-ai-a-deep-dive-into-article-50-of-the-european-unions-ai-act)
- [Bird & Bird: Taking the EU AI Act to Practice -- Understanding the Draft Transparency Code of Practice](https://www.twobirds.com/en/insights/2026/taking-the-eu-ai-act-to-practice-understanding-the-draft-transparency-code-of-practice)
- [Ashurst: Transparency of AI-generated content -- the EU's first draft Code of Practice](https://www.ashurst.com/en/insights/transparency-of-ai-generated-content-the-eu-first-draft-code-of-practice/)
- [Jones Day: European Commission Publishes Draft Code of Practice on AI Labelling](https://www.jonesday.com/en/insights/2026/01/european-commission-publishes-draft-code-of-practice-on-ai-labelling-and-transparency)
- [HAERTING: Provider or Deployer? Decoding the Key Roles in the AI Act](https://haerting.de/en/insights/provider-or-deployer-decoding-the-key-roles-in-the-ai-act/)
- [Holistic AI: Penalties of the EU AI Act](https://www.holisticai.com/blog/penalties-of-the-eu-ai-act)
- [A&O Shearman: Obligations for limited-risk AI systems](https://www.aoshearman.com/en/insights/ao-shearman-on-tech/zooming-in-on-ai-11-eu-ai-act-what-are-the-obligations-for-the-limited-risk-ai-systems)
