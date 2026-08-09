import uuid
import logging
import hashlib
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.models import ResearchQuestion, ResearchThread, Agent, PersonaProfile, ResearchRun, Source, Evidence
from app.llm.base import LLMProvider
from app.research.search import SearchProvider
from app.research.query_planner import QueryPlanner
from app.research.fetcher import SourceFetcher, normalize_url
from app.research.extractor import ContentExtractor
from app.research.evidence import EvidenceExtractor

logger = logging.getLogger("thread")

class ResearchService:
    def __init__(self, db: AsyncSession, llm_provider: LLMProvider, search_provider: SearchProvider,
                 fast_llm_provider: LLMProvider | None = None):
        self.db = db
        # Use the fast provider for high-volume LLM calls (query gen + evidence extraction).
        # Falls back to the main provider if no fast provider is supplied.
        _fast = fast_llm_provider if fast_llm_provider is not None else llm_provider
        self.planner = QueryPlanner(_fast)
        self.fetcher = SourceFetcher()
        self.content_extractor = ContentExtractor()
        self.evidence_extractor = EvidenceExtractor(_fast)
        self.search_provider = search_provider

    async def research_question(self, question_id: str, stop_event: asyncio.Event = None) -> str:
        logger.info(f"[RESEARCH] run_started for question_id={question_id}")
        
        # 1. Load Question & Persona
        result = await self.db.execute(
            select(ResearchQuestion)
            .options(
                selectinload(ResearchQuestion.thread).selectinload(ResearchThread.agent).selectinload(Agent.persona)
            )
            .where(ResearchQuestion.id == question_id)
        )
        question = result.scalar_one_or_none()
        
        if not question:
            logger.error("Question not found")
            return None
            
        logger.info(f"[RESEARCH] question_loaded: {question.question}")
        persona = question.thread.agent.persona
        
        # 2. Create ResearchRun
        run = ResearchRun(
            id=str(uuid.uuid4()),
            question_id=question.id,
            status="RUNNING",
            queries_generated=[],
            sources_discovered=[],
            sources_processed=[],
            evidence_extracted=[]
        )
        self.db.add(run)
        question.status = "INVESTIGATING"
        await self.db.commit()
        await self.db.refresh(run)

        # Ensure lists are initialized
        run_queries = []
        run_discovered = []
        run_processed = []
        run_evidence = []
        
        try:
            # 3. Generate queries
            generated_queries = await self.planner.generate_queries(question, persona)
            run_queries = [q.query for q in generated_queries.queries]
            logger.info(f"[RESEARCH] queries_generated: {run_queries}")
            
            # 4. Search
            search_tasks = [self.search_provider.search(q.query, limit=3) for q in generated_queries.queries]
            search_results_lists = await asyncio.gather(*search_tasks, return_exceptions=True)
            
            all_urls = set()
            search_results = []
            for res_list in search_results_lists:
                if isinstance(res_list, Exception):
                    logger.warning(f"Search task failed: {res_list}")
                    continue
                for res in res_list:
                    norm_url = normalize_url(res.url)
                    if norm_url not in all_urls:
                        all_urls.add(norm_url)
                        search_results.append((norm_url, res))
                        run_discovered.append(norm_url)
            
            logger.info(f"[SEARCH] results_received, deduplicated count: {len(search_results)}")
            
            # --- Quota Optimization: Limit to top 3 unique sources per run ---
            search_results = search_results[:3]
            logger.info(f"[SEARCH] results_limited_to: {len(search_results)}")
            
            # 5. Process Sources with Bounded Concurrency
            # Serialize LLM evidence extraction to avoid TPM bursts within a minute window
            semaphore = asyncio.Semaphore(1)
            
            async def process_source(norm_url, search_res):
                async with semaphore:
                    if stop_event and stop_event.is_set():
                        return None, None
                    logger.info(f"[SOURCE] discovered: {norm_url}")
                    
                    # 1. DB: Check if source exists
                    from app.db.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as session:
                        existing_source = await session.execute(select(Source).where(Source.canonical_url == norm_url))
                        source = existing_source.scalar_one_or_none()
                        source_id = source.id if source else None
                        source_url = source.url if source else None
                        source_quality_score = source.quality_score if source else None
                    
                    if not source_id:
                        try:
                            # External I/O outside DB session
                            if stop_event and stop_event.is_set():
                                return None, None
                            doc = await self.fetcher.fetch(search_res.url)
                            logger.info(f"[SOURCE] fetched: {norm_url}")
                            
                            content_text = self.content_extractor.extract_text(doc)
                            if not content_text:
                                raise ValueError("No usable text extracted")
                                
                            content_hash = hashlib.sha256(content_text.encode('utf-8')).hexdigest()
                            
                            quality = 0.6 if len(content_text) > 500 else 0.3
                            if ".edu" in norm_url or ".gov" in norm_url:
                                quality += 0.2
                                
                            source_id = str(uuid.uuid4())
                            source_quality_score = min(quality, 1.0)
                            
                            # 2. DB: Insert new source
                            async with AsyncSessionLocal() as session:
                                new_source = Source(
                                    id=source_id,
                                    url=search_res.url,
                                    canonical_url=norm_url,
                                    title=search_res.title,
                                    domain=search_res.source_domain,
                                    content_type=doc.content_type,
                                    content_hash=content_hash,
                                    quality_score=source_quality_score
                                )
                                session.add(new_source)
                                await session.commit()
                        except Exception as e:
                            logger.warning(f"Failed to process source {norm_url}: {e}")
                            return None, None # Failed source, gracefully skip
                    else:
                        logger.info(f"[SOURCE] loaded from cache: {norm_url}")
                        try:
                            if stop_event and stop_event.is_set():
                                return None, None
                            doc = await self.fetcher.fetch(source_url)
                            content_text = self.content_extractor.extract_text(doc)
                            if not content_text:
                                raise ValueError("No usable text extracted")
                        except Exception as e:
                            logger.warning(f"Failed to fetch cached source {norm_url}: {e}")
                            return None, None
                            
                    if stop_event and stop_event.is_set():
                        return None, None
                        
                    # --- Context Chunking for Token Reduction (Ordered) ---
                    stop_words = {"what", "how", "why", "is", "are", "the", "a", "an", "do", "does", "did", "in", "of", "for", "to", "and", "or", "on"}
                    import re
                    keywords = set(re.findall(r'\b\w+\b', question.question.lower())) - stop_words
                    
                    chunk_size = 1500
                    chunks = []
                    for i in range(0, len(content_text), chunk_size):
                        chunks.append((i, content_text[i:i+chunk_size]))
                        
                    scored_chunks = []
                    for orig_idx, chunk_text in chunks:
                        chunk_lower = chunk_text.lower()
                        score = sum(1 for kw in keywords if kw in chunk_lower)
                        scored_chunks.append((score, orig_idx, chunk_text))
                        
                    scored_chunks.sort(key=lambda x: x[0], reverse=True)
                    top_chunks = scored_chunks[:3]
                    
                    # Restore original document order
                    top_chunks.sort(key=lambda x: x[1])
                    
                    if top_chunks and any(score > 0 for score, _, _ in top_chunks):
                        filtered_text = "\n...\n".join(text for _, _, text in top_chunks)
                    else:
                        logger.info(f"[EVIDENCE] Skipping {norm_url} due to 0 keyword matches")
                        return norm_url, []

                    # --- Evidence Caching (Fix #5) ---
                    async with AsyncSessionLocal() as session:
                        past_runs_res = await session.execute(
                            select(ResearchRun)
                            .where(ResearchRun.question_id == question.id)
                            .where(ResearchRun.status == "COMPLETED")
                        )
                        processed_before = False
                        for past_run in past_runs_res.scalars().all():
                            if past_run.sources_processed and norm_url in past_run.sources_processed:
                                processed_before = True
                                break
                                
                        if processed_before:
                            cached_ev_res = await session.execute(
                                select(Evidence)
                                .where(Evidence.source_id == source_id)
                                .where(Evidence.question_id == question.id)
                            )
                            cached_ev = cached_ev_res.scalars().all()
                            logger.info(f"[EVIDENCE] skipped LLM extraction, loaded {len(cached_ev)} cached items for {norm_url}")
                            return norm_url, [e.id for e in cached_ev]

                    # 6. Extract Evidence
                    logger.info(f"[EVIDENCE] extraction_started for {norm_url}")
                    evidence_list = await self.evidence_extractor.extract(question, filtered_text, norm_url)
                    
                    if stop_event and stop_event.is_set():
                        return None, None
                    
                    persisted_evidence = []
                    # 3. DB: Insert evidence
                    async with AsyncSessionLocal() as session:
                        for ev in evidence_list:
                            e_model = Evidence(
                                id=str(uuid.uuid4()),
                                question_id=question.id,
                                source_id=source_id,
                                claim=ev.claim,
                                evidence_text=ev.evidence_text,
                                context=ev.context,
                                relevance_score=ev.relevance_score,
                                source_quality_score=source_quality_score or 0.5,
                                confidence=ev.confidence,
                                polarity=ev.polarity
                            )
                            session.add(e_model)
                            persisted_evidence.append(e_model.id)
                        await session.commit()
                    
                    return norm_url, persisted_evidence

            process_tasks = [process_source(u, r) for u, r in search_results]
            processed_results = await asyncio.gather(*process_tasks, return_exceptions=True)
            
            for res in processed_results:
                if isinstance(res, tuple):
                    url, ev_ids = res
                    if url:
                        run_processed.append(url)
                    if ev_ids:
                        run_evidence.extend(ev_ids)
            
            # Determine final status
            if len(run_processed) == 0 and len(run_discovered) > 0:
                run.status = "FAILED"
                run.error_message = "All sources failed to process"
            elif len(run_processed) < len(run_discovered):
                run.status = "PARTIAL"
            else:
                run.status = "COMPLETED"
                
        except Exception as e:
            logger.error(f"[RESEARCH] run failed with exception: {e}")
            run.status = "FAILED"
            run.error_message = str(e)
        finally:
            run.queries_generated = run_queries
            run.sources_discovered = run_discovered
            run.sources_processed = run_processed
            run.evidence_extracted = run_evidence
            run.completed_at = datetime.utcnow()
            question.status = "OPEN"
            await self.db.commit()
            logger.info(f"[RESEARCH] run_completed with status {run.status}")
            
        return run.id
