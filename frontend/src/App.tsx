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
  } = useAgentState();

  // No agent yet — show creation screen
  if (!agentId) {
    return (
      <CreateAgent
        onInit={initAgent}
        isInitializing={isInitializing}
      />
    );
  }

  // Agent exists — show workspace (wired to real backend)
  return (
    <AgentWorkspace
      agentId={agentId}
      status={status}
      workspace={workspace}
      feed={feed}
      error={error}
      isStarting={isStarting}
      isStopping={isStopping}
      onStart={startAgent}
      onStop={stopAgent}
      onReset={resetAgent}
    />
  );
}

export default App;
