"""
RAG (Retrieval-Augmented Generation) Service.

Orchestrates the full RAG pipeline:
1. Parse user query to extract intent and filters
2. Search vector store for relevant sites
3. Fetch full site details from PostgreSQL
4. Build context within token limits
5. Generate response (template-based or LLM)
6. Parse response to extract site IDs for highlighting
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, AsyncGenerator

from .query_parser import QueryParser, QueryIntent
from .vector_store import VectorStore, get_vector_store
from .query_classifier import classify_query, QueryType, ClassificationResult
from .web_search import WebSearchService, get_web_search_service

# LLM is optional - we can work without it
try:
    from .llm_service import LLMService, get_llm_service
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class SiteHighlight:
    """A site to be highlighted on the map."""
    id: str
    name: str
    lat: float
    lon: float
    site_type: Optional[str] = None
    period_name: Optional[str] = None


@dataclass
class RAGResponse:
    """Response from RAG pipeline."""
    text: str
    sites: list[SiteHighlight] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# System prompt for the LLM - defines Lyra's persona and behavior
SYSTEM_PROMPT = """You are Lyra, an AI archaeology assistant for Ancient Nerds Map.

CRITICAL RULES:
1. TRUST THE DATA: When site data is provided, it is THE authoritative source. Never contradict it.
2. BE PRECISE: Count exactly how many sites match the criteria. Say "Found 5 temples" not "several temples".
3. USE THE DATA: Reference specific site names, dates, and locations from the provided list.
4. ADMIT LIMITS: If data is truncated, acknowledge "showing top N of M results".

FORMAT:
- Be concise and factual - no fluff or marketing language
- No emojis or promotional text
- List specific site names when answering
- Include dates/periods when relevant

