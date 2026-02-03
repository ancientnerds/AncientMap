"""
Connector Registry - Central registration and discovery of content connectors.

Provides:
- Automatic connector registration via decorator
- Discovery by connector ID or content type
- Parallel search across multiple connectors
- Health checking and status reporting
"""

import asyncio
import time
from datetime import datetime

from loguru import logger

from pipeline.connectors.base import BaseConnector
from pipeline.connectors.types import (
    ConnectorStatus,
    ContentItem,
    ContentSearchResult,
    ContentType,
    QueryTestResult,
    SampleItem,
    SourceInfo,
)


class ConnectorRegistry:
    """
    Central registry for all content connectors.

    Usage:
        # Register a connector class
        @ConnectorRegistry.register
        class MyConnector(BaseConnector):
            connector_id = "my_source"
            ...

        # Get a connector instance
        connector = ConnectorRegistry.get("my_source")

        # Search across all connectors
        results = await ConnectorRegistry.search_all("roman temple")
    """

    # Class-level storage
    _connector_classes: dict[str, type[BaseConnector]] = {}
    _connector_instances: dict[str, BaseConnector] = {}
    _api_keys: dict[str, str] = {}  # connector_id -> api_key
    _connector_status: dict[str, ConnectorStatus] = {}  # cached status

    # SPARQL endpoints need longer timeouts (30s instead of 10s)
    SPARQL_CONNECTORS = {
        "british_museum", "british_museum_coins", "nomisma", "ans", "edh"
    }

    # Test queries for connector testing
    TEST_QUERIES = [
        ("machu_picchu", "Machu Picchu"),
        ("stonehenge", "Stonehenge"),
        ("great_sphinx", "Great Sphinx of Giza"),
        ("roman_empire", "Roman Empire"),
        ("inca_empire", "Inca Empire"),
        ("egyptian_empire", "Egyptian Empire"),
    ]

    @classmethod
    def register(cls, connector_class: type[BaseConnector]) -> type[BaseConnector]:
        """
        Register a connector class with the registry.

        Can be used as a decorator:
            @ConnectorRegistry.register
            class MyConnector(BaseConnector):
                ...
        """
        if not hasattr(connector_class, "connector_id") or not connector_class.connector_id:
            raise ValueError(
                f"Connector class {connector_class.__name__} must have connector_id set"
            )

        connector_id = connector_class.connector_id
        cls._connector_classes[connector_id] = connector_class
        logger.debug(f"Registered connector: {connector_id}")

        return connector_class

    @classmethod
    def set_api_key(cls, connector_id: str, api_key: str) -> None:
        """Set API key for a connector."""
        cls._api_keys[connector_id] = api_key

    @classmethod
    def set_api_keys(cls, api_keys: dict[str, str]) -> None:
        """Set multiple API keys at once."""
        cls._api_keys.update(api_keys)

    @classmethod
    def get(cls, connector_id: str) -> BaseConnector | None:
        """
        Get a connector instance by ID.

        Creates instance on first access (lazy instantiation).
        """
        # Return existing instance
        if connector_id in cls._connector_instances:
            return cls._connector_instances[connector_id]

        # Check if class is registered
        if connector_id not in cls._connector_classes:
            logger.warning(f"Unknown connector: {connector_id}")
            return None

        # Create instance
        connector_class = cls._connector_classes[connector_id]
        api_key = cls._api_keys.get(connector_id)

        try:
            instance = connector_class(api_key=api_key)
            cls._connector_instances[connector_id] = instance
            return instance
        except Exception as e:
            logger.error(f"Failed to create connector {connector_id}: {e}")
            return None

    @classmethod
    def get_all(cls, include_unavailable: bool = False) -> list[BaseConnector]:
        """Get all registered connector instances.

        Args:
            include_unavailable: If True, include connectors marked available=False
        """
        connectors = []
        for connector_id in cls._connector_classes:
            connector = cls.get(connector_id)
            if connector:
                if not include_unavailable and not getattr(connector, 'available', True):
                    continue
                connectors.append(connector)
        return connectors

    @classmethod
    def get_by_content_type(
        cls, content_type: ContentType, include_unavailable: bool = False
    ) -> list[BaseConnector]:
        """Get all connectors that provide a specific content type."""
        connectors = []
        for connector_id, connector_class in cls._connector_classes.items():
            if content_type in connector_class.content_types:
                connector = cls.get(connector_id)
                if connector:
                    if not include_unavailable and not getattr(connector, 'available', True):
                        continue
                    connectors.append(connector)
        return connectors

    @classmethod
    def get_registered_ids(cls) -> list[str]:
        """Get list of all registered connector IDs."""
        return list(cls._connector_classes.keys())

    @classmethod
    def list_sources(cls) -> list[SourceInfo]:
        """Get info about all registered sources."""
        sources = []
        for connector in cls.get_all(include_unavailable=True):
            sources.append(connector.get_source_info())
        return sources

    @classmethod
    async def search_all(
        cls,
        query: str,
        content_type: ContentType | None = None,
        sources: list[str] | None = None,
        limit_per_source: int = 10,
        timeout: float = 30.0,
    ) -> ContentSearchResult:
        """
        Search across all (or specified) connectors in parallel.

        Args:
            query: Search query
            content_type: Filter to connectors providing this type
            sources: List of connector IDs to search (None for all)
            limit_per_source: Max results per source
            timeout: Total timeout in seconds

        Returns:
            ContentSearchResult with aggregated items
        """
        start_time = datetime.utcnow()

        # Determine which connectors to search
        if sources:
            connectors = [cls.get(s) for s in sources]
            connectors = [c for c in connectors if c is not None]
        elif content_type:
            connectors = cls.get_by_content_type(content_type)
        else:
            connectors = cls.get_all()

        if not connectors:
            return ContentSearchResult(
                items=[],
                total_count=0,
                sources_searched=[],
                sources_failed=[],
                search_time_ms=0,
            )

        # Create search tasks
        async def search_connector(connector: BaseConnector) -> tuple:
            """Search a single connector and return (connector_id, items, error)."""
            try:
                items = await connector.search(
                    query=query,
                    content_type=content_type,
                    limit=limit_per_source,
                )
                return (connector.connector_id, items, None)
            except Exception as e:
                logger.warning(f"Search failed for {connector.connector_id}: {e}")
                return (connector.connector_id, [], str(e))

        # Run searches in parallel with timeout
        tasks = [search_connector(c) for c in connectors]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning(f"Search timed out after {timeout}s")
            results = []

        # Aggregate results
        all_items: list[ContentItem] = []
        sources_searched: list[str] = []
        sources_failed: list[str] = []
        items_by_source: dict[str, int] = {}

        for result in results:
            if isinstance(result, Exception):
                continue

            connector_id, items, error = result
            if error:
                sources_failed.append(connector_id)
                items_by_source[connector_id] = 0
            else:
                sources_searched.append(connector_id)
                items_by_source[connector_id] = len(items)
                all_items.extend(items)

        # Sort by relevance
        all_items.sort(key=lambda x: x.relevance_score, reverse=True)

        # Calculate timing
        end_time = datetime.utcnow()
        search_time_ms = (end_time - start_time).total_seconds() * 1000

        return ContentSearchResult(
            items=all_items,
            total_count=len(all_items),
            sources_searched=sources_searched,
            sources_failed=sources_failed,
            items_by_source=items_by_source,
            search_time_ms=search_time_ms,
        )

    @classmethod
    async def get_by_location_all(
        cls,
        lat: float,
        lon: float,
        radius_km: float = 50,
        content_type: ContentType | None = None,
        sources: list[str] | None = None,
        limit_per_source: int = 10,
        timeout: float = 30.0,
    ) -> ContentSearchResult:
        """
        Get content by location across all (or specified) connectors.

        Args:
            lat: Latitude
            lon: Longitude
            radius_km: Search radius
            content_type: Filter by content type
            sources: List of connector IDs
            limit_per_source: Max results per source
            timeout: Total timeout

        Returns:
            ContentSearchResult with aggregated items
        """
        start_time = datetime.utcnow()

        # Determine which connectors to query
        if sources:
            connectors = [cls.get(s) for s in sources]
            connectors = [c for c in connectors if c is not None]
        elif content_type:
            connectors = cls.get_by_content_type(content_type)
        else:
            connectors = cls.get_all()

        if not connectors:
            return ContentSearchResult()

        # Create tasks
        async def query_connector(connector: BaseConnector) -> tuple:
            try:
                items = await connector.get_by_location(
                    lat=lat,
                    lon=lon,
                    radius_km=radius_km,
                    content_type=content_type,
                    limit=limit_per_source,
                )
                return (connector.connector_id, items, None)
            except Exception as e:
                logger.warning(f"Location query failed for {connector.connector_id}: {e}")
                return (connector.connector_id, [], str(e))

        tasks = [query_connector(c) for c in connectors]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            results = []

        # Aggregate
        all_items: list[ContentItem] = []
        sources_searched: list[str] = []
        sources_failed: list[str] = []
        items_by_source: dict[str, int] = {}

        for result in results:
            if isinstance(result, Exception):
                continue
            connector_id, items, error = result
            if error:
                sources_failed.append(connector_id)
                items_by_source[connector_id] = 0
            else:
                sources_searched.append(connector_id)
                items_by_source[connector_id] = len(items)
                all_items.extend(items)

        all_items.sort(key=lambda x: x.relevance_score, reverse=True)

        end_time = datetime.utcnow()
        return ContentSearchResult(
            items=all_items,
            total_count=len(all_items),
            sources_searched=sources_searched,
            sources_failed=sources_failed,
            items_by_source=items_by_source,
            search_time_ms=(end_time - start_time).total_seconds() * 1000,
        )

    @classmethod
    async def get_for_site(
        cls,
        site_name: str,
        location: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        content_types: list[ContentType] | None = None,
        limit_per_source: int = 10,
        timeout: float = 30.0,
    ) -> ContentSearchResult:
        """
        Get all content related to an archaeological site.

        Args:
            site_name: Name of the site
            location: Location string for context
            lat: Latitude
            lon: Longitude
            content_types: Types of content to fetch
            limit_per_source: Max per source
            timeout: Total timeout

        Returns:
            ContentSearchResult with aggregated items
        """
        start_time = datetime.utcnow()

        # Get relevant connectors
        connectors = cls.get_all()

        if content_types:
            type_set: set[ContentType] = set(content_types)
            connectors = [
                c for c in connectors
                if any(ct in type_set for ct in c.content_types)
            ]

        if not connectors:
            return ContentSearchResult()

        # Query each connector
        async def query_connector(connector: BaseConnector) -> tuple:
            try:
                items = await connector.get_by_site(
                    site_name=site_name,
                    location=location,
                    lat=lat,
                    lon=lon,
                    limit=limit_per_source,
                )
                return (connector.connector_id, items, None)
            except Exception as e:
                logger.warning(f"Site query failed for {connector.connector_id}: {e}")
                return (connector.connector_id, [], str(e))

        tasks = [query_connector(c) for c in connectors]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            results = []

        # Aggregate
        all_items: list[ContentItem] = []
        sources_searched: list[str] = []
        sources_failed: list[str] = []
        items_by_source: dict[str, int] = {}

        for result in results:
            if isinstance(result, Exception):
                continue
            connector_id, items, error = result
            if error:
                sources_failed.append(connector_id)
                items_by_source[connector_id] = 0
            else:
                sources_searched.append(connector_id)
                items_by_source[connector_id] = len(items)
                all_items.extend(items)

        all_items.sort(key=lambda x: x.relevance_score, reverse=True)

        end_time = datetime.utcnow()
        return ContentSearchResult(
            items=all_items,
            total_count=len(all_items),
            sources_searched=sources_searched,
            sources_failed=sources_failed,
            items_by_source=items_by_source,
            search_time_ms=(end_time - start_time).total_seconds() * 1000,
        )

    @classmethod
    async def get_for_empire(
        cls,
        empire_name: str,
        period_name: str | None = None,
        content_types: list[ContentType] | None = None,
        limit_per_source: int = 10,
        timeout: float = 30.0,
    ) -> ContentSearchResult:
        """
        Get all content related to an empire/civilization.

        Args:
            empire_name: Name of the empire
            period_name: Specific period within empire
            content_types: Types of content to fetch
            limit_per_source: Max per source
            timeout: Total timeout

        Returns:
            ContentSearchResult with aggregated items
        """
        start_time = datetime.utcnow()

        connectors = cls.get_all()

        if content_types:
            type_set: set[ContentType] = set(content_types)
            connectors = [
                c for c in connectors
                if any(ct in type_set for ct in c.content_types)
            ]

        if not connectors:
            return ContentSearchResult()

        async def query_connector(connector: BaseConnector) -> tuple:
            try:
                items = await connector.get_by_empire(
                    empire_name=empire_name,
                    period_name=period_name,
                    limit=limit_per_source,
                )
                return (connector.connector_id, items, None)
            except Exception as e:
                logger.warning(f"Empire query failed for {connector.connector_id}: {e}")
                return (connector.connector_id, [], str(e))

        tasks = [query_connector(c) for c in connectors]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            results = []

        all_items: list[ContentItem] = []
        sources_searched: list[str] = []
        sources_failed: list[str] = []
        items_by_source: dict[str, int] = {}

        for result in results:
            if isinstance(result, Exception):
                continue
            connector_id, items, error = result
            if error:
                sources_failed.append(connector_id)
                items_by_source[connector_id] = 0
            else:
                sources_searched.append(connector_id)
                items_by_source[connector_id] = len(items)
                all_items.extend(items)

        all_items.sort(key=lambda x: x.relevance_score, reverse=True)

        end_time = datetime.utcnow()
        return ContentSearchResult(
            items=all_items,
            total_count=len(all_items),
            sources_searched=sources_searched,
            sources_failed=sources_failed,
            items_by_source=items_by_source,
            search_time_ms=(end_time - start_time).total_seconds() * 1000,
        )

    @classmethod
    def _get_connector_category(cls, connector: BaseConnector) -> str:
        """Determine category for a connector based on its content types and module path."""
        content_types = connector.content_types

        # Get module path for fallback categorization
        module = connector.__class__.__module__

        # Check module path first for clear categorization
        if ".museums." in module:
            return "museums"
        if ".sites." in module:
            return "sites"
        if ".papers." in module:
            return "papers"
        if ".texts." in module:
            return "texts"
        if ".imagery." in module:
            return "images"
        if ".maps." in module:
            return "maps"
        if ".models3d." in module:
            return "3d_models"
        if ".inscriptions." in module:
            return "inscriptions"
        if ".numismatics." in module:
            return "numismatics"
        if ".vocabularies." in module:
            return "reference"

        # Fallback to content type based categorization
        if not content_types:
            return "other"

        type_values = {ct.value if hasattr(ct, 'value') else str(ct) for ct in content_types}

        if "model_3d" in type_values:
            return "3d_models"
        if "coin" in type_values:
            return "numismatics"
        if "artifact" in type_values:
            return "museums"
        if "map" in type_values:
            return "maps"
        if "paper" in type_values:
            return "papers"
        if "photo" in type_values or "artwork" in type_values:
            return "images"
        if "place" in type_values:
            return "sites"
        if "inscription" in type_values or "primary_text" in type_values:
            return "inscriptions"
        if "book" in type_values or "manuscript" in type_values:
            return "texts"
        if "document" in type_values:
            return "sites"

        return "other"

    @classmethod
    def _get_connector_tabs(cls, connector: BaseConnector) -> list[str]:
        """Determine which UI tabs a connector populates based on its content types."""
        TAB_MAPPING = {
            'photo': 'Photos',
            'artwork': 'Artworks',
            'map': 'Maps',
            'model_3d': '3D',
            'artifact': 'Artifacts',
            'coin': 'Artifacts',
            'inscription': 'Books',
            'primary_text': 'Books',
            'manuscript': 'Books',
            'book': 'Books',
            'paper': 'Books',
            'document': 'Books',
        }

        content_types = connector.content_types
        if not content_types:
            return []

        tabs = set()
        for ct in content_types:
            ct_value = ct.value if hasattr(ct, 'value') else str(ct)
            if ct_value in TAB_MAPPING:
                tabs.add(TAB_MAPPING[ct_value])

        return sorted(tabs)

    @classmethod
    async def check_connector_status(
        cls,
        connector_id: str,
        timeout: float = 10.0,
    ) -> ConnectorStatus:
        """
        Check status of a single connector by performing a health check.

        Args:
            connector_id: ID of the connector to check
            timeout: Timeout for the health check

        Returns:
            ConnectorStatus with current status
        """
        connector = cls.get(connector_id)
        if not connector:
            return ConnectorStatus(
                connector_id=connector_id,
                connector_name=connector_id,
                category="unknown",
                status="error",
                available=False,
                error_message=f"Unknown connector: {connector_id}",
            )

        # Check if connector is marked as unavailable
        if hasattr(connector, 'available') and not connector.available:
            reason = getattr(connector, 'unavailable_reason', None) or "Service unavailable"
            connector_status = ConnectorStatus(
                connector_id=connector.connector_id,
                connector_name=connector.connector_name,
                category=cls._get_connector_category(connector),
                status="unavailable",
                available=False,
                base_url=getattr(connector, 'website_url', None) or getattr(connector, 'base_url', None),
                last_ping=datetime.utcnow(),
                error_message=reason,
                response_time_ms=0,
                tabs=cls._get_connector_tabs(connector),
            )
            cls._connector_status[connector_id] = connector_status
            return connector_status

        # Use longer timeout for SPARQL endpoints
        effective_timeout = 30.0 if connector_id in cls.SPARQL_CONNECTORS else timeout

        try:
            result = await asyncio.wait_for(
                connector.health_check(),
                timeout=effective_timeout,
            )

            # Handle unavailable status from health_check
            if result.status == "unavailable":
                connector_status = ConnectorStatus(
                    connector_id=connector.connector_id,
                    connector_name=connector.connector_name,
                    category=cls._get_connector_category(connector),
                    status="unavailable",
                    available=False,
                    base_url=getattr(connector, 'website_url', None) or getattr(connector, 'base_url', None),
                    last_ping=datetime.utcnow(),
                    error_message=result.error_message,
                    response_time_ms=result.response_time_ms,
                    tabs=cls._get_connector_tabs(connector),
                )
                cls._connector_status[connector_id] = connector_status
                return connector_status

            # Determine status based on response time
            status = result.status
            if status == "ok" and result.response_time_ms > 5000:
                status = "warning"  # Slow response

            connector_status = ConnectorStatus(
                connector_id=connector.connector_id,
                connector_name=connector.connector_name,
                category=cls._get_connector_category(connector),
                status=status,
                available=True,
                base_url=getattr(connector, 'website_url', None) or getattr(connector, 'base_url', None),
                last_ping=datetime.utcnow(),
                error_message=result.error_message,
                item_count=result.item_count,
                response_time_ms=result.response_time_ms,
                tabs=cls._get_connector_tabs(connector),
            )

            # Cache the status
            cls._connector_status[connector_id] = connector_status
            return connector_status

        except TimeoutError:
            connector_status = ConnectorStatus(
                connector_id=connector.connector_id,
                connector_name=connector.connector_name,
                category=cls._get_connector_category(connector),
                status="error",
                available=True,
                base_url=getattr(connector, 'website_url', None) or getattr(connector, 'base_url', None),
                last_ping=datetime.utcnow(),
                error_message=f"Health check timed out after {effective_timeout}s",
                tabs=cls._get_connector_tabs(connector),
            )
            cls._connector_status[connector_id] = connector_status
            return connector_status

        except Exception as e:
            connector_status = ConnectorStatus(
                connector_id=connector.connector_id,
                connector_name=connector.connector_name,
                category=cls._get_connector_category(connector),
                status="error",
                available=True,
                base_url=getattr(connector, 'website_url', None) or getattr(connector, 'base_url', None),
                last_ping=datetime.utcnow(),
                error_message=str(e),
                tabs=cls._get_connector_tabs(connector),
            )
            cls._connector_status[connector_id] = connector_status
            return connector_status

    @classmethod
    async def check_all_status(
        cls,
        timeout: float = 10.0,
        include_tests: bool = False,
    ) -> list[ConnectorStatus]:
        """
        Check status of all connectors in parallel.

        Args:
            timeout: Timeout for each health check
            include_tests: If True, also run test queries against each connector

        Returns:
            List of ConnectorStatus for all connectors
        """
        connector_ids = cls.get_registered_ids()
        if not connector_ids:
            return []

        # Check all connectors in parallel
        tasks = [
            cls.check_connector_status(cid, timeout=timeout)
            for cid in connector_ids
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        statuses = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                connector_id = connector_ids[i]
                connector = cls.get(connector_id)
                statuses.append(ConnectorStatus(
                    connector_id=connector_id,
                    connector_name=connector.connector_name if connector else connector_id,
                    category=cls._get_connector_category(connector) if connector else "unknown",
                    status="error",
                    available=True,
                    base_url=getattr(connector, 'website_url', None) or getattr(connector, 'base_url', None) if connector else None,
                    last_ping=datetime.utcnow(),
                    error_message=str(result),
                    tabs=cls._get_connector_tabs(connector) if connector else [],
                ))
            else:
                statuses.append(result)

        # Run tests if requested
        if include_tests:
            # Run tests in parallel with semaphore to limit concurrency
            semaphore = asyncio.Semaphore(5)

            async def test_with_limit(cid: str):
                async with semaphore:
                    return cid, await cls.run_connector_tests(cid, timeout=30.0)

            # Only test connectors that are available and not in error state
            testable_ids = [
                s.connector_id for s in statuses
                if s.available and s.status in ("ok", "warning", "unknown")
            ]

            test_tasks = [test_with_limit(cid) for cid in testable_ids]
            test_results = await asyncio.gather(*test_tasks, return_exceptions=True)

            # Build results map
            results_map: dict[str, dict[str, QueryTestResult]] = {}
            for result in test_results:
                if not isinstance(result, Exception):
                    cid, test_result = result
                    results_map[cid] = test_result

            # Merge test results into status objects
            for status in statuses:
                if status.connector_id in results_map:
                    status.test_results = results_map[status.connector_id]
                # Add api_docs_url if available
                connector = cls.get(status.connector_id)
                if connector:
                    status.api_docs_url = getattr(connector, 'api_docs_url', None)

        return statuses

    @classmethod
    async def run_connector_tests(
        cls,
        connector_id: str,
        timeout: float = 30.0,
    ) -> dict[str, QueryTestResult]:
        """
        Run all test queries against a connector.

        Args:
            connector_id: ID of the connector to test
            timeout: Timeout for each query

        Returns:
            Dict mapping query_id to QueryTestResult
        """
        connector = cls.get(connector_id)
        if not connector:
            return {}

        # Check if connector is available
        if hasattr(connector, 'available') and not connector.available:
            return {}

        results: dict[str, QueryTestResult] = {}

        try:
            async with connector:
                for query_id, query_name in cls.TEST_QUERIES:
                    result = await cls._run_single_test(
                        connector, query_id, query_name, timeout
                    )
                    results[query_id] = result
                    # Rate limit between queries
                    await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"Error running tests for {connector_id}: {e}")
            # Return partial results if we have any
            pass

        return results

    @classmethod
    async def _run_single_test(
        cls,
        connector: BaseConnector,
        query_id: str,
        query_name: str,
        timeout: float,
    ) -> QueryTestResult:
        """
        Run a single test query against a connector.

        Args:
            connector: The connector instance
            query_id: ID of the test query
            query_name: Search query string
            timeout: Timeout in seconds

        Returns:
            QueryTestResult with results or error
        """
        start = time.time()
        try:
            items = await asyncio.wait_for(
                connector.search(query_name, limit=5),
                timeout=timeout
            )
            elapsed = (time.time() - start) * 1000

            # Extract sample items (up to 3)
            sample_items = [
                SampleItem(
                    id=item.id,
                    title=item.title[:80] if item.title else "",
                    url=item.url,
                    thumbnail_url=item.thumbnail_url,
                )
                for item in items[:3]
            ]

            return QueryTestResult(
                query_id=query_id,
                query_name=query_name,
                result_count=len(items),
                sample_items=sample_items,
                response_time_ms=elapsed,
            )
        except TimeoutError:
            return QueryTestResult(
                query_id=query_id,
                query_name=query_name,
                result_count=0,
                sample_items=[],
                response_time_ms=(time.time() - start) * 1000,
                error=f"Timeout after {timeout}s",
            )
        except Exception as e:
            return QueryTestResult(
                query_id=query_id,
                query_name=query_name,
                result_count=0,
                sample_items=[],
                response_time_ms=(time.time() - start) * 1000,
                error=str(e)[:100],
            )

    @classmethod
    def get_cached_status(cls) -> list[ConnectorStatus]:
        """
        Get cached status for all connectors without performing health checks.

        Returns cached status, or creates 'unknown' status for connectors
        that haven't been checked yet.
        """
        statuses = []
        for connector_id in cls.get_registered_ids():
            if connector_id in cls._connector_status:
                statuses.append(cls._connector_status[connector_id])
            else:
                connector = cls.get(connector_id)
                if connector:
                    # Check if connector is marked as unavailable
                    is_available = getattr(connector, 'available', True)
                    if not is_available:
                        reason = getattr(connector, 'unavailable_reason', None) or "Service unavailable"
                        statuses.append(ConnectorStatus(
                            connector_id=connector.connector_id,
                            connector_name=connector.connector_name,
                            category=cls._get_connector_category(connector),
                            status="unavailable",
                            available=False,
                            base_url=getattr(connector, 'website_url', None) or getattr(connector, 'base_url', None),
                            error_message=reason,
                            tabs=cls._get_connector_tabs(connector),
                        ))
                    else:
                        statuses.append(ConnectorStatus(
                            connector_id=connector.connector_id,
                            connector_name=connector.connector_name,
                            category=cls._get_connector_category(connector),
                            status="unknown",
                            available=True,
                            base_url=getattr(connector, 'website_url', None) or getattr(connector, 'base_url', None),
                            tabs=cls._get_connector_tabs(connector),
                        ))
        return statuses

    @classmethod
    async def close_all(cls) -> None:
        """Close all connector instances (cleanup HTTP clients, etc.)."""
        for connector_id, connector in cls._connector_instances.items():
            try:
                if hasattr(connector, "__aexit__"):
                    await connector.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing connector {connector_id}: {e}")

        cls._connector_instances.clear()
        cls._connector_status.clear()
        logger.info("All connectors closed")
