from app.llm.base import LLMProvider
from app.schemas.research import GeneratedResearchQueries
from app.db.models import ResearchQuestion, PersonaProfile
import logging

logger = logging.getLogger("thread")

PLANNER_PROMPT_TEMPLATE = """
Research Question:
{question}

Persona Domain:
{domain}

Persona Style & Principles:
{principles}

You are generating research queries to investigate the question above.
Generate exactly 2 distinct queries.
Each query must approach the question from a different angle (e.g. OVERVIEW, EMPIRICAL, TECHNICAL, COUNTEREVIDENCE).
Do not generate identical queries.
Ensure queries are specific enough to retrieve useful external evidence.
"""

class QueryPlanner:
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider

    async def generate_queries(self, question: ResearchQuestion, persona: PersonaProfile) -> GeneratedResearchQueries:
        logger.info(f"Generating queries for question: {question.id}")
        
        principles = ""
        if persona.editorial_principles:
            principles = ", ".join(persona.editorial_principles)
            
        prompt = PLANNER_PROMPT_TEMPLATE.format(
            question=question.question,
            domain=persona.domain,
            principles=principles
        )
        
        try:
            queries = await self.llm.generate_structured(prompt=prompt, schema=GeneratedResearchQueries)
            logger.info(f"Generated {len(queries.queries)} queries")
            return queries
        except Exception as e:
            logger.error(f"Failed to generate queries: {e}")
            raise
