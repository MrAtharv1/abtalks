from typing import Protocol, List
from app.schemas.research import SearchResult
from app.config import settings
import httpx
import logging

logger = logging.getLogger("thread")

class SearchProvider(Protocol):
    async def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        ...

class DefaultSearchProvider(SearchProvider):
    async def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        api_key = getattr(settings, "search_api_key", None)
        if not api_key or api_key == "your_tavily_api_key_here":
            raise ValueError("No SEARCH_API_KEY provided. Cannot perform web search.")
            
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": limit
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            if response.status_code != 200:
                logger.error(f"Tavily Search API Error {response.status_code}: {response.text}")
                return []
                
            data = response.json()
            results = data.get("results", [])
            
            search_results = []
            for r in results:
                # Basic domain extraction for source_domain
                domain = r.get("url", "").split("/")[2] if "//" in r.get("url", "") else r.get("url", "")
                
                search_results.append(
                    SearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        snippet=r.get("content", ""),
                        source_domain=domain
                    )
                )
                
            return search_results

class FakeSearchProvider(SearchProvider):
    def __init__(self):
        self.call_count = 0
        
    async def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        self.call_count += 1
        
        # Scenario logic based on number of searches
        # 1st cycle search (call count 1-3) -> Supporting
        # 2nd cycle search (call count 4-6) -> Contradictory
        
        if self.call_count > 3:
            return [
                SearchResult(
                    url=f"https://example.com/contradiction/{self.call_count}",
                    title=f"Contradictory findings for {query}",
                    snippet=f"contradict: new benchmark shows complete failure for {query}",
                    source_domain="example.com"
                )
            ]
            
        return [
            SearchResult(
                url=f"https://example.com/article/{self.call_count}",
                title=f"Fake result for {query}",
                snippet=f"This is a snippet discussing {query} with supporting evidence",
                source_domain="example.com"
            )
        ]

def get_search_provider() -> SearchProvider:
    if getattr(settings, "search_provider", "tavily") == "fake":
        return FakeSearchProvider()
    return DefaultSearchProvider()
