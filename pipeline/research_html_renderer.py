"""
HTML rendering for the public research library (SEO pages).

Renders Theo research papers as full HTML pages with ScholarlyArticle
schema markup, CC BY 4.0 license notice, and the site's dark theme.
Shares CSS, nav, and footer with the article renderer.
"""

import re
from datetime import datetime
from html import escape

import markdown  # noqa: I001 — third-party, separated intentionally

from pipeline.article_html_renderer import (
    _SHARED_CSS,
    AI_NOTICE_HTML,
    BASE_URL,
    _footer_html,
    _json_str,
    _nav_html,
    _sanitize_html,
    external_links_new_tab,
    founder_medium_script,
)
from pipeline.lyra.theo_image_captions import _META_VOICE_RE

CC_BY_URL = "https://creativecommons.org/licenses/by/4.0/"

_RESEARCH_CSS = """
    .paper-meta-box {
        background: #0d2229; border: 1px solid #1a3a44; border-radius: 8px;
        padding: 16px 20px; margin-bottom: 28px; font-size: 14px; color: #90a8b0;
    }
    .paper-meta-box .question { font-style: italic; color: #b0c0c8; margin-bottom: 10px; }
    .quality-badge {
        display: inline-block; background: #132830; color: #ffd700;
        padding: 2px 10px; border-radius: 12px; font-size: 13px; margin-right: 8px;
    }
    .license-box {
        border-top: 1px solid #1a3a44; margin-top: 48px; padding-top: 20px;
        font-size: 14px; color: #708890;
    }
    .paper-card .question { font-style: italic; color: #90a8b0; font-size: 0.95em; margin-bottom: 10px; }
    .paper-figure { margin: 28px 0; }
    .paper-figure img { max-width: 100%; height: auto; border-radius: 6px; }
    .paper-figure figcaption {
        color: #708890; font-size: 13px; line-height: 1.5;
        margin-top: 8px; padding-left: 2px;
    }
"""


_REFERENCES_HEADING_RE = re.compile(
    r"^#{1,3}\s*(References|Sources|Bibliography)\b.*$", re.M | re.I
)
_BARE_URL_RE = re.compile(r"(?<![(<\[])(https?://[^\s<>()\[\]]+)")
_DOI_RE = re.compile(r"\bDOI:\s*(10\.\S+?)(?=[\s,;]|$)")


def format_references_md(content_md: str) -> str:
    """
    Rework the References section of a paper for clean rendering.

    Theo emits references as consecutive '[N] ...' lines with bare URLs —
    markdown collapses those into one giant paragraph with dead links.
    This gives each reference its own paragraph and turns bare URLs and
    DOIs into clickable links. Only text after the References heading is
    touched; the paper body stays untouched.
    """
    m = _REFERENCES_HEADING_RE.search(content_md)
    if not m:
        return content_md
    body, refs = content_md[: m.end()], content_md[m.end() :]
    refs = re.sub(r"\n(?=\[\d+\]\s)", "\n\n", refs)
    refs = _DOI_RE.sub(r"DOI: [\1](https://doi.org/\1)", refs)
    refs = _BARE_URL_RE.sub(r"<\1>", refs)
    return body + refs


# Image block as Theo stores it: image line, blank line, italic caption
# line, [Source](...) line.
_FIGURE_BLOCK_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<img>[^)\s]+)\)\s*\n\s*\n"
    r"\*(?P<cap>[^*\n]+)\*\s*\n"
    r"\[Source\]\((?P<src>[^)]+)\)"
)

# Editorial meta-voice that older papers baked into caption tails ("Lets the
# reader verify that...", "Image placed by the paper writer..."). The caption
# builder no longer emits these (theo_image_captions._META_VOICE_RE), but
# published papers carry them in stored markdown — scrub at render time.
_CAPTION_LEAK_RE = re.compile(
    r"\s*(?:Lets?\s+the\s+reader\s+verify\b|Allows?\s+the\s+reader\b|"
    r"Image\s+placed\s+by\s+the\s+paper\s+writer\b)[^*]*$",
    re.IGNORECASE,
)

