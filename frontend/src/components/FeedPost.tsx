import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import type { PostResponse } from '../types/backend';

interface FeedPostProps {
  post:    PostResponse;
  domain?: string;
  index:   number;
}

export function FeedPost({ post, domain, index }: FeedPostProps) {
  const [showRationale, setShowRationale] = useState(false);
  const [showSources,   setShowSources]   = useState(false);

  const timeAgo = formatDistanceToNow(new Date(post.createdAt), { addSuffix: true });

  return (
    <article
      style={{
        padding: '28px 0',
        borderBottom: '1px solid var(--color-border)',
        animationName: 'fade-up',
        animationDuration: '0.3s',
        animationTimingFunction: 'ease',
        animationDelay: `${Math.min(index * 40, 300)}ms`,
        animationFillMode: 'both',
      }}
    >
      {/* Domain and Status */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
        {domain && (
          <p style={{
            margin: 0,
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.07em',
            textTransform: 'uppercase',
            color: 'var(--color-text-tertiary)',
          }}>
            {domain}
          </p>
        )}
        {post.status && post.status !== "PUBLISHED" && (
          <span style={{
            fontSize: 10,
            fontWeight: 600,
            padding: '2px 6px',
            borderRadius: '4px',
            textTransform: 'uppercase',
            backgroundColor: post.status === "FAILED" || post.status === "REJECTED" ? '#fee2e2' : '#fef3c7',
            color: post.status === "FAILED" || post.status === "REJECTED" ? '#991b1b' : '#92400e',
          }}>
            Editorial {post.status}
          </span>
        )}
      </div>

      {/* Body text */}
      <p style={{
        margin: 0,
        fontSize: 15,
        lineHeight: 1.7,
        color: 'var(--color-text)',
        fontWeight: 400,
        whiteSpace: 'pre-wrap',
        letterSpacing: '-0.01em',
      }}>
        {post.text}
      </p>

      {/* Timestamp */}
      <time
        dateTime={post.createdAt}
        style={{
          display: 'block',
          marginTop: 14,
          fontSize: 12,
          color: 'var(--color-text-tertiary)',
          letterSpacing: '-0.01em',
        }}
      >
        {timeAgo}
      </time>

      {/* Rationale */}
      {post.rationale && (
        <div style={{ marginTop: 14 }}>
          <button
            onClick={() => setShowRationale(!showRationale)}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              fontSize: 12,
              color: 'var(--color-text-secondary)',
              fontFamily: 'inherit',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              letterSpacing: '-0.01em',
            }}
          >
            <ChevronIcon open={showRationale} />
            Why this post?
          </button>
          {showRationale && (
            <p style={{
              marginTop: 8,
              padding: '10px 14px',
              background: 'var(--color-bg-subtle)',
              border: '1px solid var(--color-border)',
              borderRadius: 7,
              fontSize: 13,
              color: 'var(--color-text-secondary)',
              lineHeight: 1.6,
              animationName: 'fade-up',
              animationDuration: '0.18s',
              animationTimingFunction: 'ease',
              animationFillMode: 'both',
            }}>
              {post.rationale}
            </p>
          )}
        </div>
      )}

      {/* Sources */}
      {post.sources && post.sources.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <button
            onClick={() => setShowSources(!showSources)}
            style={{
              background: 'none',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              fontSize: 12,
              color: 'var(--color-text-secondary)',
              fontFamily: 'inherit',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              letterSpacing: '-0.01em',
            }}
          >
            <ChevronIcon open={showSources} />
            {post.sources.length} {post.sources.length === 1 ? 'source' : 'sources'}
          </button>
          {showSources && (
            <div style={{
              marginTop: 8,
              display: 'flex',
              flexDirection: 'column',
              gap: 5,
              animationName: 'fade-up',
              animationDuration: '0.18s',
              animationTimingFunction: 'ease',
              animationFillMode: 'both',
            }}>
              {post.sources.map((url, i) => {
                let label = url;
                try {
                  const u = new URL(url);
                  label = u.hostname.replace(/^www\./, '');
                  if (u.pathname.length > 1) label += u.pathname.slice(0, 40);
                } catch { /* keep raw */ }

                return (
                  <a
                    key={i}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={url}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 5,
                      fontSize: 12,
                      color: 'var(--color-text-secondary)',
                      textDecoration: 'none',
                      overflow: 'hidden',
                      maxWidth: '100%',
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--color-text)'; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.color = 'var(--color-text-secondary)'; }}
                  >
                    <ArrowUpRight />
                    <span style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {label}
                    </span>
                  </a>
                );
              })}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 12 12" fill="none"
      style={{
        transform: open ? 'rotate(90deg)' : 'rotate(0deg)',
        transition: 'transform 0.15s ease',
        flexShrink: 0,
        opacity: 0.5,
      }}
    >
      <path d="M4.5 3L7.5 6L4.5 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ArrowUpRight() {
  return (
    <svg
      width="11" height="11" viewBox="0 0 11 11" fill="none"
      style={{ flexShrink: 0, opacity: 0.6 }}
    >
      <path d="M2.5 8.5L8.5 2.5M8.5 2.5H4M8.5 2.5V7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
