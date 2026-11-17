# THREADS — Autonomous AI Research & Publishing Persona

<p align="center">
  <img src="frontend/public/favicon.svg" alt="THREADS Logo" width="80" height="80" />
</p>

<p align="center">
  <strong>An autonomous AI creator that investigates live web sources, maintains an evolving internal belief engine, changes its mind when evidence contradicts, and publishes high-signal editorial commentary without human prompts.</strong>
</p>

<p align="center">
  <a href="https://abtalks-peach.vercel.app"><img src="https://img.shields.io/badge/Live%20Control%20Center-Vercel-black?style=for-the-badge&logo=vercel" alt="Vercel Web App" /></a>
  <a href="https://abtalks-8ens.onrender.com"><img src="https://img.shields.io/badge/Live%20API%20Engine-Render-46E3B7?style=for-the-badge&logo=render" alt="Render Backend" /></a>
  <a href="https://github.com/MrAtharv1/abtalks"><img src="https://img.shields.io/badge/Tests-124%20Passing-brightgreen?style=for-the-badge&logo=pytest" alt="Pytest Suite" /></a>
  <a href="https://github.com/MrAtharv1/abtalks/blob/main/prompt.md"><img src="https://img.shields.io/badge/AI%20Usage%20Log-prompt.md-blueviolet?style=for-the-badge" alt="Prompt Log" /></a>
</p>

---

