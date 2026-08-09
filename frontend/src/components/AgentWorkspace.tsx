import { useState } from 'react';
import { StatusBadge } from './StatusBadge';
import { FeedPanel } from './FeedPanel';
import { WorkspacePanel } from './WorkspacePanel';
import { Spinner } from './CreateAgent';
import type { AgentStatus, WorkspaceResponse, FeedResponse } from '../types/backend';

type Tab = 'feed' | 'workspace';

interface AgentWorkspaceProps {
  agentId:    string;
  status:     AgentStatus | null;
  workspace:  WorkspaceResponse | null;
  feed:       FeedResponse | null;
  error:      string | null;
  isStarting: boolean;
  isStopping: boolean;
  onStart:    () => void;
  onStop:     () => void;
  onReset:    () => void;
}

export function AgentWorkspace({
  agentId, status, workspace, feed, error,
  isStarting, isStopping, onStart, onStop, onReset,
}: AgentWorkspaceProps) {
  const [tab, setTab] = useState<Tab>('feed');
  const [showMenu, setShowMenu] = useState(false);

  const isActive  = status?.status === 'ACTIVE';
  const runtimeState = status?.state ?? '';
  const dbStatus     = status?.status ?? 'STOPPED';

  const personaName   = workspace?.persona?.name   ?? '';
  const personaDomain = workspace?.persona?.domain  ?? '';

  // Loading state — workspace not yet fetched
  if (!workspace || !status) {
    return (
      <div style={{
        minHeight: '100dvh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--color-bg)',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ marginBottom: 16 }}>
            <Spinner />
          </div>
          <p style={{ fontSize: 13, color: 'var(--color-text-secondary)' }}>
            Loading workspace…
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100dvh',
      background: 'var(--color-bg)',
      overflow: 'hidden',
    }}>
      {/* ─── Top Header ─────────────────────────────────────────────── */}
      <header style={{
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        height: 52,
        borderBottom: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        position: 'relative',
        zIndex: 10,
      }}>
        {/* Wordmark */}
        <span style={{
          fontSize: 13,
          fontWeight: 700,
          letterSpacing: '-0.02em',
          color: 'var(--color-text)',
          marginRight: 'auto',
        }}>
          THREAD
        </span>

        {/* Status */}
        <StatusBadge state={runtimeState} dbStatus={dbStatus} />

        {/* Agent menu */}
        <div style={{ position: 'relative', marginLeft: 20 }}>
          <button
            id="agent-menu-btn"
            onClick={() => setShowMenu(!showMenu)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '5px 10px',
              background: 'var(--color-bg-subtle)',
              border: '1px solid var(--color-border)',
              borderRadius: 7,
              cursor: 'pointer',
              fontSize: 12,
              color: 'var(--color-text)',
              fontFamily: 'inherit',
              fontWeight: 500,
              letterSpacing: '-0.01em',
              maxWidth: 160,
            }}
          >
            <span style={{
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {personaName || agentId.slice(0, 8)}
            </span>
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{
              transform: showMenu ? 'rotate(180deg)' : 'none',
              transition: 'transform 0.15s',
              flexShrink: 0,
              opacity: 0.5,
            }}>
              <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>

          {showMenu && (
            <div
              style={{
                position: 'absolute',
                top: 'calc(100% + 6px)',
                right: 0,
                background: 'var(--color-bg)',
                border: '1px solid var(--color-border)',
                borderRadius: 9,
                boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
                minWidth: 160,
                overflow: 'hidden',
                animationName: 'fade-up',
                animationDuration: '0.15s',
                animationTimingFunction: 'ease',
                animationFillMode: 'both',
                zIndex: 100,
              }}
            >
              {/* Agent info */}
              <div style={{
                padding: '12px 14px',
                borderBottom: '1px solid var(--color-border)',
              }}>
                <p style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text)', marginBottom: 2 }}>
                  {personaName}
                </p>
                <p style={{ fontSize: 11, color: 'var(--color-text-tertiary)' }}>
                  {personaDomain}
                </p>
              </div>

              {/* Controls */}
              {isActive ? (
                <MenuButton
                  id="pause-agent-btn"
                  label={isStopping ? 'Stopping…' : 'Pause Agent'}
                  icon={<PauseIcon />}
                  onClick={() => { setShowMenu(false); onStop(); }}
                  disabled={isStopping}
                />
              ) : (
                <MenuButton
                  id="resume-agent-btn"
                  label={isStarting ? 'Starting…' : 'Resume Agent'}
                  icon={<PlayIcon />}
                  onClick={() => { setShowMenu(false); onStart(); }}
                  disabled={isStarting}
                />
              )}

              {/* Separator + reset */}
              <div style={{ borderTop: '1px solid var(--color-border)', padding: '4px 0' }}>
                <MenuButton
                  id="new-agent-btn"
                  label="New Agent"
                  icon={<PlusIcon />}
                  onClick={() => { setShowMenu(false); onReset(); }}
                  danger
                />
              </div>
            </div>
          )}
        </div>
      </header>

      {/* ─── Content ─────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Desktop sidebar */}
        <nav style={{
          width: 220,
          flexShrink: 0,
          borderRight: '1px solid var(--color-border)',
          padding: '20px 14px',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          overflowY: 'auto',
        }}
          className="sidebar"
        >
          <NavItem
            id="nav-feed"
            label="Feed"
            count={feed?.posts?.length}
            active={tab === 'feed'}
            onClick={() => setTab('feed')}
          />
          <NavItem
            id="nav-workspace"
            label="Workspace"
            active={tab === 'workspace'}
            onClick={() => setTab('workspace')}
          />

          {/* Stats strip */}
          {status && (
            <div style={{
              marginTop: 'auto',
              paddingTop: 20,
              borderTop: '1px solid var(--color-border)',
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}>
              <StatRow label="Posts"    value={status.posts_count} />
              <StatRow label="Beliefs"  value={status.beliefs_count} />
              <StatRow label="Cycles"   value={status.cycles_count} />
            </div>
          )}
        </nav>

        {/* Main content */}
        <main style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          {tab === 'feed' ? (
            <FeedPanel
              feed={feed}
              domain={personaDomain}
              error={error}
              isActive={isActive}
            />
          ) : (
            <div style={{ padding: '0 32px', maxWidth: 720 }}>
              {/* Persona header in workspace tab */}
              <div style={{
                paddingTop: 28,
                paddingBottom: 24,
                borderBottom: '1px solid var(--color-border)',
                marginBottom: 0,
              }}>
                <p style={{
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.07em',
                  textTransform: 'uppercase',
                  color: 'var(--color-text-tertiary)',
                  marginBottom: 6,
                }}>
                  Agent
                </p>
                <h1 style={{
                  fontSize: 22,
                  fontWeight: 600,
                  color: 'var(--color-text)',
                  letterSpacing: '-0.03em',
                  marginBottom: 4,
                }}>
                  {personaName}
                </h1>
                <p style={{ fontSize: 14, color: 'var(--color-text-secondary)' }}>
                  {personaDomain}
                </p>
              </div>
              <WorkspacePanel workspace={workspace} />
            </div>
          )}
        </main>
      </div>

      {/* ─── Mobile bottom tab bar ───────────────────────────────────── */}
      <nav style={{
        display: 'none',
        borderTop: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        padding: '8px 24px',
        gap: 0,
        flexShrink: 0,
      }}
        className="mobile-tabs"
      >
        <MobileTab label="Feed" active={tab === 'feed'} onClick={() => setTab('feed')} />
        <MobileTab label="Workspace" active={tab === 'workspace'} onClick={() => setTab('workspace')} />
      </nav>

      {/* Click-outside to close menu */}
      {showMenu && (
        <div
          style={{ position: 'fixed', inset: 0, zIndex: 9 }}
          onClick={() => setShowMenu(false)}
        />
      )}

      <style>{`
        @media (max-width: 640px) {
          .sidebar { display: none !important; }
          .mobile-tabs { display: flex !important; }
        }
      `}</style>
    </div>
  );
}

