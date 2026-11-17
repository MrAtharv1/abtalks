export interface PersonaInput {
  name: string;
  domain: string;
}

export interface AgentInitRequest {
  persona: PersonaInput;
}

export interface AgentInitResponse {
  agentId: string;
}

export interface PostResponse {
  id: string;
  createdAt: string;
  text: string;
  rationale?: string;
  sources: string[];
  status?: string;
  is_candidate?: boolean;
  rejection_reason?: string;
  editorial_score?: number;
  quality_gate_checks?: { name: string; passed: boolean; details: string }[];
}

export interface FeedResponse {
  posts: PostResponse[];
}

export interface AgentStatus {
  state: string;
  agent_id: string;
  budget_snapshot?: any;
  cadence_snapshot?: any;
  status: string;
  runtime_status: string;
  beliefs_count: number;
  posts_count: number;
  cycles_count: number;
}

export interface EvidenceResponse {
  id: string;
  claim: string;
  evidence_text: string;
  relevance_score: number;
  source_quality_score: number;
  confidence: number;
  polarity: string;
  source_url?: string;
  source_title?: string;
}

export interface SourceResponse {
  id: string;
  url: string;
  title?: string;
  domain?: string;
  retrieved_at: string;
}

export interface QuestionResponse {
  id: string;
  question: string;
  status: string;
  importance: number;
  confidence: number;
  evidence: EvidenceResponse[];
}

export interface BeliefRevisionStep {
  cycle: number;
  prevConfidence: number;
  newConfidence: number;
  changeType: 'SUPPORTED' | 'DISPUTED' | 'WEAKENED' | 'INITIAL';
  triggerClaim: string;
  triggerSourceUrl?: string;
  timestamp: string;
}

export interface BeliefResponse {
  id: string;
  statement: string;
  confidence: number;
  importance: number;
  status: string;
  trajectory?: BeliefRevisionStep[];
}

export interface ThreadResponse {
  id: string;
  title: string;
  description: string;
  status: string;
  priority: number;
  questions: QuestionResponse[];
  beliefs: BeliefResponse[];
}

export interface WorkspaceResponse {
  agent_id: string;
  status: string;
  persona: PersonaInput;
  threads: ThreadResponse[];
  sources: SourceResponse[];
}

export interface DemoResearchRun {
  cycle: number;
  timestamp: string;
  topic: string;
  queriesGenerated: string[];
  sourcesAnalyzed: number;
  yieldScore: number;
  beliefUpdates: string[];
  decision: 'POST_PUBLISHED' | 'POST_REJECTED' | 'NO_POST_COOLDOWN';
  rationaleSummary: string;
}
