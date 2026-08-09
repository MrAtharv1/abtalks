# Hackathon Prompts

The following represents the sequence of prompts used to generate and refine the THREAD autonomous agent system.

---

### Prompt 1: Initial Context & Problem Statement Check
> "continue where gemini left it off , 2 and also this was problem statement and rules , please check if we are not violating anything (just tell me first for this then if needed we will proceed with the fixes)"

### Prompt 2: The Core Challenge
> "The Situation: Every day, thousands of AI-generated posts appear on LinkedIn and X. Almost all of them exist because a human wrote the first prompt. Today's models are excellent writers. They are rarely autonomous creators. Your challenge is to build an autonomous AI and technology persona that no longer waits for instructions.
>
> Once initialized, the agent should independently:
> - Discover topics from live information sources
> - Decide whether a topic is worth publishing
> - Write in a consistent editorial voice
> - Remember previously published content
> - Continue publishing over time without additional human input
>
> The persona must represent an original identity within the AI and technology ecosystem. Examples include: AI Security Researcher, Machine Learning Engineer, AI Product Analyst, Open Source Contributor, Robotics Engineer, Developer Advocate, AI Ethics Researcher, Or any original AI or technology-focused persona.
> After initialization, the agent must operate autonomously."

### Prompt 3: Autonomous Lifecycle Fixes
> "# Critical Fix: Autonomous Start After Agent Initialization
> Proceed with the critical autonomous-start fix.
> 
> ## Evaluator Contract
> The evaluator's contract is:
> POST /api/agent/init
>         ↓
> evaluator only polls
> GET /api/agent/feed?agentId=...
> 
> The evaluator will NEVER call `/api/agent/start`.
> Therefore, after a successful `POST /api/agent/init`, the agent MUST autonomously begin operating and eventually publish posts to the feed without requiring any additional API call or user action. Make the smallest surgical change necessary to satisfy this contract."

### Prompt 4: Premium Frontend Control Center
> "Build the complete frontend for THREAD using the existing backend as the source of truth.
> 
> ## Goal
> We already have a working autonomous-agent backend. The frontend should be a premium, production-quality control center for autonomous research agents, not a generic dashboard.
> The backend is already implemented. Do not redesign or modify the backend unless absolutely necessary to make an existing API consumable. Inspect the actual backend routes, schemas, response shapes, runtime behavior, and existing frontend code before implementing anything. The frontend must be completely wired to the real backend — no mock data, fake agents, fake posts, placeholder API responses, or simulated runtime states.
> 
> # 1. Product Experience
> THREAD should feel like a combination of:
> - Apple's restraint and polish
> - Vercel's typography, spacing, monochrome aesthetic, and developer-product precision
> - A premium AI-native product
> - Extremely clean information hierarchy
> - Subtle motion and interaction"

### Prompt 5: Continuity
> "sonnet's limit got over so continue wheere sonnet left , check what it has done and what it was tryna do and contue"

### Prompt 6: LLM Quota & Token Efficiency
> "Optimize the existing autonomous AI agent for LLM quota/token efficiency.
> IMPORTANT: This is a hackathon submission. DO NOT change the product behavior or architecture in ways that could violate the hackathon requirements. DO NOT remove, weaken, or bypass any required capability. FIRST: inspect the existing codebase and understand the complete current flow before modifying anything.
> 
> Hackathon requirements that MUST remain fully intact:
> 1. POST /api/agent/init
> 2. GET /api/agent/feed?agentId=...
> 3. After initialization, the agent must operate autonomously.
> 4. Topic discovery must use live information sources.
> 5. Editorial judgment must remain."

### Prompt 7: Frontend Wiring
> "proceed, also make sure its correcly wired up to the frontend"

### Prompt 8: Production Hardening
> "We need to fix a set of production/runtime issues in the existing AI research agent system.
> IMPORTANT:
> - Do NOT redesign the architecture.
> - Do NOT change unrelated behavior.
> - Do NOT remove existing functionality.
> - Do NOT change database schemas unless absolutely required for the lifecycle-state fix.
> - Do NOT replace providers/models.
> - Do NOT rewrite working components just for style.
> - Preserve all existing APIs, frontend contracts, research flow, evidence grounding, memory/belief synthesis, scheduler behavior, and editorial behavior unless a change below directly requires it.
> - Make the smallest safe changes necessary.
> - Before editing anything, inspect the existing provider abstraction, fallback implementation, runtime/concurrency model, LLM call sites, editorial pipeline, candidate/post lifecycle, and tests.
> - Trace the actual execution path before deciding where to patch."

### Prompt 9 & 10: Surgical Implementation Directive
> "You are modifying an existing production-oriented multi-agent research system.
> MISSION
> =======
> Make ONLY the targeted reliability, provider-compatibility, rate-limit, lifecycle, and LLM-efficiency fixes described below. This is a SURGICAL production-hardening task. DO NOT redesign the architecture. DO NOT rewrite working subsystems. DO NOT change product behavior. DO NOT change prompts unless absolutely required for provider compatibility. DO NOT change research quality, scoring, beliefs, editorial standards, scheduling, feed UX, APIs, or unrelated code. Preserve all existing behavior unless explicitly required by one of the fixes below."

### Prompt 11: Approval & Deployment
> "proceed , just dont break anything"

### Prompt 12: Documentation Generation
> "please write a prompt.md (should not be generic but actual prompts i gavce you) file and readme.md for this whole project"
