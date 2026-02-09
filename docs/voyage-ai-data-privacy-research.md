# Voyage AI Data Privacy and Data Handling Research Report

**Date:** February 9, 2026
**Status:** Comprehensive research completed
**Context:** Voyage AI (voyageai.com) was acquired by MongoDB on February 24, 2025 for $220M. As of 2026, Voyage AI operates under MongoDB but maintains its own Terms of Service and Privacy Policy at voyageai.com. Models include voyage-4, voyage-4-large (embeddings) and rerank-2.5-lite (reranking).

---

## 1. Data Retention

### Default (Opted-In) Behavior
- **Voyage AI DOES store customer content by default.** Text sent for embedding or reranking is retained indefinitely under the default terms.
- No specific retention period is stated in their ToS or Privacy Policy for opted-in users. The license granted is described as "perpetual" and "irrevocable."

### Opted-Out Behavior
- Customers who opt out get **zero-day retention**: "Customer Content provided after such opt out will be immediately deleted by Voyage AI after it is processed for you." (ToS Section 3)
- The opt-out only applies to data submitted AFTER opting out. Data submitted before the opt-out remains subject to the original license.
- Opt-out is irreversible through the dashboard; to opt back in, you must contact legal@voyageai.com.

### How to Opt Out
1. Must have a **payment method on file**
2. Must be an **organization Admin**
3. Log into dashboard > Organization > Terms of Service section
4. Toggle the "Opted In" slider to "Opted Out"

### Critical Caveat
The ToS states: "If you opt out, any credits or tokens for free usage of the Service may be automatically void." This means **opting out may forfeit your free tier allocation.**

**Source:** https://www.voyageai.com/tos, https://docs.voyageai.com/docs/faq

---

## 2. Training Data Usage

### Default (Opted-In)
Unless you opt out, you grant Voyage AI:
> "a worldwide, irrevocable, perpetual, royalty-free, fully paid-up right and license to use, copy, reproduce, distribute, and prepare derivative works of your Customer Content to:
> (i) maintain and provide the Service
> (ii) exercise its rights and perform its obligations
> (iii) train, improve, and otherwise further develop the Service (such as by training the artificial intelligence models)"

**This means your embedding input text IS used to train their models by default.**

### Opted-Out
If you opt out (Section 3(iii) specifically), Voyage AI retains only the rights in (i) and (ii) -- operating the service and fulfilling obligations. They lose the right to use your data for model training.

**Source:** https://www.voyageai.com/tos

---

## 3. Data Processing Infrastructure

### Voyage AI Hosted API
- Privacy policy states data is maintained "at our premises, or the premises of our third-party providers."
- No specific data center locations are disclosed in their public documentation.
- Information may be transferred to the United States (per Privacy Policy).

### Self-Hosted Alternatives (No Data Leaves Your Infrastructure)
- **AWS Marketplace:** Deploy Voyage AI models in your own AWS account/VPC via SageMaker. Customer maintains full control over data flow.
- **GCP Model Garden:** Available on Google Cloud Vertex AI.
- **Azure Managed Applications:** Available on Azure Marketplace.
- **MongoDB Atlas Embedding & Reranking API:** Available in public preview (launched Jan/Feb 2026), runs within MongoDB Atlas infrastructure.

### Post-Acquisition (MongoDB)
MongoDB Atlas infrastructure is available across AWS, GCP, and Azure with data residency options. However, the voyageai.com hosted API's specific infrastructure is not publicly documented.

**Source:** https://docs.voyageai.com/docs/aws-marketplace-voyage, https://blog.voyageai.com/2026/01/15/new-models-and-expanded-availability/

---

## 4. Compliance and Certifications

### Voyage AI (Standalone)
- **No publicly listed certifications.** Voyage AI's website and documentation do not mention SOC 2, ISO 27001, HIPAA, GDPR compliance, or any third-party security audits.
- Security measures mentioned: SSL encryption for sensitive data, industry standard security practices.
- CCPA: California residents can request data disclosures under CCPA and "Shine the Light" law.
- Children: No intentional collection from users under 13.
- **No published DPA (Data Processing Agreement)** specific to Voyage AI.
- No trust portal or security page exists at voyageai.com.

### MongoDB (Parent Company)
MongoDB Atlas holds extensive certifications that MAY apply to the Atlas-hosted Voyage AI API:
- SOC 2 Type II
- ISO/IEC 27001:2022
- ISO 27017:2015, ISO 27018:2019
- ISO 9001:2015
- PCI DSS
- HIPAA
- HITRUST
- FedRAMP Moderate (Atlas for Government)
- CSA STAR
- GDPR-compliant DPA with EU SCCs, UK IDTA, Swiss FADP provisions

