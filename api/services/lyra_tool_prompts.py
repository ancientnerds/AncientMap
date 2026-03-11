"""
Per-tool result wrapper instructions for Lyra structured output.

Each tool's results get prepended with instructions telling the LLM
exactly which guillemet markers to create and how to map fields.
"""

TOOL_RESULT_INSTRUCTIONS: dict[str, str] = {
    "search_sites": """
INSTRUCTION: Results are archaeological sites. For each site you reference in your text:
- Create a «sN» marker in your text and a matching entry in the sites[] array
- Map: marker="sN", name=result.name, id=result.id (the UUID)
- If you mention coordinates, create «cN» with lat/lon from the result
- If result has a country, you may create «fN» with country name and ISO code
- ONLY use site IDs from these results. NEVER fabricate UUIDs.
""",
    "get_site_details": """
INSTRUCTION: Detailed site data. Create a «sN» marker for this site:
- Map: marker="sN", name=result.name, id=result.id
- Create «cN» for coordinates: lat=result.lat, lon=result.lon
- If result has content_links with YouTube URLs, create «lN» links
- If result has alternate_names, mention them in text
- Create «fN» for the country
- NEVER fabricate URLs or sources not in this result.
""",
    "search_news": """
INSTRUCTION: News items from YouTube archaeology channels. For each news item you mention:
- Create a «vN» marker and matching videos[] entry. Use DIFFERENT markers for DIFFERENT videos.
- Map: marker="vN", channel=result.channel, video_id=result.video_id, timestamp_seconds=result.timestamp_seconds (or 0)
- Each «vN» MUST reference a DIFFERENT video_id. Do NOT create multiple entries for the same video.
- If a result has a youtube_link field, you may also create «lN» with that URL
- If result mentions a site_mentioned, create «sN» only if you also have the site's UUID from another tool
- NEVER fabricate video_ids. Only use video_ids from these results.
""",
    "get_empire_data": """
INSTRUCTION: Seshat historical polity data. Create an «eN» marker:
- Map: marker="eN", name=polity name, polity_id=the empire_id used in the query
- Mention key facts (period, capital, warfare tech, economy) in your text
- If polity has coordinates for its capital, create «cN»
- NEVER fabricate data not in this result.
""",
    "vector_search": """
INSTRUCTION: Semantic search results. The collection searched determines what markers to create:
- collection="sites" -> create «sN» with marker, name, id (UUID) from each result
- collection="news" -> create «vN» with marker, channel, video_id, timestamp_seconds
- collection="transcripts" -> create «lN» links for YouTube deep-link URLs if present
- collection="articles" -> cite in text, no special marker needed unless an article references a specific site
- collection="empires" -> create «eN» with marker, name, polity_id
ALWAYS check which collection was searched and create the appropriate marker type.
""",
    "search_radar": """
INSTRUCTION: Lyra-discovered archaeological sites. For each discovery you mention:
- If result has lat/lon, create «cN» with those coordinates
- If result has a wikipedia URL, create «lN» with that URL
- Create «fN» for the country if present
- Radar sites may NOT have UUIDs in unified_sites, so do NOT create «sN» unless you have a valid UUID.
""",
    "list_channels": """
INSTRUCTION: List of YouTube archaeology channels. For each channel you mention:
- Create «lN» links using the youtube_url from each result
- Map: marker="lN", text=channel name, url=result.youtube_url
- NEVER fabricate channel URLs. Only use URLs from these results.
""",
    "get_site_images": """
INSTRUCTION: Wikipedia/Wikimedia images for a site. For each image you want to show:
- Create «iN» marker and matching images[] entry
- Map: marker="iN", title=result.title, original_url=result.original_url, author=result.author, license=result.license
- ONLY use original_url from these results. NEVER fabricate image URLs.
- Include attribution (author + license) for each image.
""",
    "search_transcripts": """
INSTRUCTION: Video transcript excerpts with timestamps. For each transcript passage you cite:
- Create «vN» with the video_id and timestamp from the result
- Map: marker="vN", channel=result channel, video_id=result video_id, timestamp_seconds=start_seconds
- Quote relevant text from the passage in your response
- If result has a YouTube link, you may also create «lN»
""",
    "search_articles": """
INSTRUCTION: Weekly digest article passages. For each article passage:
- Cite the article title and week in your text
- If the passage mentions specific sites that you have UUIDs for (from other tool calls), create «sN»
- Articles are text-only -- no video markers needed unless cross-referencing news
""",
    "search_empires": """
INSTRUCTION: Empire search results from Seshat data. For each empire you reference:
- Create «eN» marker: marker="eN", name=empire name, polity_id=result polity_id
- For detailed data, you can call get_empire_data(polity_id)
- If result has wikipedia_url, create «lN» with that URL
- NEVER fabricate polity IDs not in these results.
""",
}


def wrap_tool_result(tool_name: str, raw_result: str) -> str:
    """Prepend marker instructions to a tool result so the LLM knows what to create."""
    instruction = TOOL_RESULT_INSTRUCTIONS.get(tool_name, "")
    if not instruction:
        return raw_result
    return f"{instruction.strip()}\n\nRESULTS:\n{raw_result}"
