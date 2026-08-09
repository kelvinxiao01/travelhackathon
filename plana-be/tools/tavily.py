import os
import logging
from typing import Optional
import httpx
from langsmith import traceable

logger = logging.getLogger(__name__)

@traceable
async def web_research(query: str, location: Optional[str] = None) -> str:
    """
    Search the web using Tavily.
    Raises ValueError if API Key is not set, or httpx exceptions on connection errors.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logger.error("Tavily API key is missing from environment variables!")
        raise ValueError("Tavily API Key is not configured.")

    logger.info("Executing real Tavily search for: %r", query)
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": f"{query} in {location}" if location else query,
        "search_depth": "basic",
        "include_answer": True
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=12.0)
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        
        formatted_results = []
        for r in results[:4]:
            formatted_results.append(
                f"Title: {r.get('title')}\nURL: {r.get('url')}\nSnippet: {r.get('content')}"
            )
        return "\n\n".join(formatted_results)
