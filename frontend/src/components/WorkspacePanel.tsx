import React, { useState } from 'react';
import type { WorkspaceResponse } from '../types/backend';
import { DEMO_RUNS } from '../data/demoResearchData';

interface WorkspacePanelProps {
  workspace: WorkspaceResponse;
  isDemoMode?: boolean;
}

export function WorkspacePanel({ workspace, isDemoMode }: WorkspacePanelProps) {
  const { threads, sources } = workspace;
  const activeThread = threads.find(t => t.status === 'ACTIVE') ?? threads[0] ?? null;

  // Belief filtering state
  const [beliefFilter, setBeliefFilter] = useState<'ALL' | 'ACTIVE' | 'DISPUTED' | 'WEAKENED'>('ALL');
  const [selectedBeliefId, setSelectedBeliefId] = useState<string | null>(null);

  // Question expansion state
  const [expandedQuestionId, setExpandedQuestionId] = useState<string | null>(null);

  // Cycle run trace state
  const [selectedCycle, setSelectedCycle] = useState<number>(5);

  const allBeliefs = activeThread?.beliefs ?? [];
  const filteredBeliefs = allBeliefs.filter(b => {
    if (beliefFilter === 'ALL') return true;
    return b.status === beliefFilter;
  });

  const activeCount = allBeliefs.filter(b => b.status === 'ACTIVE').length;
  const disputedCount = allBeliefs.filter(b => b.status === 'DISPUTED').length;
  const weakenedCount = allBeliefs.filter(b => b.status === 'WEAKENED').length;

  return (
    <div style={{ padding: '24px 0' }}>
      {/* ─── Autonomous Cycles Trace (Demo Mode / Multi-Cycle History) ──────── */}
      {isDemoMode && DEMO_RUNS.length > 0 && (
        <section style={{
          marginBottom: 36,
          padding: '18px 20px',
          background: 'var(--color-bg-subtle)',
          border: '1px solid var(--color-border)',
          borderRadius: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <div>
              <SectionLabel>Autonomous Cycles Execution Trace</SectionLabel>
              <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                Inspect real multi-cycle query planning, evidence yield tracking, and editorial decisions.
              </p>
            </div>
            <span style={{
              fontSize: 11,
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: 12,
              background: '#ede9fe',
              color: '#6d28d9',
            }}>
              5 Autonomous Cycles
            </span>
          </div>

          {/* Cycle selector buttons */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 16, overflowX: 'auto', paddingBottom: 4 }}>
            {DEMO_RUNS.map(run => {
              const isSelected = selectedCycle === run.cycle;
              return (
                <button
                  key={run.cycle}
                  type="button"
                  onClick={() => setSelectedCycle(run.cycle)}
                  style={{
                    padding: '6px 12px',
                    fontSize: 12,
                    fontWeight: isSelected ? 600 : 500,
                    borderRadius: 7,
                    border: '1px solid',
                    borderColor: isSelected ? 'var(--color-text)' : 'var(--color-border)',
                    background: isSelected ? 'var(--color-text)' : 'var(--color-bg)',
                    color: isSelected ? '#ffffff' : 'var(--color-text-secondary)',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    transition: 'all 0.15s ease',
                  }}
                >
                  Cycle {run.cycle} {run.decision === 'POST_PUBLISHED' ? '📰' : run.decision === 'POST_REJECTED' ? '🛡️' : '⏱️'}
                </button>
              );
            })}
          </div>

          {/* Selected Cycle Details */}
          {(() => {
            const run = DEMO_RUNS.find(r => r.cycle === selectedCycle) ?? DEMO_RUNS[DEMO_RUNS.length - 1];
            return (
              <div style={{
                background: 'var(--color-bg)',
                border: '1px solid var(--color-border)',
                borderRadius: 8,
                padding: '14px 16px',
                fontSize: 12,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div>
                    <span style={{ fontWeight: 600, color: 'var(--color-text)', fontSize: 13 }}>
                      Cycle {run.cycle}: {run.topic}
                    </span>
                    <p style={{ color: 'var(--color-text-tertiary)', fontSize: 11, marginTop: 2 }}>
                      Executed at {new Date(run.timestamp).toUTCString()}
                    </p>
                  </div>
                  <span style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '2px 7px',
                    borderRadius: 4,
                    textTransform: 'uppercase',
                    background: run.decision === 'POST_PUBLISHED' ? '#dcfce7' : run.decision === 'POST_REJECTED' ? '#fee2e2' : '#f3f4f6',
                    color: run.decision === 'POST_PUBLISHED' ? '#15803d' : run.decision === 'POST_REJECTED' ? '#b91c1c' : '#4b5563',
                  }}>
                    {run.decision.replace(/_/g, ' ')}
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10, marginBottom: 12 }}>
                  <div style={{ padding: '8px 10px', background: 'var(--color-bg-subtle)', borderRadius: 6 }}>
                    <span style={{ color: 'var(--color-text-tertiary)', fontSize: 11 }}>Research Yield Score</span>
                    <p style={{ fontWeight: 600, color: 'var(--color-text)', margin: '2px 0 0', fontSize: 13 }}>
                      {run.yieldScore.toFixed(2)} / 1.00
                    </p>
                  </div>
                  <div style={{ padding: '8px 10px', background: 'var(--color-bg-subtle)', borderRadius: 6 }}>
                    <span style={{ color: 'var(--color-text-tertiary)', fontSize: 11 }}>Sources Analyzed</span>
                    <p style={{ fontWeight: 600, color: 'var(--color-text)', margin: '2px 0 0', fontSize: 13 }}>
                      {run.sourcesAnalyzed} verified sources
                    </p>
                  </div>
                </div>

                <div style={{ marginBottom: 10 }}>
                  <span style={{ fontWeight: 600, color: 'var(--color-text)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Generated Query Plan
                  </span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 4 }}>
                    {run.queriesGenerated.map((q, idx) => (
                      <span key={idx} style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--color-text-secondary)', background: 'var(--color-bg-subtle)', padding: '3px 8px', borderRadius: 4 }}>
                        🔍 "{q}"
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <span style={{ fontWeight: 600, color: 'var(--color-text)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Editorial Outcome & Rationale
                  </span>
                  <p style={{ margin: '4px 0 0', color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
                    {run.rationaleSummary}
                  </p>
                </div>
              </div>
            );
          })()}
        </section>
      )}

      {/* ─── Research Threads ────────────────────────────────────────── */}
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

      {/* ─── Formed Beliefs & Trajectories (Interactive) ─────────────── */}
      {activeThread && activeThread.beliefs.length > 0 && (
        <section style={{ marginBottom: 36 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
            <div>
              <SectionLabel>Formed Beliefs & Trajectories</SectionLabel>
              <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2 }}>
                The agent's evolving worldview. Click any belief to inspect its confidence revisions.
              </p>
            </div>
          </div>

          {/* Belief Filter Pills */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
            <PillButton label={`All (${allBeliefs.length})`} active={beliefFilter === 'ALL'} onClick={() => setBeliefFilter('ALL')} />
            <PillButton label={`Active (${activeCount})`} active={beliefFilter === 'ACTIVE'} onClick={() => setBeliefFilter('ACTIVE')} />
            <PillButton label={`Disputed (${disputedCount})`} active={beliefFilter === 'DISPUTED'} onClick={() => setBeliefFilter('DISPUTED')} highlight="disputed" />
            <PillButton label={`Weakened (${weakenedCount})`} active={beliefFilter === 'WEAKENED'} onClick={() => setBeliefFilter('WEAKENED')} highlight="weakened" />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {filteredBeliefs.map(belief => {
              const isSelected = selectedBeliefId === belief.id;
              const statusColor = belief.status === 'DISPUTED' ? '#b91c1c' : belief.status === 'WEAKENED' ? '#c2410c' : '#15803d';
              const statusBg = belief.status === 'DISPUTED' ? '#fef2f2' : belief.status === 'WEAKENED' ? '#fff7ed' : '#f0fdf4';

              return (
                <div
                  key={belief.id}
                  onClick={() => setSelectedBeliefId(isSelected ? null : belief.id)}
                  style={{
                    padding: '12px 14px',
                    border: '1px solid',
                    borderColor: isSelected ? 'var(--color-text)' : 'var(--color-border)',
                    borderRadius: 8,
                    background: isSelected ? 'var(--color-bg-subtle)' : 'var(--color-bg)',
                    cursor: 'pointer',
                    transition: 'border-color 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, marginBottom: 6 }}>
                    <p style={{
                      fontSize: 13,
                      fontWeight: 500,
                      color: 'var(--color-text)',
                      lineHeight: 1.55,
                      margin: 0,
                      flex: 1,
                    }}>
                      {belief.statement}
                    </p>
                    <span style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: '2px 6px',
                      borderRadius: 4,
                      background: statusBg,
                      color: statusColor,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      whiteSpace: 'nowrap',
                    }}>
                      {belief.status}
                    </span>
                  </div>

                  <ConfidenceBar value={belief.confidence} />

                  {/* Expanded Trajectory Timeline */}
                  {isSelected && belief.trajectory && belief.trajectory.length > 0 && (
                    <div style={{
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: '1px solid var(--color-border)',
                      fontSize: 11,
                    }}>
                      <span style={{ fontWeight: 600, color: 'var(--color-text)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Confidence Trajectory (Belief Engine History)
                      </span>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
                        {belief.trajectory.map((step, idx) => (
                          <div key={idx} style={{
                            padding: '8px 10px',
                            background: 'var(--color-bg)',
                            border: '1px solid var(--color-border)',
                            borderRadius: 6,
                          }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                              <span style={{ fontWeight: 600, color: 'var(--color-text)' }}>
                                Cycle {step.cycle} · {step.changeType}
                              </span>
                              <span style={{ fontFamily: 'monospace', fontWeight: 600, color: step.newConfidence > step.prevConfidence ? '#15803d' : step.newConfidence < step.prevConfidence ? '#b91c1c' : 'var(--color-text-secondary)' }}>
                                {(step.prevConfidence * 100).toFixed(0)}% → {(step.newConfidence * 100).toFixed(0)}%
                              </span>
                            </div>
                            <p style={{ margin: '0 0 4px', color: 'var(--color-text-secondary)', lineHeight: 1.4 }}>
                              {step.triggerClaim}
                            </p>
                            {step.triggerSourceUrl && (
                              <a
                                href={step.triggerSourceUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={e => e.stopPropagation()}
                                style={{ color: '#8b5cf6', textDecoration: 'none', fontWeight: 500, fontSize: 11 }}
                              >
                                ↗ View Source Citation
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {!isSelected && belief.trajectory && belief.trajectory.length > 0 && (
                    <p style={{ margin: '6px 0 0', fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                      Click to view {belief.trajectory.length} revision steps ▸
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ─── Active Questions & Evidence Citations (Interactive) ─────── */}
      {activeThread && activeThread.questions.length > 0 && (
        <section style={{ marginBottom: 36 }}>
          <SectionLabel>Open Questions & Verified Evidence</SectionLabel>
          <p style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 2, marginBottom: 12 }}>
            Click any question to view its extracted, verbatim-grounded evidence items.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {activeThread.questions.map(q => {
              const isExpanded = expandedQuestionId === q.id;

              return (
                <div
                  key={q.id}
                  onClick={() => setExpandedQuestionId(isExpanded ? null : q.id)}
                  style={{
                    padding: '12px 14px',
                    background: isExpanded ? 'var(--color-bg-subtle)' : 'var(--color-bg)',
                    border: '1px solid',
                    borderColor: isExpanded ? 'var(--color-text)' : 'var(--color-border)',
                    borderRadius: 8,
                    cursor: 'pointer',
                    transition: 'border-color 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                    <p style={{
                      fontSize: 13,
                      fontWeight: 500,
                      color: 'var(--color-text)',
                      lineHeight: 1.55,
                      margin: 0,
                    }}>
                      {q.question}
                    </p>
                    <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)', whiteSpace: 'nowrap' }}>
                      {q.evidence.length} citation{q.evidence.length !== 1 ? 's' : ''} {isExpanded ? '▲' : '▼'}
                    </span>
                  </div>

                  {/* Expanded Evidence List */}
                  {isExpanded && q.evidence.length > 0 && (
                    <div style={{
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: '1px solid var(--color-border)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                    }}>
                      {q.evidence.map(ev => {
                        const isContradiction = ev.polarity === 'CONTRADICTS';
                        const polarityColor = isContradiction ? '#b91c1c' : '#15803d';
                        const polarityBg = isContradiction ? '#fef2f2' : '#f0fdf4';

                        return (
                          <div
                            key={ev.id}
                            style={{
                              padding: '10px 12px',
                              background: 'var(--color-bg)',
                              border: '1px solid var(--color-border)',
                              borderRadius: 6,
                              fontSize: 12,
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                              <span style={{
                                fontSize: 10,
                                fontWeight: 700,
                                padding: '2px 6px',
                                borderRadius: 4,
                                background: polarityBg,
                                color: polarityColor,
                                textTransform: 'uppercase',
                              }}>
                                {ev.polarity}
                              </span>
                              <span style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                                Source Quality: {Math.round(ev.source_quality_score * 100)}%
                              </span>
                            </div>

                            <p style={{ fontWeight: 600, color: 'var(--color-text)', margin: '0 0 6px', lineHeight: 1.4 }}>
                              {ev.claim}
                            </p>

                            <blockquote style={{
                              margin: '0 0 8px',
                              padding: '6px 10px',
                              background: 'var(--color-bg-subtle)',
                              borderLeft: '3px solid var(--color-border-strong)',
                              fontStyle: 'italic',
                              color: 'var(--color-text-secondary)',
                              fontSize: 11,
                              lineHeight: 1.5,
                            }}>
                              "{ev.evidence_text}"
                            </blockquote>

                            {ev.source_url && (
                              <a
                                href={ev.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={e => e.stopPropagation()}
                                style={{ color: '#8b5cf6', textDecoration: 'none', fontWeight: 500, fontSize: 11 }}
                              >
                                ↗ {ev.source_title || ev.source_url}
                              </a>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ─── Discovered Sources ──────────────────────────────────────── */}
      {sources.length > 0 && (
        <section>
          <SectionLabel>Discovered Sources</SectionLabel>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
            gap: 8,
            marginTop: 14,
          }}>
            {sources.map(source => {
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
                    transition: 'border-color 0.15s ease',
                    overflow: 'hidden',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.borderColor = 'var(--color-text)'; }}
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
                    margin: 0,
                  }}>
                    {source.url}
                  </p>
                </a>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}

function PillButton({
  label, active, onClick, highlight,
}: { label: string; active: boolean; onClick: () => void; highlight?: 'disputed' | 'weakened' }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: '4px 10px',
        fontSize: 11,
        fontWeight: active ? 600 : 500,
        borderRadius: 20,
        border: '1px solid',
        borderColor: active
          ? 'var(--color-text)'
          : highlight === 'disputed'
          ? '#fecdd3'
          : highlight === 'weakened'
          ? '#fed7aa'
          : 'var(--color-border)',
        background: active
          ? 'var(--color-text)'
          : highlight === 'disputed'
          ? '#fff1f2'
          : highlight === 'weakened'
          ? '#fff7ed'
          : 'var(--color-bg-subtle)',
        color: active
          ? '#ffffff'
          : highlight === 'disputed'
          ? '#9f1239'
          : highlight === 'weakened'
          ? '#9a3412'
          : 'var(--color-text-secondary)',
        cursor: 'pointer',
        fontFamily: 'inherit',
        transition: 'all 0.15s ease',
      }}
    >
      {label}
    </button>
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
          <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)', margin: 0 }}>
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
      margin: 0,
    }}>
      {children}
    </p>
  );
}

function EmptySection({ label, message }: { label: string; message: string }) {
  return (
    <section style={{ marginBottom: 28 }}>
      <SectionLabel>{label}</SectionLabel>
      <p style={{ marginTop: 12, fontSize: 13, color: 'var(--color-text-tertiary)' }}>{message}</p>
    </section>
  );
}
