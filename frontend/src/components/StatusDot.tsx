// Status indicator reflecting real backend states
// Backend states: state (runtime), status (db), runtime_status
// We never invent states — only what the backend returns.

interface StatusDotProps {
  state: string;       // runtime state machine state
  dbStatus: string;   // db status: ACTIVE | STOPPED
  size?: 'sm' | 'md';
  showLabel?: boolean;
}

function getStatusConfig(state: string, dbStatus: string) {
  const s = (state || '').toUpperCase();
  const db = (dbStatus || '').toUpperCase();

  if (db === 'STOPPED' || s === 'STOPPED') {
    return { color: '#a1a1aa', label: 'Stopped', pulse: false };
  }
  if (s === 'RUNNING' || s === 'STARTING' || db === 'ACTIVE') {
    return { color: '#22c55e', label: 'Active', pulse: true };
  }
  if (s === 'COOLDOWN') {
    return { color: '#22c55e', label: 'Active', pulse: false };
  }
  if (s === 'BACKOFF') {
    return { color: '#f59e0b', label: 'Backing off', pulse: true };
  }
  if (s === 'BUDGET_EXHAUSTED') {
    return { color: '#ef4444', label: 'Budget limit', pulse: false };
  }
  if (s === 'STOPPING') {
    return { color: '#f59e0b', label: 'Stopping…', pulse: true };
  }
  return { color: '#a1a1aa', label: s || 'Unknown', pulse: false };
}

export function StatusDot({ state, dbStatus, size = 'md', showLabel = true }: StatusDotProps) {
  const { color, label, pulse } = getStatusConfig(state, dbStatus);
  const dotSize = size === 'sm' ? 6 : 8;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: size === 'sm' ? 12 : 13,
        color: '#71717a',
        fontWeight: 500,
        letterSpacing: '-0.01em',
      }}
    >
      <span
        style={{
          display: 'inline-block',
          width: dotSize,
          height: dotSize,
          borderRadius: '50%',
          backgroundColor: color,
          flexShrink: 0,
          animation: pulse ? 'pulse-dot 2s ease-in-out infinite' : 'none',
        }}
      />
      {showLabel && label}
    </span>
  );
}
