from bs4 import BeautifulSoup
from app.schemas.research import FetchedDocument
import logging

logger = logging.getLogger("thread")

class ContentExtractor:
    def extract_text(self, document: FetchedDocument) -> str:
        """Extract clean text from fetched document."""
        from app.config import settings
        if settings.llm_provider == "fake":
            return "Grounded Claim Test Content"

        if "text/html" not in document.content_type:
            # We skip PDF extraction for Phase 2, return empty string or raise
            return ""
            
        try:
            soup = BeautifulSoup(document.raw_content, 'html.parser')
            
            # Remove boilerplate elements
            for el in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript']):
                el.decompose()
                
            text = soup.get_text(separator=' ', strip=True)
            
            # Basic cleanup of extra whitespace
            clean_text = ' '.join(text.split())
            return clean_text
        except Exception as e:
            logger.warning(f"Content extraction failed for {document.final_url}: {e}")
            return ""
