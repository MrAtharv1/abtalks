import type { WorkspaceResponse } from '../types/backend';

interface WorkspacePanelProps {
  workspace: WorkspaceResponse;
}

export function WorkspacePanel({ workspace }: WorkspacePanelProps) {
  const { threads, sources } = workspace;
  const activeThread = threads.find(t => t.status === 'ACTIVE') ?? threads[0] ?? null;

  return (
    <div style={{ padding: '24px 0' }}>
      {/* Research threads */}
      {threads.length === 0 ? (
        <EmptySection label="Research Threads" message="No research threads yet." />
      ) : (
        <section style={{ marginBottom: 36 }}>
          <SectionLabel>Research Threads</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 14 }}>
            {threads.map(thread => (
              <ThreadCard key={thread.id} thread={thread} />
            ))}
          </div>
        </section>
      )}

      {/* Active questions */}
      {activeThread && activeThread.questions.length > 0 && (
        <section style={{ marginBottom: 36 }}>
          <SectionLabel>Open Questions</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
            {activeThread.questions
              .filter(q => q.status === 'OPEN' || q.status === 'IN_PROGRESS')
              .slice(0, 6)
              .map(q => (
                <div key={q.id} style={{
                  padding: '10px 14px',
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 8,
                }}>
                  <p style={{
                    fontSize: 13,
                    color: 'var(--color-text)',
                    lineHeight: 1.55,
                    marginBottom: q.evidence.length > 0 ? 6 : 0,
                  }}>
                    {q.question}
                  </p>
                  {q.evidence.length > 0 && (
                    <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                      {q.evidence.length} evidence item{q.evidence.length !== 1 ? 's' : ''} collected
                    </p>
                  )}
                </div>
              ))}
          </div>
        </section>
      )}

      {/* Beliefs */}
      {activeThread && activeThread.beliefs.length > 0 && (
        <section style={{ marginBottom: 36 }}>
          <SectionLabel>Formed Beliefs</SectionLabel>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
            {activeThread.beliefs.slice(0, 8).map(belief => (
              <div key={belief.id} style={{
                padding: '10px 14px',
                border: '1px solid var(--color-border)',
                borderRadius: 8,
              }}>
                <p style={{
                  fontSize: 13,
                  color: 'var(--color-text)',
                  lineHeight: 1.55,
                  marginBottom: 6,
                }}>
                  {belief.statement}
                </p>
                <ConfidenceBar value={belief.confidence} />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Sources */}
      {sources.length > 0 && (
        <section>
          <SectionLabel>Discovered Sources</SectionLabel>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 8,
            marginTop: 14,
          }}>
            {sources.slice(0, 12).map(source => {
              let label = source.title || source.domain || '';
              if (!label) {
                try {
                  label = new URL(source.url).hostname.replace(/^www\./, '');
                } catch { label = source.url; }
              }
              return (
                <a
                  key={source.id}
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: 'block',
                    padding: '10px 12px',
                    background: 'var(--color-bg-subtle)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 8,
                    textDecoration: 'none',
                    transition: 'border-color 0.15s',
                    overflow: 'hidden',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--color-border-strong)'; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--color-border)'; }}
                >
                  <p style={{
                    fontSize: 12,
                    fontWeight: 500,
                    color: 'var(--color-text)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    marginBottom: 2,
                  }}>
                    {label}
                  </p>
                  <p style={{
                    fontSize: 11,
                    color: 'var(--color-text-tertiary)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {source.url}
                  </p>
                </a>
              );
            })}
          </div>
        </section>
      )}

      {threads.length === 0 && sources.length === 0 && (
        <p style={{
          fontSize: 13,
          color: 'var(--color-text-tertiary)',
          lineHeight: 1.6,
          paddingTop: 8,
        }}>
          Research workspace is initializing.
          <br />
          Threads and sources will appear as the agent works.
        </p>
      )}
    </div>
  );
}

function ThreadCard({ thread }: { thread: WorkspaceResponse['threads'][0] }) {
  const isActive = thread.status === 'ACTIVE';
  return (
    <div style={{
      padding: '14px 16px',
      background: 'var(--color-bg)',
      border: '1px solid var(--color-border)',
      borderRadius: 9,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <div style={{
          marginTop: 4,
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: isActive ? 'var(--color-active)' : 'var(--color-stopped)',
          flexShrink: 0,
          animation: isActive ? 'pulse-active 2s ease-in-out infinite' : 'none',
        }} />
        <div>
          <p style={{
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--color-text)',
            letterSpacing: '-0.01em',
            marginBottom: 3,
          }}>
            {thread.title}
          </p>
          {thread.description && (
            <p style={{
              fontSize: 12,
              color: 'var(--color-text-secondary)',
              lineHeight: 1.5,
              marginBottom: 8,
            }}>
              {thread.description}
            </p>
          )}
          <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
            {thread.questions.length} questions · {thread.beliefs.length} beliefs
          </p>
        </div>
      </div>
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const color = pct >= 60 ? 'var(--color-active)' : pct >= 40 ? 'var(--color-warning)' : 'var(--color-error)';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        flex: 1,
        height: 3,
        background: 'var(--color-bg-muted)',
        borderRadius: 2,
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: color,
          borderRadius: 2,
          transition: 'width 0.4s ease',
        }} />
      </div>
      <span style={{ fontSize: 10, color: 'var(--color-text-tertiary)', minWidth: 28, textAlign: 'right' }}>
        {pct}%
      </span>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p style={{
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: '0.07em',
      textTransform: 'uppercase',
      color: 'var(--color-text-tertiary)',
    }}>
      {children}
    </p>
  );
}

import React from 'react';

function EmptySection({ label, message }: { label: string; message: string }) {
  return (
    <section style={{ marginBottom: 28 }}>
      <SectionLabel>{label}</SectionLabel>
      <p style={{ marginTop: 12, fontSize: 13, color: 'var(--color-text-tertiary)' }}>{message}</p>
    </section>
  );
}
