"""Which stories have a public page at /news-archive/{slug}.

One definition for the routes (story_page_query), the sitemap and the
library export — the rule used to live in the route module only, which the
pipeline may not import, so the library aggregator would have needed a copy.
A story needs a body and a significance of at least 2 from the scorer. Until
2026-10-09 an unscored story (significance NULL, the state between the posts
and rescore steps) was public too, so a cycle that died in between - a deploy
restart - left stories online, in the sitemap and the feed, that the scorer
then withdrew as 410: 108 new 410s in September, and about a fifth of
Googlebot's requests went to withdrawn stories (SEO audit 2026-10-08; owner
decision 2026-10-09). The feed (/api/news/feed), /api/v1/news and
storyHrefFor() in NewsCard.tsx apply the same rule.
"""

from pipeline.database import NewsItem


def public_story_criteria():
    """SQLAlchemy filter criteria — unpack into .filter(*public_story_criteria())."""
    return (
        NewsItem.post_text.isnot(None),
        NewsItem.significance >= 2,
    )
