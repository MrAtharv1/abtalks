from sqlalchemy import Column, String, ForeignKey, DateTime, Text, func, JSON, Float, Integer
from sqlalchemy.orm import relationship
from app.db.database import Base

class PersonaProfile(Base):
    __tablename__ = "personas"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    domain = Column(String, nullable=False)
    voice_style = Column(String, nullable=True)
    technicality = Column(Float, nullable=True)
    skepticism = Column(Float, nullable=True)
    formality = Column(Float, nullable=True)
    preferred_content_types = Column(JSON, nullable=True)
    avoided_content_types = Column(JSON, nullable=True)
    editorial_principles = Column(JSON, nullable=True)
    evidence_preferences = Column(JSON, nullable=True)

    agent = relationship("Agent", back_populates="persona", uselist=False)

class Agent(Base):
    __tablename__ = "agents"
    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="ACTIVE", nullable=False)
    runtime_status = Column(String, default="IDLE", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    persona_id = Column(String, ForeignKey("personas.id"), nullable=False, unique=True)
    # Phase 7: runtime stats (nullable for backward compat with existing rows)
    last_post_at = Column(DateTime(timezone=True), nullable=True)
    total_cycles = Column(Integer, default=0, nullable=True)
    total_posts = Column(Integer, default=0, nullable=True)
    total_llm_calls = Column(Integer, default=0, nullable=True)

    persona = relationship("PersonaProfile", back_populates="agent")
    posts = relationship("Post", back_populates="agent", cascade="all, delete-orphan")
    research_threads = relationship("ResearchThread", back_populates="agent", cascade="all, delete-orphan")
    beliefs = relationship("Belief", back_populates="agent", cascade="all, delete-orphan")
    editorial_candidates = relationship("EditorialCandidate", back_populates="agent", cascade="all, delete-orphan")
    editorial_decisions = relationship("EditorialDecision", back_populates="agent", cascade="all, delete-orphan")
    research_runs = relationship("ResearchRun", back_populates="agent", cascade="all, delete-orphan")
    agent_cycles = relationship("AgentCycle", back_populates="agent", cascade="all, delete-orphan")

class Post(Base):
    __tablename__ = "posts"
    id = Column(String, primary_key=True, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    candidate_id = Column(String, ForeignKey("editorial_candidates.id"), nullable=True)
    belief_id = Column(String, ForeignKey("beliefs.id"), nullable=True)
    revision_id = Column(String, ForeignKey("belief_revisions.id"), nullable=True)
    question_id = Column(String, ForeignKey("research_questions.id"), nullable=True)
    rationale = Column(Text, nullable=True)
    sources = Column(JSON, nullable=True)

    agent = relationship("Agent", back_populates="posts")

class ResearchThread(Base):
    __tablename__ = "research_threads"
    id = Column(String, primary_key=True, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, default="ACTIVE", nullable=False)
    priority = Column(Float, default=0.5, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_activity_at = Column(DateTime(timezone=True), nullable=True)

    agent = relationship("Agent", back_populates="research_threads")
    questions = relationship("ResearchQuestion", back_populates="thread", cascade="all, delete-orphan")
    beliefs = relationship("Belief", back_populates="thread", cascade="all, delete-orphan")

class ResearchQuestion(Base):
    __tablename__ = "research_questions"
    id = Column(String, primary_key=True, index=True)
    thread_id = Column(String, ForeignKey("research_threads.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    status = Column(String, default="OPEN", nullable=False)
    importance = Column(Float, default=0.5, nullable=False)
    confidence = Column(Float, default=0.5, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # Phase 7: research yield memory fields (all nullable for backward compat)
    research_attempts = Column(Integer, default=0, nullable=True)
    successful_runs = Column(Integer, default=0, nullable=True)
    useful_evidence_count = Column(Integer, default=0, nullable=True)
    consecutive_low_yield_runs = Column(Integer, default=0, nullable=True)
    last_meaningful_change_at = Column(DateTime(timezone=True), nullable=True)
    yield_score = Column(Float, default=0.5, nullable=True)
    stagnant_until = Column(DateTime(timezone=True), nullable=True)

    thread = relationship("ResearchThread", back_populates="questions")
    research_runs = relationship("ResearchRun", back_populates="question", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="question", cascade="all, delete-orphan")

class Source(Base):
    __tablename__ = "sources"
    id = Column(String, primary_key=True, index=True)
    url = Column(String, nullable=False)
    canonical_url = Column(String, nullable=False, unique=True, index=True)
    title = Column(String, nullable=True)
    publisher = Column(String, nullable=True)
    author = Column(String, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    retrieved_at = Column(DateTime(timezone=True), server_default=func.now())
    content_type = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    source_type = Column(String, nullable=True)
    quality_score = Column(Float, nullable=True)
    content_hash = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # Phase 7: freshness tracking
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    evidence = relationship("Evidence", back_populates="source", cascade="all, delete-orphan")

class Evidence(Base):
    __tablename__ = "evidence"
    id = Column(String, primary_key=True, index=True)
    question_id = Column(String, ForeignKey("research_questions.id"), nullable=False, index=True)
    source_id = Column(String, ForeignKey("sources.id"), nullable=False, index=True)
    
    claim = Column(Text, nullable=False)
    evidence_text = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    
    relevance_score = Column(Float, nullable=False)
    source_quality_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    polarity = Column(String, nullable=False)
    
    extracted_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    question = relationship("ResearchQuestion", back_populates="evidence")
    source = relationship("Source", back_populates="evidence")

class ResearchRun(Base):
    __tablename__ = "research_runs"
    id = Column(String, primary_key=True, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=True, index=True)
    question_id = Column(String, ForeignKey("research_questions.id"), nullable=False, index=True)
    status = Column(String, nullable=False)  # RUNNING, COMPLETED, FAILED, PARTIAL
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    queries_generated = Column(JSON, nullable=True)
    sources_discovered = Column(JSON, nullable=True)
    sources_processed = Column(JSON, nullable=True)
    evidence_extracted = Column(JSON, nullable=True)
    
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Phase 7: yield tracking fields (all nullable for backward compat)
    yield_score = Column(Float, nullable=True)
    source_diversity_score = Column(Float, nullable=True)
    contradiction_count = Column(Integer, default=0, nullable=True)
    belief_change_delta = Column(Float, nullable=True)

    agent = relationship("Agent", back_populates="research_runs")
    question = relationship("ResearchQuestion", back_populates="research_runs")

class Belief(Base):
    __tablename__ = "beliefs"
    id = Column(String, primary_key=True, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    thread_id = Column(String, ForeignKey("research_threads.id"), nullable=False, index=True)
    statement = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    importance = Column(Float, nullable=False)
    status = Column(String, nullable=False)  # ACTIVE, WEAKENED, DISPUTED, SUPERSEDED, ABANDONED
    scope = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_revised_at = Column(DateTime(timezone=True), nullable=True)

    agent = relationship("Agent", back_populates="beliefs")
    thread = relationship("ResearchThread", back_populates="beliefs")
    evidence_links = relationship("BeliefEvidence", back_populates="belief", cascade="all, delete-orphan")
    revisions = relationship("BeliefRevision", back_populates="belief", cascade="all, delete-orphan", order_by="asc(BeliefRevision.created_at)")

class BeliefEvidence(Base):
    __tablename__ = "belief_evidence"
    id = Column(String, primary_key=True, index=True)
    belief_id = Column(String, ForeignKey("beliefs.id"), nullable=False, index=True)
    evidence_id = Column(String, ForeignKey("evidence.id"), nullable=False, index=True)
    relationship_type = Column("relationship", String, nullable=False)  # SUPPORTS, CONTRADICTS, QUALIFIES
    weight = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    belief = relationship("Belief", back_populates="evidence_links")
    evidence = relationship("Evidence")

class BeliefRevision(Base):
    __tablename__ = "belief_revisions"
    id = Column(String, primary_key=True, index=True)
    belief_id = Column(String, ForeignKey("beliefs.id"), nullable=False, index=True)
    previous_confidence = Column(Float, nullable=False)
    new_confidence = Column(Float, nullable=False)
    change_type = Column(String, nullable=False)  # INITIAL, STRENGTHENED, WEAKENED, DISPUTED, REPLACED
    reason = Column(Text, nullable=False)
    trigger_evidence_id = Column(String, ForeignKey("evidence.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    belief = relationship("Belief", back_populates="revisions")
    trigger_evidence = relationship("Evidence")

class EditorialCandidate(Base):
    __tablename__ = "editorial_candidates"
    id = Column(String, primary_key=True, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    belief_id = Column(String, ForeignKey("beliefs.id"), nullable=True, index=True)
    revision_id = Column(String, ForeignKey("belief_revisions.id"), nullable=True, index=True)
    question_id = Column(String, ForeignKey("research_questions.id"), nullable=True, index=True)
    
    headline = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    
    editorial_significance = Column(Float, nullable=False)
    novelty_score = Column(Float, nullable=False)
    relevance_score = Column(Float, nullable=False)
    evidence_strength = Column(Float, nullable=False)
    persona_fit_score = Column(Float, nullable=False)
    timeliness_score = Column(Float, nullable=False)
    continuity_score = Column(Float, nullable=False)
    competition_score = Column(Float, nullable=False)
    
    status = Column(String, nullable=False)  # PENDING, SELECTED, PUBLISHED, REJECTED, EXPIRED, FAILED
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    selected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)

    agent = relationship("Agent", back_populates="editorial_candidates")

class EditorialDecision(Base):
    __tablename__ = "editorial_decisions"
    id = Column(String, primary_key=True, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    candidate_id = Column(String, ForeignKey("editorial_candidates.id"), nullable=False, index=True)
    selected = Column(String, nullable=False)
    score = Column(Float, nullable=False)
    decision_type = Column(String, nullable=False)  # SELECTED, REJECTED, DEFERRED
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agent = relationship("Agent", back_populates="editorial_decisions")

class AgentCycle(Base):
    __tablename__ = "agent_cycles"
    id = Column(String, primary_key=True, index=True)
    agent_id = Column(String, ForeignKey("agents.id"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False)  # COMPLETED, FAILED, PARTIAL
    question_id = Column(String, ForeignKey("research_questions.id"), nullable=True, index=True)
    research_run_id = Column(String, ForeignKey("research_runs.id"), nullable=True, index=True)
    belief_revisions_count = Column(Integer, default=0, nullable=True)
    candidate_count = Column(Integer, default=0, nullable=True)
    published_post_id = Column(String, ForeignKey("posts.id"), nullable=True, index=True)
    error = Column(Text, nullable=True)
    
    agent = relationship("Agent", back_populates="agent_cycles")