**Important:** It is unclear whether these MongoDB certifications extend to the voyageai.com hosted API or only to the Atlas Embedding & Reranking API.

**Source:** https://www.mongodb.com/products/platform/trust, https://www.mongodb.com/products/platform/trust/soc, https://www.mongodb.com/products/platform/trust/iso

---

## 5. Terms of Service: Key Clauses

### Data Ownership
"You retain ownership of all data and other information you provide to Voyage AI." -- However, ownership is separate from the license granted.

### License Grant (Default)
Worldwide, irrevocable, perpetual, royalty-free license to use Customer Content for service operation AND model training (unless opted out).

### Fine-Tuned Models
Voyage AI owns custom models created through fine-tuning but will NOT sell or distribute them to third parties. They may use fine-tuned models internally.

### Platform Data
Voyage AI collects operational analytics and metadata ("Platform Data") separately from Customer Content. Platform Data excludes actual content and won't be disclosed in ways identifying the customer, except to employees/contractors under confidentiality obligations.

### Limitation of Liability
Standard limitation applies -- no guarantee of 100% security.

**Source:** https://www.voyageai.com/tos

---

## 6. Privacy Policy: API Data Handling

### What Is Collected
- **Customer Content:** Data uploaded via APIs (the text you send for embedding/reranking)
- **Direct information:** Name, email, payment details, phone number, employer, job title
- **Usage data:** IP address, browser type, device identifiers, pages visited, time spent

### Third-Party Sharing
- Data shared with: service providers (security, SMS, customer support), business account administrators, acquiring companies in business transfers
- Customer Content will NOT be disclosed to third parties "other than to our sub-processors and subcontractors acting on our behalf" or in "aggregate and anonymized manner"
- No published list of sub-processors

### Breach Notification
Via email or account page notification (no specific timeline committed)

### Data Transfer
Information may be transferred to the United States

**Source:** https://www.voyageai.com/privacy

---

## 7. Reranking Data Handling

**There is no separate privacy policy or data handling distinction for reranking vs. embedding calls.** The same Terms of Service and Privacy Policy apply to all API calls, including:
- Embedding requests (voyage-4, voyage-4-large, etc.)
- Reranking requests (rerank-2.5, rerank-2.5-lite, etc.)

This means the query + document pairs sent to the reranking API are subject to the same default retention and training license as embedding input text. The opt-out mechanism applies equally to both.

**Source:** https://www.voyageai.com/tos (covers "the Service" holistically), https://docs.voyageai.com/docs/reranker

---

## 8. Free Tier vs. Paid: Privacy Differences

### Explicit Differences
- **None documented.** The Privacy Policy and ToS make no distinction between free and paid tier data handling.

### Implicit Difference (Critical)
- **Opting out of data training requires a payment method on file** and may void free tier credits.
- This means free tier users effectively CANNOT opt out of data training without adding a payment method and potentially losing their free allocation.
- Free tier allocations: 200M tokens for voyage-4 models; 200M tokens for rerankers.

### Interpretation
Free tier usage is functionally subsidized by the data training license. If you want privacy, you must pay (or at least register a payment method and accept the loss of free credits).

**Source:** https://docs.voyageai.com/docs/faq, https://docs.voyageai.com/docs/pricing, https://www.voyageai.com/tos

---

## 9. Data Sharing with Third Parties

### Customer Content
- Shared ONLY with sub-processors and subcontractors acting on Voyage AI's behalf
- May be shared in "aggregate and anonymized manner that does not identify you"
- No published sub-processor list

### Personal Information
Shared with:
- Service providers (security, SMS/communications, customer support tools)
- Business account administrators (if applicable)
- Third parties with explicit user consent
- Acquiring companies in mergers/acquisitions/business transfers

### Post-Acquisition Context
MongoDB acquired Voyage AI in February 2025. This constitutes a business transfer. User data may have been transferred to MongoDB per the "acquiring companies" provision.

**Source:** https://www.voyageai.com/privacy

---

## 10. Comparison with OpenAI Embeddings API

