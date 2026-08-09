import { FeedPost } from './FeedPost';
import type { FeedResponse } from '../types/backend';

interface FeedPanelProps {
  feed:     FeedResponse | null;
  domain?:  string;
  error?:   string | null;
  isActive: boolean;
}

export function FeedPanel({ feed, domain, error, isActive }: FeedPanelProps) {
  const posts = feed?.posts ?? [];

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '20px 24px 18px',
        borderBottom: '1px solid var(--color-border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
        background: 'var(--color-bg)',
        position: 'sticky',
        top: 0,
        zIndex: 1,
      }}>
        <div>
          <h2 style={{
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--color-text)',
            letterSpacing: '-0.02em',
          }}>
            Feed
          </h2>
          <p style={{
            fontSize: 12,
            color: 'var(--color-text-tertiary)',
            marginTop: 1,
          }}>
            {posts.length === 0
              ? 'Waiting for first post…'
              : `${posts.length} ${posts.length === 1 ? 'post' : 'posts'} published`
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
        {posts.length === 0 ? (
          <EmptyFeed isActive={isActive} />
        ) : (
          posts.map((post, i) => (
            <FeedPost key={post.id} post={post} domain={domain} index={i} />
          ))
        )}
      </div>
    </div>
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
