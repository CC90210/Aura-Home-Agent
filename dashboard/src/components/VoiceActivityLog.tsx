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
    <div className="rounded-2xl border border-purple-900/30 bg-[#0E0E1E]/90 backdrop-blur-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-purple-900/20">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-purple-600/15 border border-purple-600/25">
          <Mic size={14} className="text-violet-400" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-100 tracking-wide">Voice Activity</h2>
          <p className="text-[11px] text-slate-500 mt-0.5">Recent commands &amp; responses</p>
        </div>
        {/* Live indicator */}
        <div className="ml-auto flex items-center gap-1.5">
          <span
            className="w-1.5 h-1.5 rounded-full bg-emerald-400"
            style={{ boxShadow: '0 0 6px rgba(52,211,153,0.7)', animation: 'pulse 2s ease-in-out infinite' }}
            aria-hidden="true"
          />
          <span className="text-[10px] font-semibold text-emerald-400 tracking-widest uppercase">Live</span>
        </div>
      </div>

      {/* Feed */}
      <div
        ref={containerRef}
        className="overflow-y-auto"
        style={{ maxHeight: '420px' }}
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
              }}
              className={[
                'px-5 py-4',
                index < entries.length - 1 ? 'border-b border-purple-900/15' : '',
              ].join(' ')}
              aria-label={`${entry.speaker} said: ${entry.command}`}
            >
              {/* Row: speaker badge + timestamp */}
              <div className="flex items-center gap-2 mb-2">
                <span
                  className={[
                    'text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-md',
                    isCc
                      ? 'bg-purple-600/20 text-violet-400 border border-purple-600/30'
                      : 'bg-blue-600/20 text-blue-400 border border-blue-600/30',
                  ].join(' ')}
                >
                  {entry.speaker}
                </span>
                <div className="flex items-center gap-1 text-slate-600">
                  <Clock size={10} aria-hidden="true" />
                  <span className="text-[10px]">{formatTimestamp(entry.timestamp)}</span>
                </div>
              </div>

              {/* Command bubble */}
              <div className="mb-2 ml-0">
                <div className="inline-block max-w-full px-3 py-2 rounded-xl rounded-tl-sm bg-[#1A1A32] border border-purple-900/25 text-[13px] text-slate-300">
                  &ldquo;{entry.command}&rdquo;
                </div>
              </div>

              {/* AURA response */}
              <div className="ml-3 mb-1">
                <div className="flex items-start gap-2">
                  <div className="flex-shrink-0 mt-0.5">
                    <div
                      className="w-4 h-4 rounded-full flex items-center justify-center"
                      style={{ background: 'linear-gradient(135deg, #7C3AED, #2563EB)' }}
                      aria-hidden="true"
                    >
                      <Zap size={8} className="text-white" />
                    </div>
                  </div>
                  <div className="text-[12px] text-slate-400 italic leading-relaxed">
                    {entry.response}
                  </div>
                </div>
              </div>

              {/* Action chip */}
              {entry.actionTaken && (
                <div className="ml-6 mt-1.5">
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-emerald-900/20 text-emerald-500 border border-emerald-900/30 font-mono">
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
