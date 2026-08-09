import { useState, useCallback, useEffect } from 'react';
import { endpoints } from '../api/endpoints';
import { useAgentPoller } from './useAgentPoller';
import type { AgentInitRequest } from '../types/backend';

const STORAGE_KEY = 'thread_agent_id';

export function useAgentState() {
  const [agentId, setAgentId] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY)
  );
  const [isInitializing, setIsInitializing] = useState(false);
  const [isStarting,     setIsStarting]     = useState(false);
  const [isStopping,     setIsStopping]     = useState(false);

  const poller = useAgentPoller(agentId);

  // Persist agentId
  useEffect(() => {
    if (agentId) {
      localStorage.setItem(STORAGE_KEY, agentId);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [agentId]);

  // Drive polling from real backend state.
  // Backend auto-starts on init so agent is ACTIVE immediately.
  useEffect(() => {
    if (!poller.status) return;
    const isActive =
      poller.status.status === 'ACTIVE' ||
      (poller.status.state !== 'STOPPED' && poller.status.state !== '');
    if (isActive && !poller.isPolling) {
      poller.setIsPolling(true);
    } else if (!isActive && poller.isPolling && !isStarting) {
      poller.setIsPolling(false);
    }
  }, [poller.status?.status, poller.status?.state, isStarting]);

  const initAgent = useCallback(async (req: AgentInitRequest) => {
    setIsInitializing(true);
    try {
      const res = await endpoints.initAgent(req);
      setAgentId(res.agentId);
      // Backend is now ACTIVE. Start polling immediately.
      poller.setIsPolling(true);
    } finally {
      setIsInitializing(false);
    }
  }, [poller]);

  const startAgent = useCallback(async () => {
    if (!agentId || isStarting) return;
    setIsStarting(true);
    try {
      await endpoints.startAgent(agentId);
      poller.setIsPolling(true);
      await poller.forceRefresh();
    } finally {
      setIsStarting(false);
    }
  }, [agentId, isStarting, poller]);

  const stopAgent = useCallback(async () => {
    if (!agentId || isStopping) return;
    setIsStopping(true);
    try {
      await endpoints.stopAgent(agentId);
      await poller.forceRefresh();
      poller.setIsPolling(false);
    } finally {
      setIsStopping(false);
    }
  }, [agentId, isStopping, poller]);

  const resetAgent = useCallback(() => {
    setAgentId(null);
    poller.setIsPolling(false);
  }, [poller]);

  return {
    agentId,
    isInitializing,
    isStarting,
    isStopping,
    initAgent,
    startAgent,
    stopAgent,
    resetAgent,
    ...poller,
  };
}