DATES: Negative numbers = BC (e.g., -3000 means 3000 BC). When asked about sites "older than X", check period_start values."""


USER_PROMPT_TEMPLATE = """{query}"""


class RAGService:
    """
    Core RAG orchestration service.

    Flow:
    1. Parse user query to extract intent (filters, search terms)
    2. Search vector store for semantically similar sites
    3. Fetch full site details from PostgreSQL
    4. Build context (respecting token limits)
    5. Generate response (template-based or LLM)
    6. Parse response to extract site IDs for highlighting
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        llm_service = None
    ):
        self.query_parser = QueryParser()
        self._vector_store = vector_store
        self._llm_service = llm_service
        self._web_search = None
        self._use_llm = LLM_AVAILABLE

    @property
    def vector_store(self) -> VectorStore:
        if self._vector_store is None:
            self._vector_store = get_vector_store()
        return self._vector_store

    @property
    def llm_service(self):
        if not LLM_AVAILABLE:
            return None
        if self._llm_service is None:
            self._llm_service = get_llm_service()
        return self._llm_service

    @property
    def web_search(self) -> WebSearchService:
        if self._web_search is None:
            self._web_search = get_web_search_service()
        return self._web_search

    def _is_knowledge_question(self, query: str) -> bool:
        """Check if query is asking for knowledge rather than searching for sites."""
        query_lower = query.lower().strip()
        knowledge_patterns = [
            r'^what (does|is|was|were|are)',
            r'^who (was|were|is|are|built|created)',
            r'^when (was|were|did)',
            r'^where (is|was|were)',
            r'^why (was|were|did|is)',
            r'^how (was|were|did|old|many)',
            r'^tell me about',
            r'^explain',
            r'^describe',
            r'mean\??$',
            r'meaning\??$',
            r'history of',
            r'origin of',
        ]
        for pattern in knowledge_patterns:
            if re.search(pattern, query_lower):
                return True
        return False

    def _generate_template_response(self, sites: list[dict], intent: QueryIntent) -> str:
        """Generate a response without LLM using templates."""
        # Check if this is a knowledge question
        if self._is_knowledge_question(intent.original_query):
            if sites:
                # We found related sites but can't answer the knowledge question
                site_name = sites[0].get('name', 'this site')
                return f"I found **{site_name}** in the database, but I need a language model to answer questions about meanings, history, or explanations. Try asking me to 'show' or 'find' sites instead!\n\nFor example: 'Show me {site_name}' or 'Find sites like {site_name}'"
            else:
                return "I'm a site search assistant - I can help you find and explore archaeological sites, but I need a language model to answer knowledge questions. Try asking me to 'find', 'show', or 'search for' specific sites!"

        if not sites:
            return "I couldn't find any archaeological sites matching your query. Try:\n• Using different keywords\n• Broadening your search area\n• Checking spelling of site names"

        # Build response parts
        count = len(sites)

        # Describe what was found
        type_counts = {}
        countries = set()
        for s in sites:
            st = s.get("site_type", "site")
            type_counts[st] = type_counts.get(st, 0) + 1
            if s.get("country"):
                countries.add(s["country"])

        # Format type summary
        type_summary = ", ".join([f"{v} {k}{'s' if v > 1 else ''}" for k, v in sorted(type_counts.items(), key=lambda x: -x[1])[:5]])

        # Format location summary
        if len(countries) == 1:
            location_str = f"in {list(countries)[0]}"
        elif len(countries) <= 5:
            location_str = f"across {', '.join(sorted(countries))}"
        else:
            location_str = f"across {len(countries)} countries"

        # Build main response
        response = f"I found {count} archaeological site{'s' if count > 1 else ''}: {type_summary} {location_str}.\n\n"

        # Add highlights
        response += "Notable sites:\n"
        for i, site in enumerate(sites[:5], 1):
            period_info = f" ({site.get('period_name')})" if site.get('period_name') and site.get('period_name') != 'Unknown period' else ""
            country_info = f" in {site.get('country')}" if site.get('country') and site.get('country') != 'Unknown' else ""
            response += f"\n• **{site['name']}** - {site.get('site_type', 'site')}{period_info}{country_info}"

        if count > 5:
            response += f"\n\n...and {count - 5} more. Click 'Highlight on Map' to see them all!"
        else:
            response += "\n\nClick 'Highlight on Map' to see them on the globe!"

        return response

    async def process_query(
        self,
        query: str,
        max_sites: int = 50,
        include_site_details: bool = True
    ) -> RAGResponse:
        """
        Process a user query through the RAG pipeline.

        Args:
            query: Natural language query
            max_sites: Maximum number of sites to retrieve
            include_site_details: Whether to fetch full details from DB

        Returns:
            RAGResponse with text and highlighted sites
        """
        # 1. Parse query
        intent = self.query_parser.parse(query)
        logger.info(f"Parsed query intent: filters={intent.filters}, types={intent.site_types}")

        # 2. Search vector store
        search_query = self._build_search_query(intent)
        search_results = self.vector_store.search(
            query=search_query,
            filters=intent.filters,
            limit=max_sites
        )
        logger.info(f"Vector search returned {len(search_results)} results")

        # 3. Fetch full site details if requested
        if include_site_details and search_results:
            site_details = await self._fetch_site_details(
                [r.site_id for r in search_results]
            )
        else:
            # Use data from vector store SearchResult
            site_details = [
                {
                    "id": r.site_id,
                    "name": r.name or "Unknown",
                    "site_type": r.site_type or "Unknown",
                    "period_name": r.period_name or "Unknown",
                    "lat": r.lat or 0,
                    "lon": r.lon or 0,
                    "country": r.country or "Unknown",
                    "description": (r.description or "")[:200]
                }
                for r in search_results
            ]

        # 4. Build context
        context = self._build_simple_context(site_details, max_tokens=2500)

        # Log what we're sending
        logger.info(f"=== PROCESS_QUERY DEBUG ===")
        logger.info(f"Query: {query}")
        logger.info(f"Sites found: {len(site_details)}")
        logger.info(f"First 3: {[s.get('name') for s in site_details[:3]]}")

        # 5. Generate response with context in the prompt
        prompt = f"""ARCHAEOLOGICAL DATABASE RESULTS
================================
Total sites found: {len(site_details)}

{context}

================================
IMPORTANT INSTRUCTIONS:
1. You MUST answer using ONLY the sites listed above
2. Do NOT mention ANY sites that are not in this list
3. If the listed sites don't match the question well, say "The search returned these related sites:" and describe them
4. NEVER invent or recall sites from memory - ONLY use the numbered list above

USER QUESTION: {query}"""

        response_text = await self.llm_service.generate_async(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=500
        )

        # 6. Parse response for site highlights
        highlighted_sites = self._extract_highlighted_sites(response_text, site_details)

        # If user wanted highlights but none were explicitly listed, include all relevant
        if intent.wants_highlight and not highlighted_sites and site_details:
            highlighted_sites = [
                SiteHighlight(
                    id=s["id"],
                    name=s["name"],
                    lat=s["lat"],
                    lon=s["lon"],
                    site_type=s.get("site_type"),
                    period_name=s.get("period_name")
                )
                for s in site_details[:20]  # Limit to 20 for map clarity
            ]

        # Clean response text (remove [SITES:...] tags)
        clean_text = re.sub(r'\[SITES:[^\]]*\]', '', response_text).strip()

        return RAGResponse(
            text=clean_text,
            sites=highlighted_sites,
            metadata={
                "query_intent": {
                    "filters": intent.filters,
                    "site_types": intent.site_types,
                    "period": intent.period_name,
                    "region": intent.region_name
                },
                "sites_searched": len(search_results),
                "sites_returned": len(highlighted_sites)
            }
        )

    async def process_query_stream(
        self,
        query: str,
        max_sites: int = 50,
        source_ids: Optional[list[str]] = None,
        conversation_history: Optional[list[dict]] = None,
        model_override: Optional[str] = None,
        max_tokens: int = 200
    ) -> AsyncGenerator[dict, None]:
        """
        Process query with streaming response using intelligent routing.

        Routes queries as:
        - KNOWLEDGE: Direct LLM answer (fast, ~10s)
        - DATABASE: Search + LLM with context

        Yields dicts with:
        - {"type": "status", "message": "..."} - Status update
        - {"type": "token", "content": "..."} - Response token
        - {"type": "sites", "sites": [...]} - Sites to highlight
        - {"type": "done", "metadata": {...}} - Completion
        """
        # Apply model override if specified
        original_model = None
        if model_override and self.llm_service:
            original_model = self.llm_service.model
            self.llm_service.model = model_override
            logger.info(f"Using model override: {model_override}")

        # Default to ancient_nerds source for quality results
        if source_ids is None:
            source_ids = ["ancient_nerds"]

        # Build context from conversation history
        history_context = ""
        if conversation_history:
            history_context = "PREVIOUS CONVERSATION:\n"
            for msg in conversation_history[-5:]:  # Last 5 messages
                role = "User" if msg["role"] == "user" else "Lyra"
                history_context += f"{role}: {msg['content']}\n"
            history_context += "\n"

        # NEW: Augment query with context if needed (LLM-assisted)
        # This resolves references like "show me on the map" → "Gate of the Sun"
        augmented_query, resolved_site = await self._augment_query_with_context(
            query, conversation_history, max_history=10
        )
        if resolved_site:
            logger.info(f"Context resolved: '{query}' references '{resolved_site}'")

        # 1. CLASSIFY the query (use augmented if we resolved a site)
        effective_query = augmented_query if resolved_site else query
        classification = classify_query(effective_query)
        logger.info(f"Query classified as {classification.query_type.value}: {classification.reason}")

        site_details = []
        search_results = []

        # 2. Route based on classification
        if classification.query_type == QueryType.KNOWLEDGE:
            # KNOWLEDGE: Answer directly with LLM, no database search
            logger.info("Routing to direct LLM answer (no database)")
            full_response = await self._generate_knowledge_answer(query, history_context)

        else:
            # DATABASE: Full RAG pipeline
            yield {"type": "status", "message": "Searching archaeological database..."}

            # Parse query for filters (use effective_query to include resolved site name)
            intent = self.query_parser.parse(effective_query)

            # Determine which sources to search
            # Priority: explicit parameter wins (user explicitly passed sources in URL)
            # The source_ids from URL should NOT be overridden by query parsing
            effective_sources = source_ids

            # Check if this is a feature proximity search (e.g., "sites near volcanos")
            if intent.feature_type:
                yield {"type": "status", "message": f"Finding sites near {intent.feature_type}s..."}
                search_results = self.vector_store.search_near_feature(
                    feature_type=intent.feature_type,
                    sources=effective_sources,
                    radius_km=intent.feature_radius_km,
                    limit=max_sites,
                )
            else:
                # Regular semantic search
                # Use resolved site name directly if available, otherwise build from intent
                if resolved_site:
                    search_query = resolved_site
                    logger.info(f"Using resolved site for search: '{search_query}'")
                else:
                    search_query = self._build_search_query(intent)

                search_results = self.vector_store.search(
                    query=search_query,
                    sources=effective_sources,
                    filters=intent.filters,
                    limit=max_sites,
                )
                logger.info(f"Vector search returned {len(search_results)} results")

            # Fetch site details
            site_details = await self._fetch_site_details(
                [r.site_id for r in search_results]
            )

            if site_details:
                yield {"type": "status", "message": f"Found {len(site_details)} sites, generating response..."}

            # Generate response with context
            full_response = await self._generate_database_answer(query, site_details, history_context)

        # 3. Stream the response
        for token in self._stream_response(full_response):
            yield {"type": "token", "content": token}

        # 4. Yield sites if we have them
        if site_details:
            # For superlative queries (oldest, largest, etc.), only highlight top result(s)
            # Otherwise highlight up to 20 sites
            highlight_limit = 3 if classification.is_superlative else 20

            highlighted_sites = [
                SiteHighlight(
                    id=s["id"],
                    name=s["name"],
                    lat=s["lat"],
                    lon=s["lon"],
                    site_type=s.get("site_type"),
                    period_name=s.get("period_name")
                )
                for s in site_details[:highlight_limit]
            ]

            if highlighted_sites:
                yield {
                    "type": "sites",
                    "sites": [
                        {"id": s.id, "name": s.name, "lat": s.lat, "lon": s.lon}
                        for s in highlighted_sites
                    ]
                }

        # 5. Done - restore model and yield completion
        if original_model and self.llm_service:
            self.llm_service.model = original_model
            logger.info(f"Restored model to: {original_model}")

        yield {
            "type": "done",
            "metadata": {
                "query_type": classification.query_type.value,
                "sites_searched": len(search_results),
                "sites_returned": len(site_details)
            }
        }

    async def _generate_knowledge_answer(self, query: str, history_context: str = "") -> str:
        """Generate a knowledge answer using web search + LLM for grounding."""
        if self.llm_service is None:
            return "I need a language model to answer knowledge questions."

        # Try web search first for grounding (prevents hallucination)
        web_results = await self.web_search.search_archaeology(query)

        if web_results["success"] and web_results["results"]:
            web_context = self.web_search.format_for_context(web_results["results"])
            source = web_results.get("source", "web")

            prompt = f"""{history_context}Based on these {source} search results:

{web_context}

CURRENT QUESTION: {query}

Provide a concise, factual answer. If citing information, mention the source."""

            try:
                response = await self.llm_service.generate_async(
                    prompt=prompt,
                    system_prompt=SYSTEM_PROMPT,
                    max_tokens=250
                )
                return self._clean_response(response)
            except Exception as e:
                logger.error(f"LLM error with web context: {e}")

        # Fallback to direct LLM (warn about potential hallucination)
        prompt = f"{history_context}CURRENT QUESTION: {query}" if history_context else query

        try:
            response = await self.llm_service.generate_async(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT + "\n\nIMPORTANT: Only answer if confident. Otherwise say you don't have reliable information.",
                max_tokens=150
            )
            return self._clean_response(response)
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return "Sorry, I couldn't process that question. Please try again."

    async def _generate_database_answer(self, query: str, sites: list[dict], history_context: str = "") -> str:
        """Generate an answer using database context."""
        if not sites:
            return "I couldn't find any sites matching your query. Try different keywords or filters."

        if self.llm_service is None:
            # Template response without LLM
            intent = self.query_parser.parse(query)
            return self._generate_template_response(sites, intent)

        # Build context from ALL sites (token-aware truncation handles limits)
        context = self._build_simple_context(sites)  # Pass ALL sites, not [:10]

        # Log what we're sending to LLM for debugging
        logger.info(f"=== LLM CONTEXT DEBUG ===")
        logger.info(f"Query: {query}")
        logger.info(f"Sites passed: {len(sites)}")
        logger.info(f"First 3 sites: {[s.get('name', 'Unknown') for s in sites[:3]]}")
        logger.info(f"Context preview (first 500 chars): {context[:500]}")

        prompt = f"""{history_context}ARCHAEOLOGICAL DATABASE RESULTS
================================
Total sites found: {len(sites)}

{context}

================================
IMPORTANT INSTRUCTIONS:
1. You MUST answer using ONLY the sites listed above
2. Do NOT mention ANY sites that are not in this list
3. If the listed sites don't match the question well, say "The search returned these related sites:" and describe them
4. NEVER invent or recall sites from memory - ONLY use the numbered list above

USER QUESTION: {query}"""

        try:
            response = await self.llm_service.generate_async(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=200
            )
            logger.info(f"LLM Response: {response[:200]}...")
            return self._clean_response(response)
        except Exception as e:
            logger.error(f"LLM error: {e}")
            # Fallback to template
            intent = self.query_parser.parse(query)
            return self._generate_template_response(sites, intent)

    def _build_simple_context(self, sites: list[dict], max_tokens: int = 2500) -> str:
        """Build context with ALL sites, respecting token limits."""
        lines = []
        estimated_tokens = 0
        total_sites = len(sites)

        for i, s in enumerate(sites, 1):
            # Build site line with period dates (CRITICAL for time queries)
            period = s.get("period_name", "Unknown")
            period_start = s.get("period_start")
            if period_start is not None:
                # Show BC/AD properly
                if period_start < 0:
                    period += f" (from {abs(period_start)} BC)"
                else:
                    period += f" (from {period_start} AD)"

            line = f"{i}. {s.get('name', 'Unknown')}: {s.get('site_type', 'site')}, {period}, {s.get('country', '')}"
            line_tokens = len(line.split()) + 5  # Rough estimate

            if estimated_tokens + line_tokens > max_tokens:
                remaining = total_sites - i + 1
                lines.append(f"... and {remaining} more sites (truncated for length)")
                break

            lines.append(line)
            estimated_tokens += line_tokens

        return "\n".join(lines)

    def _clean_response(self, response: str) -> str:
        """Clean LLM response of garbage patterns."""
        # Remove garbage patterns
        garbage_patterns = [r'\[SITES?:[^\]]*\]', r'\(ID:[^\)]*\)', r'\[/SITES[^\]]*\]']
        for pattern in garbage_patterns:
            response = re.sub(pattern, '', response, flags=re.IGNORECASE)

        # Truncate at repetition
        words = response.split()
        if len(words) > 10:
            for i in range(10, len(words)):
                if words[i-4:i] == words[i:i+4]:
                    response = ' '.join(words[:i])
                    break

        return response.strip()

    async def _quick_llm_call(self, prompt: str) -> str:
        """
        Make a fast LLM call for simple classification tasks.
        Uses lower max_tokens and temperature for speed.
        """
        if self.llm_service is None:
            return "NO_REFERENCE"

        try:
            response = await self.llm_service.generate_async(
                prompt=prompt,
                max_tokens=50,  # Very short response needed
                temperature=0.0  # Deterministic
            )
            return response.strip()
        except Exception as e:
            logger.warning(f"Quick LLM call failed: {e}")
            return "NO_REFERENCE"

    async def _augment_query_with_context(
        self,
        query: str,
        conversation_history: Optional[list[dict]],
        max_history: int = 10
    ) -> tuple[str, Optional[str]]:
        """
        Use LLM to determine if query references conversation context.

        Returns:
            tuple: (augmented_query, extracted_site_name or None)

        If the query is self-contained (like "thanks" or "show me temples in Greece"),
        returns the original query unchanged.

        If the query references context (like "show me on the map" after discussing
        a specific site), returns an augmented query with the site name.
        """
        if not conversation_history:
            return query, None

        # Skip if there's no assistant message in history (nothing to reference)
        has_assistant_msg = any(msg.get("role") == "assistant" for msg in conversation_history)
        if not has_assistant_msg:
            return query, None

        # Skip augmentation for clearly self-contained queries
        query_lower = query.lower().strip()
        if len(query.split()) > 8:
            return query, None  # Long queries are usually self-contained

        # Skip for greetings, thanks, and other non-site phrases
        non_site_phrases = ['thanks', 'thank you', 'ok', 'okay', 'cool', 'great',
                           'hello', 'hi', 'hey', 'bye', 'goodbye', 'yes', 'no',
                           'sure', 'got it', 'understood', 'nice', 'awesome']
        if query_lower in non_site_phrases or any(query_lower.startswith(p) for p in ['thanks', 'thank']):
            return query, None

        # Skip if query explicitly mentions site types (self-contained search)
        site_keywords = ['temple', 'church', 'castle', 'fort', 'tomb', 'pyramid',
                        'monument', 'ruin', 'megalith', 'dolmen', 'menhir', 'site']
        if any(word in query_lower for word in site_keywords):
            return query, None

        # Only process last N messages for context
        recent_history = conversation_history[-max_history:]

        # Build context summary for the LLM
        context_lines = []
        for msg in recent_history:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "")[:400]  # Truncate for speed
            context_lines.append(f"{role}: {content}")
        context_text = "\n".join(context_lines)

        # Quick LLM call to determine if query needs context
        # Extract last assistant message for context
        last_assistant_msg = ""
        for msg in reversed(recent_history):
            if msg.get("role") == "assistant":
                last_assistant_msg = msg.get("content", "")[:300]
                break

        resolution_prompt = f"""I just told the user about: {last_assistant_msg}

User now says: "{query}"

What archaeological site is the user asking about? Just give the site name, nothing else.
If the user is NOT asking about a site (like saying "thanks" or asking a new question), say NO_REFERENCE.

Site name:"""

        response = await self._quick_llm_call(resolution_prompt)
        response = response.strip().strip('"\'')

        # Parse response - take first line only, ignore if it says NO_REFERENCE
        first_line = response.split('\n')[0].strip()

        # Check if LLM found a reference
        if not first_line or "NO_REFERENCE" in first_line.upper() or first_line.upper() == "NO":
            return query, None

        # LLM found a site reference
        site_name = first_line
        augmented_query = site_name  # Use site name as the search query

        logger.info(f"Context resolved: '{query}' → '{site_name}'")
        return augmented_query, site_name

    def _stream_response(self, response: str):
        """Yield response word by word for streaming effect."""
        words = response.split()
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")

    def _build_search_query(self, intent: QueryIntent) -> str:
        """Build a search query string from parsed intent."""
        parts = []

        # Add search terms
        if intent.search_terms:
            parts.extend(intent.search_terms)

        # Add site types as keywords
        if intent.site_types:
            parts.extend(intent.site_types[:3])  # Limit to avoid over-specification

        # Add period name
        if intent.period_name:
            parts.append(intent.period_name)

        # Add region
        if intent.region_name:
            parts.append(intent.region_name)

        # Fall back to original query if no parts extracted
        if not parts:
            return intent.original_query

        return " ".join(parts)

    async def _fetch_site_details(self, site_ids: list[str]) -> list[dict]:
        """
        Fetch full site details from PostgreSQL.

        Args:
            site_ids: List of site IDs to fetch

        Returns:
            List of site detail dicts
        """
        if not site_ids:
            return []

        try:
            from pipeline.database import get_session
            from sqlalchemy import text

            with get_session() as session:
                # Fetch sites
                placeholders = ", ".join([f":id{i}" for i in range(len(site_ids))])
                params = {f"id{i}": sid for i, sid in enumerate(site_ids)}

                result = session.execute(text(f"""
                    SELECT
                        id::text,
                        name,
                        site_type,
                        period_start,
                        period_end,
                        period_name,
                        country,
                        description,
                        lat,
                        lon,
                        source_id
                    FROM unified_sites
                    WHERE id::text IN ({placeholders})
                """), params)

                sites = []
                for row in result:
                    sites.append({
                        "id": row.id,
                        "name": row.name or "Unknown",
                        "site_type": row.site_type or "Unknown",
                        "period_start": row.period_start,
                        "period_end": row.period_end,
                        "period_name": row.period_name or "Unknown period",
                        "country": row.country or "Unknown",
                        "description": (row.description or "")[:500],
                        "lat": row.lat,
                        "lon": row.lon,
                        "source": row.source_id
                    })

                return sites

        except Exception as e:
            logger.error(f"Error fetching site details: {e}")
            return []

    def _extract_highlighted_sites(
        self,
        response: str,
        site_details: list[dict]
    ) -> list[SiteHighlight]:
        """
        Extract site IDs from [SITES: ...] tags in the response.

        Args:
            response: LLM response text
            site_details: Available site details to match against

        Returns:
            List of SiteHighlight objects
        """
        # Find [SITES: id1, id2, ...] pattern
        pattern = r'\[SITES:\s*([^\]]+)\]'
        matches = re.findall(pattern, response, re.IGNORECASE)

        if not matches:
            return []

        # Parse site IDs
        site_ids = set()
        for match in matches:
            ids = [s.strip() for s in match.split(",")]
            site_ids.update(ids)

        # Create site map for lookup
        site_map = {s["id"]: s for s in site_details}

        # Build highlights
        highlights = []
        for site_id in site_ids:
            if site_id in site_map:
                s = site_map[site_id]
                highlights.append(SiteHighlight(
                    id=s["id"],
                    name=s["name"],
                    lat=s["lat"],
                    lon=s["lon"],
                    site_type=s.get("site_type"),
                    period_name=s.get("period_name")
                ))

        return highlights

    def health_check(self) -> dict:
        """Check RAG service health."""
        vector_health = self.vector_store.health_check()
        llm_health = self.llm_service.health_check()

        overall_status = "healthy"
        if vector_health.get("status") != "healthy":
            overall_status = "degraded"
        if llm_health.get("status") in ("unhealthy", "error"):
            overall_status = "degraded"

        return {
            "status": overall_status,
            "vector_store": vector_health,
            "llm": llm_health
        }


# Singleton instance
_rag_service_instance: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get singleton RAGService instance."""
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RAGService()
    return _rag_service_instance
