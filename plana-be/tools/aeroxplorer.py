import os
import time
import logging
from typing import Any, Dict, List, Optional
import httpx
from langsmith import traceable

logger = logging.getLogger(__name__)

class AeroXplorerClient:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(AeroXplorerClient, cls).__new__(cls, *args, **kwargs)
            cls._instance.token = None
            cls._instance.token_expiry = 0
        return cls._instance

    async def get_token(self) -> Optional[str]:
        """Retrieve or refresh cached bearer token using real hackathon keys."""
        api_key = os.getenv("AEROXPLORER_API_KEY")
        api_secret = os.getenv("AEROXPLORER_API_SECRET")
        token_url = os.getenv("AEROXPLORER_TOKEN_URL", "https://api.aeroxplorer.com/v1/token")

        if not api_key or not api_secret:
            logger.error("AeroXplorer credentials are not configured!")
            raise ValueError("AeroXplorer Key/Secret is missing.")

        current_time = time.time()
        if self.token and self.token_expiry > current_time + 300:
            return self.token

        logger.info("AeroXplorer: Fetching real hackathon bearer token")
        headers = {
            "X-User": f"{api_key}:{api_secret}"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(token_url, headers=headers, timeout=6.0)
                if response.status_code == 200:
                    data = response.json()
                    self.token = data.get("access_token") or data.get("token")
                    expires_in = data.get("expires_in", 3600)
                    self.token_expiry = current_time + expires_in
                    logger.info("AeroXplorer: Token successfully cached")
                    return self.token
                else:
                    logger.error("AeroXplorer real auth failed: %s %s", response.status_code, response.text)
            except Exception as e:
                logger.error("AeroXplorer auth request failed: %s", e)

        return None

    @traceable
    async def search_flights(self, query: str) -> List[Dict[str, Any]]:
        """Search flight information using the AeroXplorer API."""
        token = await self.get_token()
        if token:
            logger.info("Executing real AeroXplorer flight search for: %r", query)
            url = "https://api.aeroxplorer.com/v1/flights/search"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            params = {"query": query}
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(url, headers=headers, params=params, timeout=10.0)
                    if response.status_code == 200:
                        return response.json().get("flights", [])
                    else:
                        logger.error("AeroXplorer search failed: %s %s", response.status_code, response.text)
                except Exception as e:
                    logger.error("AeroXplorer search request failed: %s", e)
        return []

async def search_flight_information(query: str) -> List[Dict[str, Any]]:
    client = AeroXplorerClient()
    return await client.search_flights(query)
