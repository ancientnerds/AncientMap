# Creator Outreach Email Template

Use this template when reaching out to YouTube archaeology channels to request permission for featuring their content in the Ancient Nerds news feed.

---

## Subject Line Options

- "Ancient Nerds Map — featuring your archaeology content"
- "Partnership request: your videos on our archaeology map"
- "Can we feature your archaeology discoveries?"

---

## Email Template

Hi [Creator Name],

I run Ancient Nerds (https://ancientnerds.com), an open-source interactive globe that maps archaeological sites from 100+ databases worldwide. We recently launched a news feed that highlights new discoveries from archaeology YouTube channels — and your content is exactly the kind we'd love to feature.

**What we do:**
- Our AI extracts archaeological facts (site names, dates, locations, findings) from video captions
- Each news item links directly back to your video with a timestamp, so viewers always land on YOUR content
- Your channel name is credited on every item
- You can see a live example at https://ancientnerds.com/news.html

**What we're asking:**
We'd like your permission to use your video captions to generate these summaries. To be clear:
- We never reproduce your narrative or creative expression — only factual archaeological information
- Every summary links back to your video (with timestamp) to drive viewers to your channel
- You retain full copyright over your content
- You can opt out at any time by emailing us

**What's in it for you:**
- Free promotion to our community of archaeology enthusiasts
- Direct deep-links to specific moments in your videos
- Your channel featured alongside major archaeological databases

If you're interested, a simple "yes, go ahead" reply is all we need. If you have any questions or concerns, I'm happy to discuss.

You can also check out the project on GitHub: https://github.com/AncientNerds/AncientMap

Best regards,
[Your Name]
Ancient Nerds
ancient.nerds@protonmail.com

---

## Follow-Up Template (if no response after 2 weeks)

Subject: Quick follow-up — Ancient Nerds archaeology map

Hi [Creator Name],

Just a quick follow-up on my previous email. We'd love to feature your archaeology content on our interactive map at ancientnerds.com. Every item links directly back to your video.

No worries if you're not interested — just let me know and I won't follow up again.

Best,
[Your Name]

---

## Record-Keeping

When a creator responds, save the permission record:

| Channel | Contact | Date Contacted | Response | Permission Granted | Notes |
|---------|---------|----------------|----------|--------------------|-------|
| | | | | | |

Store email threads as evidence of consent. A simple "yes" or "go ahead" in writing is sufficient.

---

## If a Creator Declines or Doesn't Respond

- Remove their channel from the pipeline configuration (`pipeline/lyra/config.py` channels list)
- No further contact needed
- Their existing news items can remain (they were generated from publicly available content) but no new items should be created
