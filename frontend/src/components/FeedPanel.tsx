import { useState } from 'react';
import { FeedPost } from './FeedPost';
import type { FeedResponse } from '../types/backend';

interface FeedPanelProps {
  feed:        FeedResponse | null;
  domain?:     string;
  error?:      string | null;
  isActive:    boolean;
  isDemoMode?: boolean;
}

export function FeedPanel({ feed, domain, error, isActive }: FeedPanelProps) {
  const posts = feed?.posts ?? [];
  const [filter, setFilter] = useState<'all' | 'published' | 'rejected'>('all');

  const publishedCount = posts.filter(p => p.status === 'PUBLISHED').length;
  const rejectedCount = posts.filter(p => p.status === 'REJECTED' || p.status === 'FAILED').length;

  const filteredPosts = posts.filter(p => {
    if (filter === 'published') return p.status === 'PUBLISHED';
    if (filter === 'rejected') return p.status === 'REJECTED' || p.status === 'FAILED';
    return true;
  });

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '20px 24px 14px',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        flexShrink: 0,
        background: 'var(--color-bg)',
        position: 'sticky',
        top: 0,
        zIndex: 1,
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <h2 style={{
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--color-text)',
              letterSpacing: '-0.02em',
            }}>
              Feed & Editorial Decisions
            </h2>
            <p style={{
              fontSize: 12,
              color: 'var(--color-text-tertiary)',
              marginTop: 1,
            }}>
              {posts.length === 0
                ? 'Waiting for first post…'
                : `${publishedCount} published • ${rejectedCount} quality-gate filtered`
              }
            </p>
          </div>

          {/* Live indicator */}
          {isActive && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              fontSize: 11,
              fontWeight: 500,
              color: 'var(--color-text-tertiary)',
              letterSpacing: '-0.01em',
            }}>
              <span style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: 'var(--color-active)',
                animation: 'pulse-active 2s ease-in-out infinite',
              }} />
              LIVE
            </div>
          )}
        </div>

        {/* Filter Pills */}
        {posts.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <FilterPill
              label={`All (${posts.length})`}
              active={filter === 'all'}
              onClick={() => setFilter('all')}
            />
            <FilterPill
              label={`Published (${publishedCount})`}
              active={filter === 'published'}
              onClick={() => setFilter('published')}
            />
            <FilterPill
              label={`Rejected by Gate (${rejectedCount})`}
              active={filter === 'rejected'}
              onClick={() => setFilter('rejected')}
              highlight={rejectedCount > 0}
            />
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div style={{
          padding: '10px 24px',
          background: '#fff7ed',
          borderBottom: '1px solid #fed7aa',
          fontSize: 12,
          color: '#c2410c',
          letterSpacing: '-0.01em',
        }}>
          {error}
        </div>
      )}

      {/* Feed list */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '0 24px',
      }}>
        {filteredPosts.length === 0 ? (
          posts.length === 0 ? (
            <EmptyFeed isActive={isActive} />
          ) : (
            <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: 13 }}>
              No posts matching this filter.
            </div>
          )
        ) : (
          filteredPosts.map((post, i) => (
            <FeedPost key={post.id} post={post} domain={domain} index={i} />
          ))
        )}
      </div>
    </div>
  );
}

function FilterPill({
  label, active, onClick, highlight,
}: { label: string; active: boolean; onClick: () => void; highlight?: boolean }) {
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
          : highlight
          ? '#fecdd3'
          : 'var(--color-border)',
        background: active
          ? 'var(--color-text)'
          : highlight
          ? '#fff1f2'
          : 'var(--color-bg-subtle)',
        color: active
          ? '#ffffff'
          : highlight
          ? '#9f1239'
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

function EmptyFeed({ isActive }: { isActive: boolean }) {
  return (
    <div style={{
      paddingTop: 48,
      paddingBottom: 48,
      textAlign: 'center',
    }}>
      {isActive ? (
        <>
          {/* Skeleton posts */}
          {[0, 1].map(i => (
            <div key={i} style={{
              marginBottom: 28,
              padding: '28px 0',
              borderBottom: '1px solid var(--color-border)',
              textAlign: 'left',
            }}>
              <div className="skeleton" style={{
                height: 11,
                width: '30%',
                borderRadius: 6,
                marginBottom: 14,
              }} />
              <div className="skeleton" style={{
                height: 14,
                width: '100%',
                borderRadius: 6,
                marginBottom: 8,
              }} />
              <div className="skeleton" style={{
                height: 14,
                width: '85%',
                borderRadius: 6,
                marginBottom: 8,
              }} />
              <div className="skeleton" style={{
                height: 14,
                width: '70%',
                borderRadius: 6,
              }} />
            </div>
          ))}
          <p style={{
            fontSize: 13,
            color: 'var(--color-text-tertiary)',
            lineHeight: 1.6,
            marginTop: 12,
          }}>
            Your agent is researching its first topic.
            <br />
            Posts will appear here automatically.
          </p>
        </>
      ) : (
        <p style={{
          fontSize: 13,
          color: 'var(--color-text-tertiary)',
          lineHeight: 1.6,
        }}>
          Agent is paused.
          <br />
          Resume to continue publishing.
        </p>
      )}
    </div>
  );
}
