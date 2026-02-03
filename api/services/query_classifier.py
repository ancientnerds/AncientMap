"""
Query Classifier for Lyra AI Agent.

Classifies user queries into:
- KNOWLEDGE: General questions that can be answered directly by the LLM
- DATABASE: Questions requiring search through the archaeological database
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Type of query for routing."""
    KNOWLEDGE = "knowledge"  # Answer directly with LLM
    DATABASE = "database"    # Search database first, then answer


@dataclass
class ClassificationResult:
    """Result of query classification."""
    query_type: QueryType
    confidence: float  # 0.0 to 1.0
    reason: str
    search_hint: str | None = None  # For DATABASE queries, what to search for
    is_superlative: bool = False  # True for "oldest", "largest", etc. (highlight only top result)


# Patterns that indicate KNOWLEDGE questions (answer directly)
KNOWLEDGE_PATTERNS = [
    # "What does X mean" / "What is the meaning of X"
    (r'^what\s+(does|do|did)\s+.+\s+mean', 0.95, 'meaning question'),
    (r'meaning\s+of\s+', 0.9, 'meaning question'),
    (r'what\s+is\s+the\s+meaning', 0.95, 'meaning question'),

    # "What is the name of" - factual knowledge questions
    (r'^what.+name\s+of', 0.95, 'name question'),
    (r'^what.+called', 0.9, 'name question'),
    (r'^who\s+is\s+the\s+god', 0.95, 'deity question'),
    (r'\b(god|goddess|deity|spirit)\b', 0.85, 'deity question'),

    # "What is X" (general knowledge)
    (r'^what\s+is\s+(?!there|in|at|on|the\s+best)', 0.8, 'what is question'),
    (r'^what\s+are\s+(?!there|the\s+sites|the\s+places)', 0.8, 'what are question'),

    # "Who" questions
    (r'^who\s+(was|were|is|are|built|created|discovered)', 0.9, 'who question'),

    # "When" questions about history
    (r'^when\s+(was|were|did|is)', 0.85, 'when question'),

    # "Why" questions
    (r'^why\s+(was|were|did|is|are)', 0.9, 'why question'),

    # "How" questions about history/process
    (r'^how\s+(was|were|did|old|many|long)', 0.85, 'how question'),

    # "Tell me about" / "Explain"
    (r'^tell\s+me\s+about\s+(?!sites|places|temples)', 0.85, 'tell me about'),
    (r'^explain\s+', 0.9, 'explanation request'),
    (r'^describe\s+(?!the\s+sites)', 0.85, 'description request'),

    # History/origin questions
    (r'history\s+of\s+', 0.85, 'history question'),
    (r'origin\s+of\s+', 0.9, 'origin question'),
    (r'etymology', 0.95, 'etymology question'),

    # Simple greetings
    (r'^(hi|hello|hey|greetings)[\s\!\?\.]?$', 0.99, 'greeting'),
    (r'^(thanks|thank\s+you|bye|goodbye)', 0.99, 'farewell'),
]

# Patterns that indicate DATABASE questions (search required)
DATABASE_PATTERNS = [
    # "Find" / "Show" / "Search" commands
    (r'^(find|show|search|locate|list|display)\s+', 0.95, 'search command'),
    (r'^(give\s+me|get\s+me)\s+', 0.9, 'retrieval request'),

    # "Are there any" questions
    (r'^are\s+there\s+(any|some)', 0.95, 'existence query'),
    (r'^is\s+there\s+(a|an|any)', 0.95, 'existence query'),

    # Location-specific queries
    (r'\s+in\s+(europe|asia|africa|america|greece|italy|egypt|peru|mexico|china|india|france|spain|england|uk|germany)', 0.85, 'location filter'),
    (r'(near|around|close\s+to|within)\s+\d+', 0.9, 'proximity query'),

    # Type-specific queries
    (r'(temples?|churches?|castles?|forts?|tombs?|pyramids?|monuments?|ruins?|caves?|megaliths?)', 0.7, 'site type mentioned'),

    # Period-specific queries
    (r'(roman|greek|egyptian|medieval|bronze\s+age|iron\s+age|neolithic|prehistoric|ancient|byzantine|viking|celtic|inca|maya|aztec)', 0.75, 'period mentioned'),
    (r'(before|after|during)\s+\d+\s*(bc|ad|bce|ce)', 0.9, 'date filter'),
    (r'older\s+than\s+\d+', 0.9, 'age filter'),

    # Highlight/map requests
    (r'(highlight|mark|pin|show\s+on\s+map)', 0.95, 'highlight request'),

    # "Where" with location intent
    (r'^where\s+(can\s+i\s+find|are\s+the|is\s+the)', 0.85, 'location query'),

    # Counting queries
    (r'^how\s+many\s+(sites?|temples?|churches?|monuments?)', 0.9, 'counting query'),

    # Comparison queries
    (r'(compare|similar\s+to|like)\s+', 0.8, 'comparison query'),
]

