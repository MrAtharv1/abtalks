import { fetchApi } from './client';
import type {
  AgentInitRequest,
  AgentInitResponse,
  FeedResponse,
  AgentStatus,
  WorkspaceResponse,
} from '../types/backend';

export const endpoints = {
  initAgent: (data: AgentInitRequest) =>
    fetchApi<AgentInitResponse>('/api/agent/init', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  startAgent: (agentId: string) =>
    fetchApi<{ status: string }>(`/api/agent/${agentId}/start`, {
      method: 'POST',
    }),

  stopAgent: (agentId: string) =>
    fetchApi<{ status: string }>(`/api/agent/${agentId}/stop`, {
      method: 'POST',
    }),

  getFeed: (agentId: string) =>
    fetchApi<FeedResponse>(`/api/agent/feed?agentId=${agentId}`),

  getStatus: (agentId: string) =>
    fetchApi<AgentStatus>(`/api/agent/status?agentId=${agentId}`),

  getWorkspace: (agentId: string) =>
    fetchApi<WorkspaceResponse>(`/api/agent/${agentId}/workspace`),
};
