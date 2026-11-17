import { useState, useCallback, useEffect } from 'react';
import { endpoints } from '../api/endpoints';
import { useAgentPoller } from './useAgentPoller';
import type { AgentInitRequest } from '../types/backend';
import {
  DEMO_AGENT_ID,
  DEMO_FEED,
  DEMO_STATUS,
  DEMO_WORKSPACE,
} from '../data/demoResearchData';

const STORAGE_KEY = 'thread_agent_id';
const DEMO_MODE_KEY = 'thread_demo_mode';

export function useAgentState() {
  const [liveAgentId, setLiveAgentId] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY)
  );
  const [isDemoMode, setIsDemoMode] = useState<boolean>(() =>
    localStorage.getItem(DEMO_MODE_KEY) === 'true'
  );
  const [isInitializing, setIsInitializing] = useState(false);
  const [isStarting,     setIsStarting]     = useState(false);
  const [isStopping,     setIsStopping]     = useState(false);

  const handleNotFound = useCallback(() => {
    setLiveAgentId(null);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  // When in demo mode, do not poll live backend
  const activePollerId = isDemoMode ? null : liveAgentId;
  const poller = useAgentPoller(activePollerId, handleNotFound);

  // Persist live agentId
  useEffect(() => {
    if (liveAgentId) {
      localStorage.setItem(STORAGE_KEY, liveAgentId);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [liveAgentId]);

  // Persist demo mode
  useEffect(() => {
    if (isDemoMode) {
      localStorage.setItem(DEMO_MODE_KEY, 'true');
    } else {
      localStorage.removeItem(DEMO_MODE_KEY);
    }
  }, [isDemoMode]);

  // Drive polling from real backend state when not in demo mode
  useEffect(() => {
    if (isDemoMode) return;
    if (!poller.status) return;
    const isActive =
      poller.status.status === 'ACTIVE' ||
      (poller.status.state !== 'STOPPED' && poller.status.state !== '');
    if (isActive && !poller.isPolling) {
      poller.setIsPolling(true);
    } else if (!isActive && poller.isPolling && !isStarting) {
      poller.setIsPolling(false);
    }
  }, [isDemoMode, poller.status?.status, poller.status?.state, isStarting]);

  const initAgent = useCallback(async (req: AgentInitRequest) => {
    setIsInitializing(true);
    try {
      const res = await endpoints.initAgent(req);
      setLiveAgentId(res.agentId);
      setIsDemoMode(false);
      poller.setIsPolling(true);
    } finally {
      setIsInitializing(false);
    }
  }, [poller]);

  const startAgent = useCallback(async () => {
    if (isDemoMode || !liveAgentId || isStarting) return;
    setIsStarting(true);
    try {
      await endpoints.startAgent(liveAgentId);
      poller.setIsPolling(true);
      await poller.forceRefresh();
    } finally {
      setIsStarting(false);
    }
  }, [isDemoMode, liveAgentId, isStarting, poller]);

  const stopAgent = useCallback(async () => {
    if (isDemoMode || !liveAgentId || isStopping) return;
    setIsStopping(true);
    try {
      await endpoints.stopAgent(liveAgentId);
      await poller.forceRefresh();
      poller.setIsPolling(false);
    } finally {
      setIsStopping(false);
    }
  }, [isDemoMode, liveAgentId, isStopping, poller]);

  const resetAgent = useCallback(() => {
    setLiveAgentId(null);
    setIsDemoMode(false);
    poller.setIsPolling(false);
  }, [poller]);

  const enableDemoMode = useCallback(() => {
    setIsDemoMode(true);
    poller.setIsPolling(false);
  }, [poller]);

  const disableDemoMode = useCallback(() => {
    setIsDemoMode(false);
    if (liveAgentId) {
      poller.setIsPolling(true);
    }
  }, [liveAgentId, poller]);

  const activeAgentId = isDemoMode ? DEMO_AGENT_ID : liveAgentId;
  const activeStatus = isDemoMode ? DEMO_STATUS : poller.status;
  const activeWorkspace = isDemoMode ? DEMO_WORKSPACE : poller.workspace;
  const activeFeed = isDemoMode ? DEMO_FEED : poller.feed;
  const activeError = isDemoMode ? null : poller.error;

  return {
    agentId: activeAgentId,
    liveAgentId,
    isDemoMode,
    enableDemoMode,
    disableDemoMode,
    isInitializing,
    isStarting,
    isStopping,
    initAgent,
    startAgent,
    stopAgent,
    resetAgent,
    status: activeStatus,
    workspace: activeWorkspace,
    feed: activeFeed,
    error: activeError,
    isPolling: isDemoMode ? false : poller.isPolling,
    setIsPolling: poller.setIsPolling,
    forceRefresh: poller.forceRefresh,
  };
}
