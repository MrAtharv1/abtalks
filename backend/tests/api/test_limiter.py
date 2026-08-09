import pytest
import asyncio
import time
from app.llm.limiter import GlobalGroqLimiter

@pytest.mark.asyncio
async def test_global_limiter_concurrency():
    limiter = GlobalGroqLimiter()
    limiter.tpm_limit = 100000 # High limit so we only test concurrency
    
    active_workers = 0
    max_active = 0
    
    async def worker():
        nonlocal active_workers, max_active
        await limiter.acquire(100)
        active_workers += 1
        max_active = max(max_active, active_workers)
        await asyncio.sleep(0.1) # Simulate network call
        active_workers -= 1
        await limiter.release(100, 100)

    # Launch 5 workers concurrently
    await asyncio.gather(*(worker() for _ in range(5)))
    
    # Sem has 2 slots, max active should never exceed 2
    assert max_active == 2

@pytest.mark.asyncio
async def test_global_limiter_tpm_reservation():
    limiter = GlobalGroqLimiter()
    limiter.tpm_limit = 200 # Small limit
    
    # First acquire should pass immediately
    start = time.monotonic()
    await limiter.acquire(150)
    assert limiter.tokens_used == 150
    await limiter.release(150, 150)
    
    # Second acquire for 100 should wait because 150 + 100 > 200
    # Wait time should be around (250 - 200) / (200 / 60) = 50 / 3.33 = 15s.
    # To avoid a slow test, we can manually manipulate last_update
    limiter.last_update = time.monotonic() - 15.0 
    
    await limiter.acquire(100)
    # The decay should have cleared ~50 tokens.
    assert limiter.tokens_used <= 200
    await limiter.release(100, 100)

@pytest.mark.asyncio
async def test_global_limiter_429():
    limiter = GlobalGroqLimiter()
    
    # Simulate a 429 that asks us to wait 0.5s
    await limiter.handle_429(0.5)
    
    start = time.monotonic()
    await limiter.acquire(10)
    end = time.monotonic()
    
    assert end - start >= 0.45
    await limiter.release(10, 10)
