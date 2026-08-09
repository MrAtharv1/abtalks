import asyncio
import httpx
import logging
from pprint import pprint
import json
import time

# Set up simple logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluator_soak")

API_URL = "http://127.0.0.1:8000/api/agent"

async def main():
    logger.info("Starting Evaluator Soak Test (20 minutes)...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Initialize Agent
        logger.info("Initializing Agent via POST /init...")
        init_payload = {
            "persona": {
                "name": "Dr. Aris",
                "domain": "Artificial Intelligence Ethics"
            }
        }
        
        try:
            init_response = await client.post(f"{API_URL}/init", json=init_payload)
            init_response.raise_for_status()
            data = init_response.json()
            agent_id = data["agentId"]
            logger.info(f"Agent initialized successfully. ID: {agent_id}")
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            return
            
        logger.info("The agent is now completely autonomous.")
        logger.info("Waiting and polling GET /feed to observe independent output over 20 minutes...")
        
        # 2. Polling Loop
        polls = 0
        last_post_count = 0
        start_time = time.time()
        # 20 minutes = 1200 seconds, polling every 10 seconds = 120 polls
        total_polls = 120
        
        while polls < total_polls:
            polls += 1
            await asyncio.sleep(10)
            
            logger.info(f"--- Poll {polls}/{total_polls} (Elapsed: {int(time.time() - start_time)}s) ---")
            try:
                feed_response = await client.get(f"{API_URL}/feed?agentId={agent_id}")
                feed_response.raise_for_status()
                feed_data = feed_response.json()
                
                posts = feed_data.get("posts", [])
                
                if len(posts) > last_post_count:
                    new_posts = posts[last_post_count:]
                    logger.info(f"*** FOUND {len(new_posts)} NEW POSTS! ***")
                    for i, post in enumerate(new_posts):
                        logger.info(f"--- NEW POST {last_post_count + i + 1} ---")
                        logger.info(f"TEXT: {post['text']}")
                        logger.info(f"RATIONALE: {post['rationale']}")
                        logger.info(f"SOURCES: {post['sources']}")
                        logger.info("-" * 40)
                    last_post_count = len(posts)
                else:
                    logger.info(f"No new posts. Total: {last_post_count}")
                    
            except Exception as e:
                logger.error(f"Failed to fetch feed: {e}")

        logger.info("\n=========================================")
        logger.info(f"SOAK TEST COMPLETE. Total posts generated: {last_post_count}")
        logger.info("=========================================")

if __name__ == "__main__":
    asyncio.run(main())
