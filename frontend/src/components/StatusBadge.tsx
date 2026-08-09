// StatusBadge: only reflects real backend states
// state = runtime state machine (RUNNING, STOPPED, COOLDOWN, BACKOFF, BUDGET_EXHAUSTED, STOPPING)
// dbStatus = DB status column (ACTIVE, STOPPED)

interface StatusBadgeProps {
  state:    string;
  dbStatus: string;
}

function getConfig(state: string, dbStatus: string) {
  const s  = (state    || '').toUpperCase();
  const db = (dbStatus || '').toUpperCase();

  if (db === 'STOPPED' && s !== 'RUNNING') {
    return { label: 'Stopped', color: 'var(--color-stopped)', pulse: false };
  }
  if (s === 'RUNNING'  || db === 'ACTIVE') {
    return { label: 'Active',        color: 'var(--color-active)',  pulse: true  };
  }
  if (s === 'COOLDOWN') {
    return { label: 'Active',        color: 'var(--color-active)',  pulse: false };
  }
  if (s === 'BACKOFF')  {
    return { label: 'Backing off',   color: 'var(--color-warning)', pulse: true  };
  }
  if (s === 'BUDGET_EXHAUSTED') {
    return { label: 'Budget limit',  color: 'var(--color-error)',   pulse: false };
  }
  if (s === 'STOPPING') {
    return { label: 'Stopping…',     color: 'var(--color-warning)', pulse: true  };
  }
  return   { label: 'Stopped',       color: 'var(--color-stopped)', pulse: false };
}

export function StatusBadge({ state, dbStatus }: StatusBadgeProps) {
  const { label, color, pulse } = getConfig(state, dbStatus);

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      fontSize: 12,
      fontWeight: 500,
      color: 'var(--color-text-secondary)',
      letterSpacing: '-0.01em',
    }}>
      <span style={{
        display: 'inline-block',
        width: 7,
        height: 7,
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
        animation: pulse ? 'pulse-active 2s ease-in-out infinite' : 'none',
      }} />
      {label}
    </span>
  );
}