# Patterns that indicate SUPERLATIVE queries (only highlight top result)
SUPERLATIVE_PATTERNS = [
    r'\b(oldest|youngest|newest|earliest|latest|first|last)\b',
    r'\b(largest|biggest|smallest|tallest|highest|lowest|deepest)\b',
    r'\b(most\s+\w+|least\s+\w+)\b',
    r'\bthe\s+(\w+est)\b',  # "the oldest", "the biggest"
    r'\b(best|worst|top|greatest|number\s+one|#1)\b',
]


def classify_query(query: str) -> ClassificationResult:
    """
    Classify a user query as KNOWLEDGE or DATABASE type.

    Args:
        query: The user's question/request

    Returns:
        ClassificationResult with type, confidence, and reason
    """
    query_lower = query.lower().strip()

    # Check for empty or very short queries
    if len(query_lower) < 3:
        return ClassificationResult(
            query_type=QueryType.KNOWLEDGE,
            confidence=0.99,
            reason="too short for database query"
        )

    # Score for each type
    knowledge_score = 0.0
    knowledge_reason = ""
    database_score = 0.0
    database_reason = ""
    search_hint = None

    # Check for superlative queries (oldest, largest, etc.)
    is_superlative = any(re.search(pattern, query_lower) for pattern in SUPERLATIVE_PATTERNS)

    # Check KNOWLEDGE patterns
    for pattern, weight, reason in KNOWLEDGE_PATTERNS:
        if re.search(pattern, query_lower):
            if weight > knowledge_score:
                knowledge_score = weight
                knowledge_reason = reason

    # Check DATABASE patterns
    for pattern, weight, reason in DATABASE_PATTERNS:
        match = re.search(pattern, query_lower)
        if match:
            if weight > database_score:
                database_score = weight
                database_reason = reason
            # Extract search hint for certain patterns
            if 'site type' in reason or 'period' in reason:
                search_hint = match.group(0)

    # Decision logic
    # If both scores are similar, prefer DATABASE (more useful for this app)
    if database_score > knowledge_score + 0.1:
        return ClassificationResult(
            query_type=QueryType.DATABASE,
            confidence=database_score,
            reason=database_reason,
            search_hint=search_hint,
            is_superlative=is_superlative
        )
    elif knowledge_score > database_score:
        return ClassificationResult(
            query_type=QueryType.KNOWLEDGE,
            confidence=knowledge_score,
            reason=knowledge_reason,
            is_superlative=is_superlative
        )
    else:
        # Ambiguous - check for specific site names that might need lookup
        # If query mentions a specific place name, lean towards DATABASE
        proper_noun_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
        proper_nouns = re.findall(proper_noun_pattern, query)

        if proper_nouns and len(proper_nouns[0]) > 3:
            # Has proper nouns - might be asking about a specific site
            # But "What is Stonehenge" should be KNOWLEDGE
            if any(p in query_lower for p in ['what is', 'what does', 'tell me about', 'who', 'when', 'why']):
                return ClassificationResult(
                    query_type=QueryType.KNOWLEDGE,
                    confidence=0.7,
                    reason="knowledge question about specific place",
                    is_superlative=is_superlative
                )
            else:
                return ClassificationResult(
                    query_type=QueryType.DATABASE,
                    confidence=0.6,
                    reason="mentions specific place name",
                    search_hint=proper_nouns[0],
                    is_superlative=is_superlative
                )

        # Default to KNOWLEDGE for ambiguous short queries
        if len(query_lower.split()) <= 4:
            return ClassificationResult(
                query_type=QueryType.KNOWLEDGE,
                confidence=0.5,
                reason="short ambiguous query",
                is_superlative=is_superlative
            )

        # Default to DATABASE for longer queries
        return ClassificationResult(
            query_type=QueryType.DATABASE,
            confidence=0.5,
            reason="ambiguous, defaulting to search",
            is_superlative=is_superlative
        )


def get_status_message(query_type: QueryType, classification: ClassificationResult) -> str:
    """
    Generate a user-friendly status message for the query type.

    Args:
        query_type: The classified query type
        classification: The full classification result

    Returns:
        A message to show the user
    """
    if query_type == QueryType.KNOWLEDGE:
        return None  # No status needed for quick knowledge answers
    else:
        return "Searching archaeological database..."
