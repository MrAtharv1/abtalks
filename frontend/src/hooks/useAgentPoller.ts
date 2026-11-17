import { useState, useEffect, useRef, useCallback } from 'react';
import { endpoints } from '../api/endpoints';
import { ApiError } from '../api/client';
import type { FeedResponse, AgentStatus, WorkspaceResponse } from '../types/backend';

const POLL_INTERVAL_MS = 3500;

export function useAgentPoller(agentId: string | null, onNotFound?: () => void) {
  const [feed, setFeed]          = useState<FeedResponse | null>(null);
  const [status, setStatus]      = useState<AgentStatus | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceResponse | null>(null);
  const [error, setError]        = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // Stable ref so poll() closure doesn't go stale
  const agentIdRef = useRef<string | null>(agentId);
  agentIdRef.current = agentId;

  const onNotFoundRef = useRef<(() => void) | undefined>(onNotFound);
  onNotFoundRef.current = onNotFound;

  const intervalRef = useRef<number | null>(null);

  const poll = useCallback(async () => {
    const id = agentIdRef.current;
    if (!id) return;
    try {
      const [feedData, statusData, workspaceData] = await Promise.all([
        endpoints.getFeed(id),
        endpoints.getStatus(id),
        endpoints.getWorkspace(id),
      ]);
      setFeed(feedData);
      setStatus(statusData);
      setWorkspace(workspaceData);
      setError(null);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 404) {
        if (onNotFoundRef.current) {
          onNotFoundRef.current();
          return;
        }
      }
      const msg = err instanceof Error ? err.message : 'Failed to fetch';
      // Keep stale data visible — only update the error banner
      setError(msg);
    }
  }, []);

  // Effect 1: initial fetch when agentId first appears / changes
  useEffect(() => {
    if (!agentId) {
      setFeed(null);
      setStatus(null);
      setWorkspace(null);
      setError(null);
      return;
    }
    poll();
  }, [agentId, poll]);

  // Effect 2: polling interval — independent of initial fetch
  useEffect(() => {
    if (!agentId || !isPolling) {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    intervalRef.current = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [agentId, isPolling, poll]);

  return { feed, status, workspace, error, isPolling, setIsPolling, forceRefresh: poll };
}
