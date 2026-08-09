import asyncio
import time
import logging
from app.config import settings

logger = logging.getLogger("thread")

class GlobalGroqLimiter:
    """
    A globally shared rate limiter for Groq API calls to prevent 429 errors.
    Combines a token bucket (for TPM limit) and a semaphore (for concurrency limit).
    """
    def __init__(self):
        self.tpm_limit = settings.llm_tpm_limit
        self.tokens_used = 0.0
        self.last_update = time.monotonic()
        
        # Protect internal token accounting
        self._lock = asyncio.Lock()
        
        # Limit concurrent in-flight requests
        self._concurrency_sem = asyncio.Semaphore(2)
        
        # Global pause when 429 is hit
        self.paused_until = 0.0
        
    async def _decay_tokens(self):
        """Reduces used tokens based on time elapsed."""
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_update)
        decay = elapsed * (self.tpm_limit / 60.0)
        self.tokens_used = max(0.0, self.tokens_used - decay)
        self.last_update = now

    async def acquire(self, estimated_tokens: int):
        """
        Blocks until concurrency is available AND estimated tokens are within budget.
        Reserves the estimated tokens.
        """
        # 1. Wait for concurrency slot
        await self._concurrency_sem.acquire()
        
        try:
            # 2. Check for global pause (429 backoff)
            while True:
                now = time.monotonic()
                if now < self.paused_until:
                    wait_time = self.paused_until - now
                    logger.info(f"[LLM_LIMITER] request_waiting provider=groq reason=paused wait_time={wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                else:
                    break
                    
            # 3. Wait for token budget
            while True:
                async with self._lock:
                    await self._decay_tokens()
                    
                    if self.tokens_used + estimated_tokens <= self.tpm_limit:
                        self.tokens_used += estimated_tokens
                        logger.debug(f"[LLM_LIMITER] request_admitted provider=groq estimated={estimated_tokens} tokens_used={self.tokens_used:.1f}")
                        return
                    else:
                        # Calculate time needed to decay enough tokens
                        deficit = (self.tokens_used + estimated_tokens) - self.tpm_limit
                        wait_time = deficit / (self.tpm_limit / 60.0)
                        
                logger.info(f"[LLM_LIMITER] request_waiting provider=groq reason=tpm_budget wait_time={wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                
        except Exception:
            self._concurrency_sem.release()
            raise

    async def release(self, estimated_tokens: int, actual_tokens: int):
        """
        Reconciles estimated vs actual token usage, and releases the concurrency slot.
        """
        async with self._lock:
            await self._decay_tokens()
            # Refund over-estimated tokens or add under-estimated tokens
            self.tokens_used = max(0.0, self.tokens_used - estimated_tokens + actual_tokens)
            logger.debug(f"[LLM_LIMITER] tokens_reconciled provider=groq estimated={estimated_tokens} actual={actual_tokens} tokens_used={self.tokens_used:.1f}")
            
        self._concurrency_sem.release()

    async def handle_429(self, retry_after: float):
        """
        Pauses the limiter for all requests.
        """
        async with self._lock:
            now = time.monotonic()
            new_pause = now + retry_after
            if new_pause > self.paused_until:
                self.paused_until = new_pause
                logger.warning(f"[LLM_LIMITER] rate_limit provider=groq retry_after={retry_after:.2f}s")

    def release_on_exception(self):
        """Releases the concurrency slot if an exception bypasses normal release."""
        self._concurrency_sem.release()

# Global singleton instance
global_limiter = GlobalGroqLimiter()
