'use client';

import { useState, useEffect, useRef } from 'react';
import { Mic, Zap, Clock } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface VoiceEntry {
  id: string;
  timestamp: string;
  speaker: 'CC' | 'Adon';
  command: string;
  response: string;
  actionTaken: string | null;
}

export interface VoiceActivityLogProps {
  entries?: VoiceEntry[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function VoiceActivityLog({ entries = [] }: VoiceActivityLogProps) {
  const [visibleIds, setVisibleIds] = useState<Set<string>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);

  // Stagger-reveal entries whenever the list changes
  useEffect(() => {
    entries.forEach((entry, i) => {
      setTimeout(() => {
        setVisibleIds((prev) => new Set([...prev, entry.id]));
      }, i * 80);
    });
  }, [entries]);

  return (
    <div
      style={{
        borderRadius: 16,
        border: '1px solid rgba(88, 28, 135, 0.3)',
        background: 'rgba(14, 14, 30, 0.9)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '16px 20px',
          borderBottom: '1px solid rgba(88, 28, 135, 0.2)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 32,
            height: 32,
            borderRadius: 8,
            background: 'rgba(124, 58, 237, 0.15)',
            border: '1px solid rgba(124, 58, 237, 0.25)',
          }}
        >
          <Mic size={14} style={{ color: '#A78BFA' }} aria-hidden="true" />
        </div>
        <div>
          <h2
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: '#E2E8F0',
              letterSpacing: '0.025em',
              margin: 0,
            }}
          >
            Voice Activity
          </h2>
          <p
            style={{
              fontSize: 11,
              color: '#64748B',
              marginTop: 2,
              marginBottom: 0,
            }}
          >
            Recent commands &amp; responses
          </p>
        </div>
      </div>

      {/* Feed — empty state or real entries */}
      {entries.length === 0 ? (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '48px 20px',
            gap: 12,
          }}
        >
          <Mic size={28} style={{ color: '#334155' }} aria-hidden="true" />
          <div style={{ textAlign: 'center' }}>
            <p style={{ fontSize: 14, fontWeight: 600, color: '#475569', margin: 0 }}>
              No recent commands
            </p>
            <p style={{ fontSize: 12, color: '#334155', marginTop: 6, marginBottom: 0 }}>
              Say &ldquo;Hey Aura&rdquo; to get started
            </p>
          </div>
        </div>
      ) : (
        <div
          ref={containerRef}
          style={{ overflowY: 'auto', maxHeight: 420 }}
          role="log"
          aria-label="Voice command log"
          aria-live="polite"
        >
          {entries.map((entry, index) => {
            const isVisible = visibleIds.has(entry.id);
            const isCc = entry.speaker === 'CC';

            return (
              <div
                key={entry.id}
                style={{
                  opacity: isVisible ? 1 : 0,
                  transform: isVisible ? 'translateY(0)' : 'translateY(8px)',
                  transition: 'opacity 0.35s ease, transform 0.35s ease',
                  padding: '16px 20px',
                  borderBottom: index < entries.length - 1 ? '1px solid rgba(88, 28, 135, 0.15)' : 'none',
                }}
                aria-label={`${entry.speaker} said: ${entry.command}`}
              >
                {/* Row: speaker badge + timestamp */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                      padding: '2px 8px',
                      borderRadius: 6,
                      background: isCc ? 'rgba(124, 58, 237, 0.2)' : 'rgba(37, 99, 235, 0.2)',
                      color: isCc ? '#A78BFA' : '#60A5FA',
                      border: isCc ? '1px solid rgba(124, 58, 237, 0.3)' : '1px solid rgba(37, 99, 235, 0.3)',
                    }}
                  >
                    {entry.speaker}
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#475569' }}>
                    <Clock size={10} aria-hidden="true" />
                    <span style={{ fontSize: 10 }}>{formatTimestamp(entry.timestamp)}</span>
                  </div>
                </div>

                {/* Command bubble */}
                <div style={{ marginBottom: 8 }}>
                  <div
                    style={{
                      display: 'inline-block',
                      maxWidth: '100%',
                      padding: '8px 12px',
                      borderRadius: '12px 12px 12px 4px',
                      background: '#1A1A32',
                      border: '1px solid rgba(88, 28, 135, 0.25)',
                      fontSize: 13,
                      color: '#CBD5E1',
                    }}
                  >
                    &ldquo;{entry.command}&rdquo;
                  </div>
                </div>

                {/* AURA response */}
                <div style={{ marginLeft: 12, marginBottom: 4 }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ flexShrink: 0, marginTop: 2 }}>
                      <div
                        style={{
                          width: 16,
                          height: 16,
                          borderRadius: '50%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          background: 'linear-gradient(135deg, #7C3AED, #2563EB)',
                        }}
                        aria-hidden="true"
                      >
                        <Zap size={8} style={{ color: '#fff' }} />
                      </div>
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: '#94A3B8',
                        fontStyle: 'italic',
                        lineHeight: 1.6,
                      }}
                    >
                      {entry.response}
                    </div>
                  </div>
                </div>

                {/* Action chip */}
                {entry.actionTaken && (
                  <div style={{ marginLeft: 24, marginTop: 6 }}>
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        fontSize: 10,
                        padding: '2px 8px',
                        borderRadius: 9999,
                        background: 'rgba(6, 78, 59, 0.2)',
                        color: '#10B981',
                        border: '1px solid rgba(6, 78, 59, 0.3)',
                        fontFamily: 'monospace',
                      }}
                    >
                      <span aria-hidden="true">&#x2713;</span>
                      {entry.actionTaken}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
