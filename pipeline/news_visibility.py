"""Which stories have a public page at /news-archive/{slug}.

One definition for the routes (story_page_query), the sitemap and the
library export — the rule used to live in the route module only, which the
pipeline may not import, so the library aggregator would have needed a copy.
A story needs a body and a significance the scorer did not reject;
significance NULL means "not scored yet", not "rejected". The feed
(/api/news/feed) and storyHrefFor() in NewsCard.tsx apply the same rule.
"""

from sqlalchemy import or_

from pipeline.database import NewsItem


def public_story_criteria():
    """SQLAlchemy filter criteria — unpack into .filter(*public_story_criteria())."""
    return (
        NewsItem.post_text.isnot(None),
        or_(NewsItem.significance.is_(None), NewsItem.significance >= 2),
    )
