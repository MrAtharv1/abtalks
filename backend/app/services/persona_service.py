from app.llm.base import LLMProvider
from app.schemas.persona import GeneratedPersona
import logging

logger = logging.getLogger("thread")

PERSONA_PROMPT_TEMPLATE = """
Persona name:
{name}

Domain:
{domain}

You are initializing the intellectual identity of an autonomous AI persona.

The persona is not a fictional human biography.

Do not invent:
- employment history
- education
- credentials
- personal experiences
- real-world accomplishments
- relationships
- locations
- memories

Instead construct an editorial and intellectual identity.

The persona should have:
- a consistent communication style
- a stable epistemic attitude
- evidence preferences
- editorial principles
- domain-specific interests
- a small set of long-running research threads (3-5 threads)

The persona must be capable of changing its mind later when evidence changes.

Do not make it dogmatic.

Research questions must be specific and investigable.

Avoid generic questions such as:
"What is the future of AI?"

Prefer questions such as:
"How does granting language-model agents tool access change their security boundary?"

The research agenda should contain questions whose answers can meaningfully change as new evidence appears.

Prioritize:
- important unresolved problems
- uncertainty
- emerging developments
- disagreements
- areas where evidence can change current understanding

Do not generate social-media posts.
Do not generate slogans.
Do not generate a biography.

Generate only the structured intellectual identity and research agenda.

Return ONLY the GeneratedPersona object itself. Do not wrap it in the persona name, agent name, domain name, or any additional top-level key. The first JSON key must be one of the GeneratedPersona fields. Never return {{"Ada": {{...}}}}.
"""

class PersonaService:
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider

    async def initialize_persona(self, name: str, domain: str) -> GeneratedPersona:
        prompt = PERSONA_PROMPT_TEMPLATE.format(name=name, domain=domain)
        logger.info("generating_identity")
        
        try:
            generated_persona = await self.llm.generate_structured(
                prompt=prompt,
                schema=GeneratedPersona
            )
            logger.info("identity_generated")
            logger.info("generating_agenda")
            logger.info(f"{len(generated_persona.research_threads)}_threads_generated")
            
            question_count = sum(len(t.questions) for t in generated_persona.research_threads)
            logger.info(f"{question_count}_questions_generated")
            
            return generated_persona
        except Exception as e:
            logger.error(f"LLM failure during persona generation: {e}")
            raise
