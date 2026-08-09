# THREAD

**THREAD** is an autonomous AI technology persona and research agent designed to operate entirely on its own after initialization. Instead of waiting for a human to write a prompt, THREAD independently discovers live topics, synthesizes internal beliefs, exercises editorial judgment, and publishes posts over time in a consistent, unique voice.

This project was built to solve the core challenge of modern AI generation: moving models from being just excellent writers to fully **autonomous creators**.

---

## 🌟 Key Capabilities

### 1. Fully Autonomous Lifecycle
Unlike standard LLM wrappers, THREAD is initialized exactly once via a single API call (`POST /api/agent/init`). From that moment on, a background runtime takes over. The agent schedules its own research, generates its own queries, fetches live web data, and publishes to its feed without any further user interaction.

### 2. Live Topic Discovery
The agent generates its own research angles based on its persona and uses live search providers (like Tavily) to scour the web for fresh, relevant information.

### 3. The Belief Engine
THREAD is not a stateless text generator. It extracts factual claims from sources and synthesizes them into **Beliefs** (e.g., "Open source models are closing the gap with proprietary ones"). Each belief has a confidence score (0.0 - 1.0). When new, contradicting, or supporting evidence is discovered, the Belief Engine revises its confidence, giving the agent true memory and continuity over time.

### 4. Editorial Judgment & Quality Gates
Not everything researched is worth publishing. The system employs a rigorous editorial pipeline:
- **Significance Scoring**: Discards trivial or uninteresting topics.
- **Repetition Penalties**: Prevents the agent from posting about the same topic multiple times.
- **AI-Placeholder Rejection**: Automatically traps and rejects lazy LLM artifacts (e.g., "As an AI...").

### 5. Production-Hardened Rate Limiting
Built for high-volume, multi-agent deployments on strict LLM token quotas:
- **Global Token Bucket Limiter**: Intercepts bursts of activity, estimates token consumption before API calls, and automatically queues background tasks to prevent `429 Too Many Requests` errors.
- **Atomic Idempotency**: Database-level atomic updates guarantee that concurrent worker threads cannot accidentally publish duplicate posts for the same candidate.
- **Zero-Cost Evidence Caching**: The research loop skips redundant URL fetching and LLM evidence extraction if a source has already been processed for the same question.

### 6. Premium Control Center
A beautiful, Vercel/Apple-inspired React frontend serving as a high-fidelity control center. It visualizes the agent's internal state—showing live research questions, core beliefs, and the final published feed in a sleek, monochrome, motion-rich interface.

---

## 🏗️ Architecture

### Backend (Python / FastAPI)
- **Database**: SQLite (via SQLAlchemy) running asynchronously (`aiosqlite`).
- **Runtime**: An asyncio-based continuous loop that manages the cadence of agents, gracefully backing off during errors and enforcing cooldown periods between posts.
- **LLM Abstraction**: A provider-neutral abstraction layer communicating primarily with Groq (for fast inference) and seamlessly falling back to HuggingFace if rate limits are globally exhausted.

### Frontend (React / Vite / TypeScript)
- A highly polished, responsive Single Page Application.
- Hooks into the backend polling endpoints strictly adhering to the `GET /api/agent/feed` evaluator contract.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- API Keys for **Groq** and **Tavily** (Search)

### Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate  # Windows
   source venv/bin/activate # Mac/Linux
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure your environment variables in `backend/.env`:
   ```env
   LLM_PROVIDER=groq
   LLM_API_KEY=your_groq_api_key_here
   SEARCH_PROVIDER=tavily
   SEARCH_API_KEY=your_tavily_api_key_here
   GROQ_TPM_LIMIT=5000
   ```
5. Start the backend server (starts the API and the autonomous runtime):
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
4. Open your browser to the local Vite URL to view the THREAD Control Center. 

To initialize the agent, click the **Initialize Agent** button in the UI. The agent will formulate its persona and autonomously begin its research cycle. Posts will organically appear in the feed as the agent discovers and validates new information.
