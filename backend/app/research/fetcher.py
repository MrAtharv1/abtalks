import httpx
import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from app.schemas.research import FetchedDocument

logger = logging.getLogger("thread")

def normalize_url(url: str) -> str:
    """Normalize URL by stripping common tracking params and trailing slashes."""
    try:
        parsed = urlparse(url)
        # Remove trailing slash from path if it's not just '/'
        path = parsed.path
        if len(path) > 1 and path.endswith('/'):
            path = path[:-1]
            
        # Filter tracking params
        query_params = parse_qs(parsed.query)
        clean_params = {k: v for k, v in query_params.items() if not k.startswith("utm_")}
        query = urlencode(clean_params, doseq=True)
        
        return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, query, parsed.fragment))
    except Exception:
        return url

class SourceFetcher:
    def __init__(self, timeout: int = 10, max_size: int = 5 * 1024 * 1024):
        self.timeout = timeout
        self.max_size = max_size
        self.headers = {
            "User-Agent": "THREAD Research Bot/1.0"
        }

    async def fetch(self, url: str) -> FetchedDocument:
        from app.config import settings
        if settings.llm_provider == "fake":
            class MockDoc:
                def __init__(self):
                    self.url = url
                    self.final_url = url
                    self.content_type = "text/html"
                    self.raw_content = b"mock content"
            return MockDoc()

        logger.info(f"Fetching source: {url}")
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, headers=self.headers) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type and "application/pdf" not in content_type:
                    raise ValueError(f"Unsupported content type: {content_type}")
                
                content = response.content
                if len(content) > self.max_size:
                    raise ValueError("Source content too large")
                    
                final_url = str(response.url)
                
                return FetchedDocument(
                    url=url,
                    final_url=final_url,
                    content_type=content_type,
                    raw_content=content
                )
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
                raise
