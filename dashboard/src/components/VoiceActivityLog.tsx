'use client';

import { useState, useEffect, useRef } from 'react';
import { Mic, Zap, Clock } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface VoiceEntry {
  id: string;
  timestamp: string;
  speaker: 'CC' | 'Adon';
  command: string;
  response: string;
  actionTaken: string | null;
}

// ---------------------------------------------------------------------------
// Mock data — most-recent first
// ---------------------------------------------------------------------------

const MOCK_LOG: VoiceEntry[] = [
  {
    id: '1',
    timestamp: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
    speaker: 'CC',
    command: 'Hey Aura, switch to Studio mode',
    response: "Done — key light on, blue accents up, room lights dimmed. Let's get to work.",
    actionTaken: 'Activated Studio scene',
  },
  {
    id: '2',
    timestamp: new Date(Date.now() - 11 * 60 * 1000).toISOString(),
    speaker: 'Adon',
    command: 'Turn off the kitchen lights',
    response: "Kitchen lights off.",
    actionTaken: 'light.kitchen_overhead → off',
  },
  {
    id: '3',
    timestamp: new Date(Date.now() - 28 * 60 * 1000).toISOString(),
    speaker: 'CC',
    command: "What's the temperature right now?",
    response: "Living room is sitting at 21°C — feeling comfortable. Target is 22°C.",
    actionTaken: null,
  },
  {
    id: '4',
    timestamp: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    speaker: 'CC',
    command: 'Play lo-fi playlist',
    response: "Lo-fi hip hop on the Echo, volume at 35%. Get into the zone.",
    actionTaken: 'media_player.living_room_speaker → playing',
  },
  {
    id: '5',
    timestamp: new Date(Date.now() - 72 * 60 * 1000).toISOString(),
    speaker: 'Adon',
    command: 'Set a gym reminder for 9am tomorrow',
    response: "Reminder set for 9 AM. I'll nudge you — don't skip.",
    actionTaken: 'Scheduled notification',
  },
  {
    id: '6',
    timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    speaker: 'CC',
    command: 'Good night Aura',
    response: "Night. Locking up, lights off in 30 seconds, thermostat dropping to 18°. Sleep well.",
    actionTaken: 'Activated Goodnight scene',
  },
];

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

export default function VoiceActivityLog() {
  const [entries, setEntries] = useState<VoiceEntry[]>(MOCK_LOG);
  const [visibleIds, setVisibleIds] = useState<Set<string>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);

  // Stagger-reveal entries on mount
  useEffect(() => {
    entries.forEach((entry, i) => {
      setTimeout(() => {
        setVisibleIds((prev) => new Set([...prev, entry.id]));
      }, i * 80);
    });
  }, [entries]);

  // Simulate a new entry arriving every 30 seconds (demo only)
  useEffect(() => {
    const DEMO_COMMANDS: Omit<VoiceEntry, 'id' | 'timestamp'>[] = [
      {
        speaker: 'CC',
        command: 'Increase brightness in the living room',
        response: "Living room LEDs at 80%. Bright enough?",
        actionTaken: 'light.living_room_leds → 80%',
      },
      {
        speaker: 'Adon',
        command: 'What scene is active?',
        response: "Studio mode is running — been on for about 40 minutes.",
        actionTaken: null,
      },
    ];
    let idx = 0;
    const timer = setInterval(() => {
      const base = DEMO_COMMANDS[idx % DEMO_COMMANDS.length];
      const newEntry: VoiceEntry = {
        ...base,
        id: `live-${Date.now()}`,
        timestamp: new Date().toISOString(),
      };
      idx++;
      setEntries((prev) => [newEntry, ...prev.slice(0, 9)]);
      setVisibleIds((prev) => new Set([...prev, newEntry.id]));
    }, 30000);
    return () => clearInterval(timer);
  }, []);

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
        {/* Live indicator */}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: '#34D399',
              boxShadow: '0 0 6px rgba(52,211,153,0.7)',
              animation: 'pulse 2s ease-in-out infinite',
              display: 'block',
            }}
            aria-hidden="true"
          />
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              color: '#34D399',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
            }}
          >
            Live
          </span>
        </div>
      </div>

      {/* Feed */}
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
    </div>
  );
}
