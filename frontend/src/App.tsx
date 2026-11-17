import { useAgentState } from './hooks/useAgentState';
import { CreateAgent } from './components/CreateAgent';
import { AgentWorkspace } from './components/AgentWorkspace';

function App() {
  const {
    agentId,
    isInitializing,
    isStarting,
    isStopping,
    initAgent,
    startAgent,
    stopAgent,
    resetAgent,
    status,
    workspace,
    feed,
    error,
    isDemoMode,
    enableDemoMode,
    disableDemoMode,
  } = useAgentState();

  // No agent yet and not in demo mode — show creation screen
  if (!agentId && !isDemoMode) {
    return (
      <CreateAgent
        onInit={initAgent}
        isInitializing={isInitializing}
        onEnableDemo={enableDemoMode}
      />
    );
  }

  // Agent exists or Demo Mode active — show workspace
  return (
    <AgentWorkspace
      agentId={agentId || 'demo-agent'}
      status={status}
      workspace={workspace}
      feed={feed}
      error={error}
      isStarting={isStarting}
      isStopping={isStopping}
      isDemoMode={isDemoMode}
      onStart={startAgent}
      onStop={stopAgent}
      onReset={resetAgent}
      onExitDemo={disableDemoMode}
    />
  );
}

export default App;