/* ─── Sub-components ─────────────────────────────────────────────────── */

function NavItem({
  id, label, count, active, onClick
}: { id: string; label: string; count?: number; active: boolean; onClick: () => void }) {
  return (
    <button
      id={id}
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        width: '100%',
        padding: '7px 10px',
        background: active ? 'var(--color-bg-muted)' : 'none',
        border: 'none',
        borderRadius: 7,
        cursor: 'pointer',
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        color: active ? 'var(--color-text)' : 'var(--color-text-secondary)',
        fontFamily: 'inherit',
        letterSpacing: '-0.01em',
        textAlign: 'left',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => { if (!active) (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-bg-subtle)'; }}
      onMouseLeave={e => { if (!active) (e.currentTarget as HTMLButtonElement).style.background = 'none'; }}
    >
      {label}
      {count !== undefined && count > 0 && (
        <span style={{
          fontSize: 11,
          fontWeight: 500,
          color: 'var(--color-text-tertiary)',
          background: 'var(--color-bg-muted)',
          borderRadius: 10,
          padding: '1px 6px',
        }}>
          {count}
        </span>
      )}
    </button>
  );
}

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 12, color: 'var(--color-text-tertiary)' }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-secondary)', fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </span>
    </div>
  );
}

function MenuButton({
  id, label, icon, onClick, disabled, danger,
}: { id: string; label: string; icon: React.ReactNode; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <button
      id={id}
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        padding: '9px 14px',
        background: 'none',
        border: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        fontSize: 13,
        color: danger ? 'var(--color-error)' : 'var(--color-text)',
        fontFamily: 'inherit',
        opacity: disabled ? 0.5 : 1,
        textAlign: 'left',
        letterSpacing: '-0.01em',
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => { if (!disabled) (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-bg-subtle)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = 'none'; }}
    >
      {icon}
      {label}
    </button>
  );
}

function MobileTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        flex: 1,
        padding: '8px 0',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        color: active ? 'var(--color-text)' : 'var(--color-text-secondary)',
        fontFamily: 'inherit',
        letterSpacing: '-0.01em',
      }}
    >
      {label}
    </button>
  );
}

import React from 'react';

function PlayIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M3 2.5L9.5 6L3 9.5V2.5Z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <rect x="2.5" y="2" width="3" height="8" rx="1" fill="currentColor"/>
      <rect x="6.5" y="2" width="3" height="8" rx="1" fill="currentColor"/>
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M6 2V10M2 6H10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}