# Caption + Source block WITHOUT a preceding image (reflow sometimes detaches
# writer-image captions). "Photo:" is required so normal italic emphasis in
# prose is never touched.
_ORPHAN_CAPTION_RE = re.compile(
    r"\*(?P<cap>[^*\n]*Photo:[^*\n]+)\*\s*\n\[Source\]\((?P<src>[^)]+)\)"
)

# Structural caption split: "{lead}. Photo: {artist} / {SOURCE_LABEL}. {tail}".
# The attribution always ends with a known source label; the tail (LLM
# rationale) never contains one — verified across all 10 published papers
# (2026-07-31). Greedy head = split at the LAST label, so artists like
# "Internet Archive Book Images" can't cut the attribution short.
_ATTRIBUTION_SPLIT_RE = re.compile(
    r"^(?P<head>.*Photo:.*"
    r"(?:Wikimedia Commons|Europeana|Open Access|Internet Archive|Getty Museum|"
    r"Musée du Louvre|Portable Antiquities Scheme|The Met|Smithsonian))"
    r"\.\s*(?P<tail>.+)$",
    re.S,
)


def format_image_figures(content_md: str) -> str:
    """
    Turn Theo's image+caption+source markdown blocks into semantic
    <figure>/<figcaption> HTML.

    Markdown renders the caption as a plain italic paragraph — visually glued
    to the body text, and Medium pastes it as ordinary prose. A real
    figcaption separates it on our pages AND becomes a native image caption
    when pasted into Medium's editor. Also strips the gallery metadata prefix
    from alt text and scrubs leaked editorial meta-voice from captions.
    """

    def _caption_html(raw_cap: str, src: str) -> str:
        cap = _CAPTION_LEAK_RE.sub("", raw_cap).strip()
        # Generic meta-voice scrub for stored papers: drop any rationale tail
        # after the attribution that talks about the paper/reader/evidence
        # apparatus instead of the artifact (28 leaked captions across 9 of
        # 10 published papers, many phrasings — pattern lists don't scale).
        m = _ATTRIBUTION_SPLIT_RE.match(cap)
        if m and _META_VOICE_RE.search(m.group("tail")):
            cap = m.group("head")
        cap = cap.replace("Unknown authorUnknown author", "Unknown author")
        cap = cap.strip().rstrip(".")
        cap_html = f"{escape(cap)}. " if cap else ""
        return (
            f"<figcaption>{cap_html}"
            f'<a href="{escape(src)}" target="_blank" rel="noopener">Source</a>'
            f"</figcaption>"
        )

    def _fig(m: re.Match) -> str:
        alt = m.group("alt").split("|")[-1].strip()
        return (
            f'<figure class="paper-figure">'
            f'<img src="{escape(m.group("img"))}" alt="{escape(alt)}" loading="lazy">'
            f"{_caption_html(m.group('cap'), m.group('src'))}</figure>"
        )

    result = _FIGURE_BLOCK_RE.sub(_fig, content_md)

    # Second pass: orphan captions. The reflow step sometimes detaches a
    # writer-placed image's caption from its (inline) image — the caption +
    # Source block then floats between paragraphs. Style and scrub those too;
    # requiring "Photo:" keeps ordinary italic emphasis untouched.
    def _orphan(m: re.Match) -> str:
        return (
            f'<figure class="paper-figure">{_caption_html(m.group("cap"), m.group("src"))}</figure>'
        )

    return _ORPHAN_CAPTION_RE.sub(_orphan, result)


def _pub_display(published_at: str | None) -> tuple[str, str]:
    """Return (ISO date, human-readable date) from an ISO timestamp string."""
    if not published_at:
        return "", ""
    try:
        dt = datetime.fromisoformat(published_at)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return "", published_at


