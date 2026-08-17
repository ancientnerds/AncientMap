# SPDX-License-Identifier: AGPL-3.0-only
"""Art. 50(2) EU AI Act: machine-readable AI marking on content API schemas."""

import pytest

from api.routes.news import NewsArticleResponse, NewsItemResponse
from api.schemas.public_v1 import ArticleSummary, NewsItemPublic, ResearchPaperSummary


@pytest.mark.parametrize(
    ("schema", "expected_system"),
    [
        (NewsItemPublic, "lyra-news"),
        (NewsItemResponse, "lyra-news"),
        (ArticleSummary, "lyra-journal"),
        (NewsArticleResponse, "lyra-journal"),
        (ResearchPaperSummary, "theo-research"),
    ],
)
def test_content_schemas_carry_ai_marking(schema, expected_system):
    assert schema.model_fields["ai_generated"].default is True
    assert schema.model_fields["ai_system"].default == expected_system