| Feature | Voyage AI | OpenAI |
|---------|-----------|--------|
| **Default training on API data** | YES (opted-in by default) | NO (API data not used for training by default since March 2023) |
| **Data retention (default)** | Indefinite (no stated period) | 30 days (for abuse monitoring) |
| **Zero retention available** | Yes (opt-out via dashboard) | Yes (ZDR, requires approval from sales) |
| **Opt-out mechanism** | Self-service dashboard toggle | Contact sales team for ZDR approval |
| **Opt-out cost** | May void free tier credits | No stated cost; enterprise feature |
| **SOC 2 Type 2** | Not publicly certified (Voyage AI standalone) | YES, certified |
| **GDPR DPA** | Not published (Voyage AI standalone) | YES, published DPA (updated Jan 2026) |
| **ISO 27001** | Not certified (Voyage AI standalone) | Referenced in trust portal |
| **Encryption** | SSL mentioned | AES-256 at rest, TLS 1.2+ in transit |
| **Self-hosted option** | YES (AWS/GCP/Azure marketplace) | NO (API only) |
| **Parent company certifications** | MongoDB: SOC 2, ISO 27001, HIPAA, FedRAMP, PCI DSS | OpenAI: SOC 2 Type II |
| **Data used for training clarity** | Buried in ToS, opt-out required | Prominently stated: "not used for training" |

### Summary Assessment

**OpenAI has significantly stronger default privacy protections for embeddings:**
- API data is NOT used for training by default (no action required)
- Clear 30-day retention with documented ZDR option
- Published DPA, SOC 2 Type 2 certified, prominent security documentation

**Voyage AI's privacy is weaker by default but can be improved:**
- API data IS used for training unless you explicitly opt out
- Opt-out requires payment method and may void free credits
- No standalone security certifications
- However, the self-hosted deployment option (AWS/GCP/Azure) provides the strongest possible privacy since data never leaves your infrastructure

**MongoDB Atlas Embedding & Reranking API (new option):**
- If using Voyage models through MongoDB Atlas instead of voyageai.com, MongoDB's extensive certifications (SOC 2, ISO 27001, HIPAA, etc.) and DPA likely apply
- This may be the best path for privacy-sensitive usage of Voyage models
- However, this is in public preview as of early 2026 and specific privacy terms are not yet documented

---

## Recommendations for the AncientMap Project

1. **If using Voyage AI's hosted API (voyageai.com):**
   - Immediately opt out of data training via the dashboard
   - Add a payment method first (required for opt-out)
   - Accept that free tier credits may be voided
   - All text sent for embedding/reranking BEFORE opt-out remains subject to training

2. **If privacy is critical:**
   - Consider the MongoDB Atlas Embedding & Reranking API (inherits MongoDB's certifications)
   - Or deploy via AWS SageMaker / GCP Vertex AI for complete data control
   - Or use OpenAI embeddings (text-embedding-3-small/large) which have stronger default privacy

3. **For the RAG pipeline specifically:**
   - The text being embedded includes archaeological site descriptions, news content, and user contributions
   - If any user-generated content flows through embeddings, GDPR considerations apply
   - Opt-out is strongly recommended at minimum

---

## Sources

- Voyage AI Privacy Policy: https://www.voyageai.com/privacy
- Voyage AI Terms of Service: https://www.voyageai.com/tos
- Voyage AI FAQ: https://docs.voyageai.com/docs/faq
- Voyage AI Pricing: https://docs.voyageai.com/docs/pricing
- Voyage AI Opt-Out Discussion: https://docs.voyageai.com/discuss/6697f3313d38730012b50a7b
- Voyage AI AWS Marketplace: https://docs.voyageai.com/docs/aws-marketplace-voyage
- MongoDB Acquisition Announcement: https://investors.mongodb.com/news-releases/news-release-details/mongodb-announces-acquisition-voyage-ai-enable-organizations
- MongoDB Trust Center: https://www.mongodb.com/products/platform/trust
- MongoDB SOC Compliance: https://www.mongodb.com/products/platform/trust/soc
- MongoDB ISO 27001: https://www.mongodb.com/products/platform/trust/iso
- MongoDB Privacy Hub: https://www.mongodb.com/legal/privacy
- MongoDB Atlas Embedding & Reranking API Blog: https://www.mongodb.com/company/blog/product-release-announcements/introducing-the-embedding-and-reranking-api-on-mongodb-atlas
- OpenAI Data Controls: https://platform.openai.com/docs/guides/your-data
- OpenAI Enterprise Privacy: https://openai.com/enterprise-privacy/
- OpenAI Trust Portal: https://trust.openai.com/