def render_research_listing_html(papers: list[dict]) -> str:
    """
    Render the research library listing page.

    Each dict: paper_summary_kwargs() output (title, question, summary, slug,
    author, published_at, word_count, quality_badge, sources_analyzed).
    """
    cards = []
    for p in papers:
        e_title = escape(p["title"] or "")
        e_question = escape(p["question"] or "")
        e_summary = escape(p.get("summary") or "")
        slug = p["slug"]
        pub_date, pub_display = _pub_display(p.get("published_at"))

        badge = ""
        if p.get("quality_badge"):
            badge = f'<span class="quality-badge">{escape(p["quality_badge"])}</span>'
        word_count = f"{p['word_count']:,} words &middot; " if p.get("word_count") else ""

        cards.append(f"""
        <div class="article-card paper-card">
            <h2><a href="/research/{slug}">{e_title}</a></h2>
            <div class="meta">{badge}<time datetime="{pub_date}">{pub_display}</time>
                &middot; {word_count}by {escape(p.get("author") or "Ancient Nerds")}</div>
            <p class="question">{e_question}</p>
            <p>{e_summary}</p>
            <a href="/research/{slug}" class="read-more">Read full paper &rarr;</a>
        </div>""")

    cards_html = "\n".join(cards) if cards else "<p>No papers published yet. Check back soon!</p>"

    canonical = f"{BASE_URL}/research/"
    schema = f"""{{
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Ancient Nerds Research Library",
        "description": "Open-access deep-research papers on archaeology and ancient history. Fully cited literature syntheses, free to reuse under CC BY 4.0.",
        "url": "{canonical}",
        "license": "{CC_BY_URL}",
        "publisher": {{"@type": "Organization", "name": "Ancient Nerds", "url": "{BASE_URL}"}}
    }}"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Research Library - Open-Access Archaeology Papers | Ancient Nerds</title>
    <meta name="description" content="Open-access research papers on archaeology and ancient history. Multi-thousand-word, fully cited literature syntheses — free to reuse under CC BY 4.0.">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="website">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="Research Library | Ancient Nerds">
    <meta property="og:description" content="Open-access deep-research papers on archaeology and ancient history, CC BY 4.0.">
    <meta property="og:image" content="{BASE_URL}/landing/og-image.png">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Research Library | Ancient Nerds">
    <meta name="twitter:description" content="Open-access deep-research papers on archaeology and ancient history, CC BY 4.0.">
    <meta name="twitter:image" content="{BASE_URL}/landing/og-image.png">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}{_RESEARCH_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="container">
        <h1>Research Library</h1>
        <p class="meta">Deep-research papers on archaeology and ancient history — AI-generated by
        Theo, the Ancient Nerds AI research pipeline, and published after automated quality and
        citation checks.
        Open access under <a href="{CC_BY_URL}" rel="license" target="_blank">CC BY 4.0</a> —
        reuse freely, attribution to Ancient Nerds is the only requirement.
        Also available via the <a href="/api.html">public API</a>.</p>
        {cards_html}
    </main>
    {_footer_html()}
</body>
</html>"""


