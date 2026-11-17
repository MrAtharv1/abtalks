import React, { useState } from 'react';
import type { AgentInitRequest } from '../types/backend';

interface CreateAgentProps {
  onInit: (req: AgentInitRequest) => Promise<void>;
  isInitializing: boolean;
  onEnableDemo?: () => void;
}

function CreateAgent({ onInit, isInitializing, onEnableDemo }: CreateAgentProps) {
  const [name,   setName]   = useState('');
  const [domain, setDomain] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !domain.trim()) return;
    await onInit({ persona: { name: name.trim(), domain: domain.trim() } });
  };

  const disabled = isInitializing || !name.trim() || !domain.trim();

  return (
    <div style={{
      minHeight: '100dvh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 20px',
      background: 'var(--color-bg)',
    }}>
      {/* Wordmark */}
      <div style={{ marginBottom: 56, textAlign: 'center' }}>
        <p style={{
          fontSize: 11,
          letterSpacing: '0.15em',
          textTransform: 'uppercase',
          color: 'var(--color-text-tertiary)',
          marginBottom: 10,
          fontWeight: 500,
        }}>
          Autonomous AI Research Agent
        </p>
        <h1 style={{
          fontSize: 'clamp(36px, 6vw, 56px)',
          fontWeight: 600,
          letterSpacing: '-0.03em',
          color: 'var(--color-text)',
          lineHeight: 1.1,
        }}>
          THREAD
        </h1>
      </div>

      {/* Form card */}
      <div style={{
        width: '100%',
        maxWidth: 400,
        background: 'var(--color-bg)',
        border: '1px solid var(--color-border)',
        borderRadius: 12,
        padding: '32px 28px',
      }}>
        <p style={{
          fontSize: 17,
          fontWeight: 600,
          color: 'var(--color-text)',
          marginBottom: 4,
          letterSpacing: '-0.02em',
        }}>
          Create your agent
        </p>
        <p style={{
          fontSize: 13,
          color: 'var(--color-text-secondary)',
          marginBottom: 28,
          lineHeight: 1.5,
        }}>
          Once initialized, your agent researches autonomously.
        </p>

        <form onSubmit={handleSubmit}>
          {/* Name */}
          <div style={{ marginBottom: 20 }}>
            <label style={{
              display: 'block',
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--color-text)',
              marginBottom: 6,
              letterSpacing: '-0.01em',
            }}>
              Name
            </label>
            <input
              id="agent-name"
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Ada"
              disabled={isInitializing}
              autoFocus
              style={{
                display: 'block',
                width: '100%',
                padding: '9px 12px',
                fontSize: 14,
                color: 'var(--color-text)',
                background: isInitializing ? 'var(--color-bg-subtle)' : 'var(--color-bg)',
                border: '1px solid var(--color-border)',
                borderRadius: 8,
                outline: 'none',
                fontFamily: 'inherit',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => { e.target.style.borderColor = 'var(--color-text)'; }}
              onBlur={e  => { e.target.style.borderColor = 'var(--color-border)'; }}
            />
          </div>

          {/* Domain */}
          <div style={{ marginBottom: 28 }}>
            <label style={{
              display: 'block',
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--color-text)',
              marginBottom: 6,
              letterSpacing: '-0.01em',
            }}>
              Domain
            </label>
            <input
              id="agent-domain"
              type="text"
              value={domain}
              onChange={e => setDomain(e.target.value)}
              placeholder="e.g. AI Safety & Alignment"
              disabled={isInitializing}
              style={{
                display: 'block',
                width: '100%',
                padding: '9px 12px',
                fontSize: 14,
                color: 'var(--color-text)',
                background: isInitializing ? 'var(--color-bg-subtle)' : 'var(--color-bg)',
                border: '1px solid var(--color-border)',
                borderRadius: 8,
                outline: 'none',
                fontFamily: 'inherit',
                transition: 'border-color 0.15s',
              }}
              onFocus={e => { e.target.style.borderColor = 'var(--color-text)'; }}
              onBlur={e  => { e.target.style.borderColor = 'var(--color-border)'; }}
            />
          </div>

          {/* Submit */}
          <button
            id="create-agent-btn"
            type="submit"
            disabled={disabled}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              width: '100%',
              padding: '10px 16px',
              fontSize: 14,
              fontWeight: 600,
              color: disabled ? 'var(--color-text-tertiary)' : '#fff',
              background: disabled ? 'var(--color-bg-muted)' : 'var(--color-text)',
              border: '1px solid transparent',
              borderRadius: 8,
              cursor: disabled ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit',
              letterSpacing: '-0.01em',
              transition: 'background 0.15s, opacity 0.15s',
            }}
          >
            {isInitializing ? (
              <>
                <Spinner />
                Creating agent…
              </>
            ) : (
              'Create Agent →'
            )}
          </button>

          {onEnableDemo && (
            <>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                margin: '22px 0 16px',
                gap: 12,
              }}>
                <div style={{ flex: 1, height: 1, background: 'var(--color-border)' }} />
                <span style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: 'var(--color-text-tertiary)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.08em',
                }}>
                  or bypass cold start
                </span>
                <div style={{ flex: 1, height: 1, background: 'var(--color-border)' }} />
              </div>

              <button
                id="explore-demo-btn"
                type="button"
                onClick={onEnableDemo}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  width: '100%',
                  padding: '10px 14px',
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--color-text)',
                  background: 'var(--color-bg-subtle)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  letterSpacing: '-0.01em',
                  transition: 'background 0.15s, border-color 0.15s',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-bg-muted)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-text-tertiary)';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-bg-subtle)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-border)';
                }}
              >
                <span style={{ color: '#8b5cf6', fontSize: 14 }}>⚡</span>
                Explore Live Demo Trace (Instant)
              </button>
            </>
          )}
        </form>
      </div>

      <p style={{
        marginTop: 28,
        fontSize: 12,
        color: 'var(--color-text-tertiary)',
        textAlign: 'center',
        maxWidth: 320,
        lineHeight: 1.5,
      }}>
        Your agent will begin researching immediately after creation — no further action required.
      </p>
    </div>
  );
}

function Spinner() {
  return (
    <svg
      width="14" height="14"
      viewBox="0 0 14 14"
      fill="none"
      style={{ animation: 'spin-smooth 0.7s linear infinite', flexShrink: 0 }}
    >
      <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" strokeOpacity="0.25" />
      <path d="M12.5 7A5.5 5.5 0 0 0 7 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export { CreateAgent, Spinner };
