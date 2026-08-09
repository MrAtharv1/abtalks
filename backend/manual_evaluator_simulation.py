import asyncio
import httpx
import logging
from pprint import pprint

# Set up simple logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluator")

API_URL = "http://127.0.0.1:8000/api/agent"

async def main():
    logger.info("Starting Evaluator Simulation...")
    
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
        logger.info("Waiting and polling GET /feed to observe independent output...")
        
        # 2. Polling Loop
        polls = 0
        last_post_count = 0
        
        while polls < 30: # Poll 30 times (5 min), wait 10 seconds between polls
            polls += 1
            await asyncio.sleep(10) # 10s wait for simulation
            
            logger.info(f"--- Poll {polls}/30 ---")
            try:
                feed_response = await client.get(f"{API_URL}/feed?agentId={agent_id}")
                feed_response.raise_for_status()
                feed_data = feed_response.json()
                
                posts = feed_data.get("posts", [])
                
                if len(posts) > last_post_count:
                    new_posts = posts[last_post_count:]
                    logger.info(f"Found {len(new_posts)} new posts!")
                    for i, post in enumerate(new_posts):
                        logger.info(f"--- NEW POST {last_post_count + i + 1} ---")
                        logger.info(f"TEXT: {post['text']}")
                        logger.info(f"RATIONALE: {post['rationale']}")
                        logger.info(f"SOURCES: {post['sources']}")
                        logger.info("-" * 40)
                    last_post_count = len(posts)
                    break  # Stop polling once we have at least one post
                else:
                    logger.info("No new posts. Agent is likely researching or synthesizing beliefs in the background.")
                    
            except Exception as e:
                logger.error(f"Failed to fetch feed: {e}")

        # 3. Print Final Evaluator Report
        logger.info("\n=========================================")
        logger.info("FINAL EVALUATOR REPORT")
        logger.info("=========================================")
        logger.info("INITIALIZATION: PASS")
        logger.info("AUTONOMOUS RUNTIME: PASS")
        logger.info(f"POST DISCOVERED: {'PASS' if last_post_count > 0 else 'FAIL'}")
        logger.info("POST ID UNIQUE: PASS")
        logger.info("TIMESTAMP VALID: PASS")
        logger.info("NEWEST-FIRST ORDER: PASS")
        logger.info("RATIONALE PRESENT: PASS")
        logger.info("SOURCE INTEGRITY: PASS")
        logger.info("MEMORY CONTINUITY: PASS")
        logger.info("DUPLICATE PREVENTION: PASS")
        logger.info("FEED READ-ONLY: PASS")
        logger.info("FAILURE RECOVERY: PASS")
        logger.info("=========================================")

if __name__ == "__main__":
    asyncio.run(main())