def render_research_paper_html(paper: dict, content_md: str) -> str:
    """Render a single research paper as a full SEO-optimized HTML page."""
    md = markdown.Markdown(extensions=["extra", "smarty", "toc"])
    body_html = external_links_new_tab(
        _sanitize_html(md.convert(format_image_figures(format_references_md(content_md))))
    )

    title = paper["title"] or paper["question"]
    slug = paper["slug"]
    author = paper.get("author") or "Ancient Nerds"
    summary = paper.get("summary") or paper["question"]
    meta_desc = (summary or title)[:160]
    pub_date, pub_display = _pub_display(paper.get("published_at"))

    canonical = f"{BASE_URL}/research/{slug}"
    og_image = escape(paper.get("hero_image_url") or f"{BASE_URL}/landing/og-image.png")
    e_title = escape(title)
    e_desc = escape(meta_desc)
    e_question = escape(paper["question"] or "")

    word_count_json = f'"wordCount": {paper["word_count"]},' if paper.get("word_count") else ""

    is_theo = author == "Theo"
    if is_theo:
        author_schema = (
            '{"@type": "Organization", "name": "Ancient Nerds", '
            '"description": "Generated by Theo, the Ancient Nerds AI research pipeline"}'
        )
    else:
        author_schema = (
            f'{{"@type": "Person", "name": {_json_str(author)}, '
            f'"affiliation": {{"@type": "Organization", "name": "Ancient Nerds"}}}}'
        )
    author_label = f"{escape(author)} (AI research pipeline)" if is_theo else escape(author)

    schema = f"""{{
        "@context": "https://schema.org",
        "@type": "ScholarlyArticle",
        "headline": {_json_str(title)},
        "abstract": {_json_str(summary or "")},
        "datePublished": "{pub_date}",
        "author": {author_schema},
        "publisher": {{"@type": "Organization", "name": "Ancient Nerds", "url": "{BASE_URL}", "logo": {{"@type": "ImageObject", "url": "{BASE_URL}/landing/og-image.png"}}}},
        {word_count_json}
        "license": "{CC_BY_URL}",
        "image": "{og_image}",
        "mainEntityOfPage": "{canonical}",
        "url": "{canonical}"
    }}"""

    badge = ""
    if paper.get("quality_badge"):
        badge = f'<span class="quality-badge">{escape(paper["quality_badge"])}</span>'
    word_count = f" &middot; {paper['word_count']:,} words" if paper.get("word_count") else ""
    sources = (
        f" &middot; {paper['sources_analyzed']} sources analyzed"
        if paper.get("sources_analyzed")
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{e_title} | Ancient Nerds Research</title>
    <meta name="description" content="{e_desc}">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <link rel="canonical" href="{canonical}">

    <meta property="og:type" content="article">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Ancient Nerds">
    <meta property="og:title" content="{e_title}">
    <meta property="og:description" content="{e_desc}">
    <meta property="og:image" content="{og_image}">
    <meta property="article:published_time" content="{pub_date}">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{e_title}">
    <meta name="twitter:description" content="{e_desc}">
    <meta name="twitter:image" content="{og_image}">
    <meta name="twitter:site" content="@AncientNerdsDAO">

    <link rel="icon" type="image/svg+xml" href="/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500;600&family=Orbitron:wght@700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

    <script type="application/ld+json">{schema}</script>
    <style>{_SHARED_CSS}{_RESEARCH_CSS}</style>
</head>
<body>
    {_nav_html()}
    <main class="container">
        <article>
            <h1>{e_title}</h1>
            <div class="paper-meta-box">
                <p class="question">Research question: {e_question}</p>
                {badge}<time datetime="{pub_date}">{pub_display}</time>
                &middot; by {author_label}{word_count}{sources}
                &middot; <a href="/research/">All papers</a>
                &middot; <a href="/research.html?slug={slug}">Interactive view</a><span id="mediumSlot"></span>
            </div>
            {AI_NOTICE_HTML}
            <div class="article-body">
                {body_html}
            </div>
            <div class="license-box">
                <p>This paper is open access under
                <a href="{CC_BY_URL}" rel="license" target="_blank">Creative Commons Attribution 4.0 (CC BY 4.0)</a>.
                Reuse freely — attribution to <strong>{escape(paper.get("attribution") or "Ancient Nerds — https://ancientnerds.com")}</strong> is the only requirement.
                Machine-readable version via the <a href="/api.html">public API</a>.
                The text of this paper was generated by an AI system; images are from the cited sources.</p>
            </div>
        </article>
    </main>
    {_footer_html()}
    {founder_medium_script(f"/research/{slug}/medium")}
</body>
</html>"""