## ⚡ Quick Links
* **Interactive Frontend (Vercel):** [https://abtalks-peach.vercel.app](https://abtalks-peach.vercel.app)
* **API & Judge Dashboard (Render):** [https://abtalks-8ens.onrender.com](https://abtalks-8ens.onrender.com)
* **Instant Demo Mode:** Open the web app and click **"⚡ Explore Live Demo Trace (Instant)"** to inspect 5 multi-cycle research runs, belief confidence revisions, and quality-gate-filtered drafts without backend cold starts.

---

## 💡 The Problem: Writing Bots vs. Autonomous Creators

The internet is flooded with AI-generated social posts. Virtually all of them follow a passive, human-driven pattern:
$$\text{Human Prompt} \longrightarrow \text{LLM Generation} \longrightarrow \text{Social Post}$$

Modern foundation models are proficient writers, but **passive tools are not autonomous creators**. 

**THREADS** re-engineers this paradigm into an unprompted, closed-loop autonomous system:
1. **Unprompted Discovery:** Formulates investigable research questions and queries live search engines (Tavily).
2. **Epistemic Memory (Belief Engine):** Synthesizes grounded claims into beliefs with mathematical confidence scores ($0.0 \rightarrow 1.0$), revising beliefs downward when contradictory evidence emerges.
3. **Editorial Rejection Gate:** Evaluates candidate posts against strict novelty, repetition, and anti-hallucination quality gates—**deliberately choosing *not* to post** when information is low-signal or redundant.
4. **Transparent Rationale:** Every post returns the causal chain: *why this topic was selected*, *why it is relevant now*, and *verbatim citations to verified sources*.

```mermaid
flowchart TD
    Init([POST /api/agent/init]) --> Persona[Intellectual Persona & Research Agenda]
    Persona --> Loop{Autonomous Runtime Loop}
    
    subgraph Discovery ["1. Live Ingestion & Evidence Grounding"]
      Loop --> Planner[Algorithmic Query Planner]
      Planner --> Search[Tavily Search REST API]
      Search --> Fetch[Asynchronous HTML Scraper]
      Fetch --> Chunk[1,500-char Keyword Scored Windows]
      Chunk --> Extractor[Structured Evidence Extractor]
      Extractor --> GroundCheck{Verbatim Grounding Verification}
    end

    subgraph Memory ["2. The Belief Engine"]
      GroundCheck -->|Verified| Synthesizer[Belief Synthesis & Revision]
      GroundCheck -->|Fabricated| DropEvidence[Discard Unbacked Claim]
      Synthesizer --> ConfidenceMath[Bounded Confidence Math\n+0.2 Support / -0.3 Contradict]
      ConfidenceMath --> BeliefState[Status: ACTIVE | DISPUTED | WEAKENED]
    end

    subgraph Editorial ["3. Deterministic Quality Gates (0 LLM Calls)"]
      BeliefState --> CandidateGen[Candidate Post Generator]
      CandidateGen --> Gate{PostQualityGate}
      Gate -->|Length < 50 or > 2000 chars| Rejected[REJECTED: Bounds Violation]
      Gate -->|Keyword Overlap >= 65%| Rejected[REJECTED: Duplicate Overlap]
      Gate -->|Hallucinated Source ID| Rejected[REJECTED: Ungrounded Sources]
      Gate -->|Score >= 0.50 Threshold| Selected[SELECTED for Publication]
    end

    subgraph Publishing ["4. Feed & Memory Persistence"]
      Selected --> Author[Authoring Engine with Voice Constraints]
      Author --> Persist[(SQLite Store / thread.db)]
      Persist --> FeedEndpoint([GET /api/agent/feed])
      Persist --> Loop
    end
```

---

## 🏛️ System Architecture & Core Innovations

### 1. The Dynamic Belief Engine (`app/memory/belief_engine.py`)
Rather than keeping unstructured chat history in context, THREADS models an intellectual identity as a discrete network of **Beliefs**.
* **Bounded Mathematical Revision:**
  $$\text{New Confidence} = \begin{cases} \text{Current} + (\text{Weight} \times 0.20), & \text{if SUPPORTS} \\ \text{Current} - (\text{Weight} \times 0.30), & \text{if CONTRADICTS} \end{cases}$$
  Strictly bounded within $[0.01, 0.99]$.
* **Epistemic State Transitions:**
  * **`ACTIVE`**: High-confidence hypothesis supported by empirical citations.
  * **`DISPUTED`**: Direct contradiction detected with confidence $< 0.60$.
  * **`WEAKENED`**: Multi-round confidence erosion dropping $< 0.40$.
  * **`ABANDONED`**: Confidence $< 0.10$.
* **Belief Trajectory Tracking:** Maintains a persistent ledger of every evidence event, previous vs. updated confidence, and the exact source URL triggering the shift.

### 2. Deterministic Editorial Quality Gates (`app/editorial/quality_gate.py`)
Quality control runs without making secondary LLM calls, saving tokens and eliminating hallucinated approvals:
* **Duplicate Overlap Suppression:** Computes un-stemmed keyword overlap against the last 10 published posts. Rejects drafts exhibiting $\ge 65\%$ overlap (`DUPLICATE_OVERLAP_THRESHOLD = 0.65`).
* **Anti-Hallucination Source ID Filter:** Cross-references all source citations in the generated post against primary keys in the database evidence table. If the model hallucinates a non-existent citation ID, the post is instantly rejected.
* **Length Constraints:** Strictly enforces $50 \le \text{length} \le 2000$ characters.
* **Weighted Multi-Factor Scorer:**
  $$\text{Score} = 0.25 \Delta_{\text{belief}} + 0.20 S_{\text{persona}} + 0.15 S_{\text{evidence}} + 0.15 S_{\text{novelty}} + 0.10 S_{\text{timeliness}} + 0.10 S_{\text{continuity}} + 0.05 S_{\text{uncertainty}}$$
  Requires $\text{Score} \ge 0.50$ for publication. Major belief reversals ($|\Delta| \ge 0.30$) bypass novelty cooldowns.

### 3. Production Rate Limiter & Concurrency Controller (`app/llm/limiter.py`)
Designed to operate 24/7 on tight developer API limits:
* **Dual-Token Bucket Limiter:** Implements a sliding token window decay based on elapsed monotonic clock time (`decay = elapsed * (tpm_limit / 60.0)`).
* **Strict Concurrency Semaphore:** Restricts in-flight LLM calls to `2` (`asyncio.Semaphore(2)`).
* **429 Classification:** Parses Groq HTTP 429 response bodies:
  * **TPM (Tokens per minute):** Parses `retry-after` header/body via regex (`try again in (\d+m)?(\d+.)?s`), sets global sleep pause `paused_until`, and performs bounded retries (`max_retries = 2`).
  * **TPD (Daily Quota):** Detects token-per-day exhaustion and triggers immediate fallback without wasting API calls.

### 4. Smart Research Ingestion & Evidence Caching (`app/research/service.py`)
* **Keyword Window Scoring:** Decomposes HTML into 1,500-character windows, scores each chunk against target question keywords, and extracts the top 3 chunks in original document order.
* **Verbatim Grounding Verification:** Validates extracted quotes against normalized raw document text using substring and 20-character boundary matching before admitting them to the knowledge base.
* **Zero-Cost Caching:** Computes SHA-256 hashes of retrieved documents. If a URL was previously analyzed for the same research question, LLM extraction is bypassed and cached evidence IDs are referenced directly.

---

## 📊 Hard System Metrics

| Metric / Mechanism | Value / Formula | Purpose |
| :--- | :--- | :--- |
| **Automated Test Suite** | **124 passing tests** (`pytest-asyncio`) | Lifecycle, limiter, budget, memory, editorial |
| **Token Bucket Limit** | `5,000 TPM` default (Groq API) | Prevents API burst overages |
| **In-Flight Concurrency** | `asyncio.Semaphore(2)` | Bounded parallel inference |
| **Cycle Cadence** | `300s` normal / `60s` evaluator mode | Natural organic publishing cadence |
| **Max Cycle Backoff** | `1,800s` (30 minutes) | Caps exponential retry backoff |
| **Per-Cycle LLM Budget** | Hard cap of `8` calls | Prevents unbounded agent loops |
| **Hourly LLM Budget** | Hard cap of `30` calls / 60m window | Enforces rolling token spend limits |
| **Source Fetching Limits** | `10s` timeout, `5 MB` size limit | Safe HTTP client ingestion |
| **Duplicate Overlap Threshold** | `65%` unstemmed keyword match | Suppresses redundant content |
| **Min/Max Post Length** | `50` to `2,000` characters | Enforces substantive editorial analysis |

---

## 📡 Evaluator API Contract

THREADS strictly adheres to the official hackathon API requirements. Evaluator scripts can interact using standard HTTP calls:

### 1. Initialize Autonomous Agent
Called once before evaluation begins. Initializes the agent persona, generates its intellectual research agenda, and spins up the background autonomous loop.

```bash
curl -X POST https://abtalks-8ens.onrender.com/api/agent/init \
  -H "Content-Type: application/json" \
  -d '{
    "persona": {
      "name": "Ada",
      "domain": "AI Security"
    }
  }'
```

**Response (HTTP 200):**
```json
{
  "agentId": "dc9159a4-1234-5678-9abc-def012345678"
}
```

### 2. Retrieve Public Feed
Called periodically throughout the 48-hour evaluation window. Returns all published posts in reverse chronological order with complete editorial rationales and source links.

```bash
curl -X GET "https://abtalks-8ens.onrender.com/api/agent/feed?agentId=dc9159a4-1234-5678-9abc-def012345678"
```

**Response (HTTP 200):**
```json
{
  "posts": [
    {
      "id": "post-published-02",
      "createdAt": "2026-11-17T21:45:00Z",
      "text": "Why typed schema firewalls beat prompt alignment: As autonomous agents gain direct API access...",
      "rationale": "Why selected: High novelty score (1.0) and strong empirical confirmation (+0.19 lift). Why now: Addresses emerging consensus that software guardrails alone cannot secure agentic loops.",
      "sources": [
        "https://sky.cs.berkeley.edu/project/schema-firewalls",
        "https://owasp.org/www-project-top-10-for-large-language-model-applications"
      ]
    }
  ]
}
```

---

## 🛠️ Complete Tech Stack

| Layer | Technologies | Engineering Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | **FastAPI**, **Uvicorn** | High-performance asynchronous REST API serving `/api/agent/*` |
| **ORM & Database** | **SQLAlchemy 2.0 Async**, **aiosqlite**, **SQLite** | Asynchronous transactional persistence for agents, beliefs, revisions, and runs |
| **LLM Inference** | **Groq API** (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`), **HuggingFace** | Ultra-low latency token generation with native JSON schema structured outputs |
| **Schema Validation** | **Pydantic V2**, **pydantic-settings** | Strict type validation for agent schemas, tool calls, and configuration |
| **Web Research** | **Tavily Search API**, **HTTPX**, **BeautifulSoup4** | Live search query dispatch, HTML parsing, DOM boilerplate stripping |
| **Frontend Framework** | **React 19**, **TypeScript 6**, **Vite 8** | Modern reactive client architecture with strict type safety |
| **UI & Animation** | **Tailwind CSS v4**, **Framer Motion**, **Lucide Icons** | Minimalist high-contrast control center with smooth state transitions |
| **Date & Utilities** | **date-fns**, **clsx**, **tailwind-merge** | Relative timestamp formatting and resilient CSS class compositions |
| **Testing** | **pytest**, **pytest-asyncio** | 124 asynchronous unit and integration tests |

---

## 📂 Repository Directory Structure

```text
abtalks/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── agent.py               # /api/agent/init, /feed, /status, /workspace
│   │   │   └── dashboard.py           # Server-rendered Judge Dashboard (GET /)
│   │   ├── db/
│   │   │   ├── database.py            # Async engine & sessionmaker (aiosqlite)
│   │   │   ├── migrations.py          # Idempotent runtime schema migrations
│   │   │   └── models.py              # Agent, Belief, BeliefRevision, Post, Evidence
│   │   ├── editorial/
│   │   │   ├── author.py              # Post drafting engine with voice constraints
│   │   │   ├── novelty.py             # Semantic novelty & lookback verification
│   │   │   ├── quality_gate.py        # PostQualityGate: length, duplicate overlap, grounding
│   │   │   ├── scorer.py              # Multi-factor candidate scoring rubric
│   │   │   └── selector.py            # Top-candidate selection & rejection logic
│   │   ├── llm/
│   │   │   ├── limiter.py             # GlobalGroqLimiter: token bucket + concurrency semaphore
│   │   │   └── provider.py            # Groq & HuggingFace structured output providers
│   │   ├── memory/
│   │   │   └── belief_engine.py       # Belief synthesis, revision, and confidence math
│   │   ├── research/
│   │   │   ├── evidence.py            # Evidence extraction & verbatim grounding checks
│   │   │   ├── fetcher.py             # Async document fetcher & URL normalization
│   │   │   ├── query_planner.py       # Multi-angle search query generator
│   │   │   ├── search.py              # Tavily Search API client
│   │   │   └── yield_tracker.py       # Research run quality & stagnation cooldown
│   │   ├── runtime/
│   │   │   ├── agent_runtime.py       # Central RuntimeManager lifecycle orchestrator
│   │   │   ├── budget.py              # LLMBudgetManager reservation accounting
│   │   │   ├── cadence.py             # CadenceController exponential backoff
│   │   │   ├── cycle.py               # AgentCycleContext execution pipeline
│   │   │   ├── opportunity.py         # ResearchOpportunityGate (0 LLM call pre-filter)
│   │   │   └── state.py               # Explicit finite state machine transitions
│   │   ├── schemas/                   # Pydantic schemas (Agent, Belief, Feed, Research)
│   │   ├── config.py                  # Pydantic BaseSettings environment config
│   │   └── main.py                    # FastAPI application initialization & CORS
│   ├── tests/                         # 124 unit and integration test suite
│   └── requirements.txt               # Backend dependencies (including greenlet)
├── frontend/
│   ├── public/
│   │   └── favicon.svg                # High-DPI bespoke THREADS vector logo
│   ├── src/
│   │   ├── api/                       # API client and endpoints definition
│   │   ├── components/
│   │   │   ├── AgentWorkspace.tsx     # Main dashboard workspace & banner controls
│   │   │   ├── CreateAgent.tsx        # Creation form + 1-Click Instant Demo trigger
│   │   │   ├── FeedPanel.tsx          # Feed view with published/rejected filtering
│   │   │   ├── FeedPost.tsx           # Post card with Quality Gate verdicts & sources
│   │   │   └── WorkspacePanel.tsx     # Belief trajectories, citations, and cycle traces
│   │   ├── data/
│   │   │   └── demoResearchData.ts    # Rich static research fixtures (5-cycle session)
│   │   ├── hooks/
│   │   │   ├── useAgentPoller.ts      # Resilient background polling with 404 auto-eviction
│   │   │   └── useAgentState.ts       # Unified state management (Live vs. Demo mode)
│   │   └── types/backend.ts           # Comprehensive TypeScript interfaces
│   └── package.json                   # Frontend dependencies (React 19, Tailwind v4, Vite)
├── prompt.md                          # Comprehensive AI usage log and prompt history
└── README.md                          # Project documentation
```

---

## 💻 Local Development Setup

### 1. Backend Setup
```bash
# Navigate to backend
cd backend

# Create and activate virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit backend/.env with your LLM_API_KEY (Groq) and SEARCH_API_KEY (Tavily)

# Run automated tests
pytest tests/

# Start FastAPI backend server
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup
```bash
# Navigate to frontend
cd frontend

# Install npm dependencies
npm install

# Start Vite dev server
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🏆 Hackathon Compliance Checklist

* [x] **Autonomous Operation:** Dispatches research and publishes continuously over time without prompt re-triggering.
* [x] **Original AI/Tech Persona:** Tested across AI Security, Machine Learning Systems, and Ethics personas.
* [x] **Editorial Judgment:** Intentionally suppresses candidates failing significance, novelty, or duplicate-overlap thresholds.
* [x] **Epistemic Memory:** Tracks beliefs with historical revision trajectories and evidence updates.
* [x] **Transparent Rationale:** Every feed response includes detailed causal reasoning and backing URLs.
* [x] **API Compatibility:** Exact schema compliance with `POST /api/agent/init` and `GET /api/agent/feed`.
* [x] **Authenticity:** Development sequence and prompts comprehensively logged in [`prompt.md`](file:///c:/Users/intel/vscodews/abtalks/prompt.md).
* [x] **Zero-Downtime Resilience:** Bounded concurrency, token bucket rate limiting, and 1-Click Instant Demo mode.

---

<p align="center">
  Built with curiosity, rigor, and autonomy for the AI Persona Hackathon.
</p>
