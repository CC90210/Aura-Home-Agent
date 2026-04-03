'use client';

import { Music2 } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types — exported so callers can pass real track data in the future
// ---------------------------------------------------------------------------

export interface Track {
  title: string;
  artist: string;
  album: string;
  duration: number; // seconds
  accentColor: string;
  progressSeconds?: number;
  isPlaying?: boolean;
}

export interface MusicVisualizerProps {
  track?: Track;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------
// Visualizer bars — pure CSS animation
// ---------------------------------------------------------------------------

interface BarConfig {
  height: number;
  delay: number;
  duration: number;
}

// Pre-defined bar configs to avoid random values on re-render
const BAR_CONFIGS: BarConfig[] = [
  { height: 40, delay: 0,    duration: 0.9 },
  { height: 70, delay: 0.1,  duration: 0.7 },
  { height: 55, delay: 0.2,  duration: 1.1 },
  { height: 85, delay: 0.05, duration: 0.8 },
  { height: 45, delay: 0.3,  duration: 0.95},
  { height: 90, delay: 0.15, duration: 0.65},
  { height: 60, delay: 0.25, duration: 1.0 },
  { height: 75, delay: 0.4,  duration: 0.85},
  { height: 35, delay: 0.1,  duration: 1.2 },
  { height: 80, delay: 0.35, duration: 0.75},
  { height: 50, delay: 0.2,  duration: 0.9 },
  { height: 65, delay: 0.45, duration: 0.7 },
  { height: 40, delay: 0.05, duration: 1.05},
  { height: 78, delay: 0.3,  duration: 0.88},
  { height: 55, delay: 0.15, duration: 0.95},
  { height: 92, delay: 0.5,  duration: 0.72},
  { height: 48, delay: 0.25, duration: 1.15},
  { height: 70, delay: 0.4,  duration: 0.82},
  { height: 38, delay: 0.1,  duration: 0.9 },
  { height: 83, delay: 0.35, duration: 0.68},
  { height: 60, delay: 0.2,  duration: 1.0 },
  { height: 72, delay: 0.45, duration: 0.78},
  { height: 44, delay: 0.15, duration: 1.1 },
  { height: 88, delay: 0.55, duration: 0.7 },
  { height: 52, delay: 0.3,  duration: 0.92},
  { height: 67, delay: 0.4,  duration: 0.85},
  { height: 41, delay: 0.05, duration: 1.2 },
  { height: 79, delay: 0.25, duration: 0.75},
  { height: 58, delay: 0.5,  duration: 0.88},
  { height: 95, delay: 0.1,  duration: 0.65},
];

interface VisualizerBarsProps {
  isPlaying: boolean;
  accentColor: string;
}

function VisualizerBars({ isPlaying, accentColor }: VisualizerBarsProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        gap: 2,
        width: '100%',
        overflow: 'hidden',
        height: 80,
      }}
      aria-hidden="true"
    >
      <style>{`
        @keyframes eq-bounce {
          0%, 100% { transform: scaleY(0.2); }
          50%       { transform: scaleY(1); }
        }
      `}</style>

      {BAR_CONFIGS.map((bar, i) => (
        <div
          key={i}
          style={{
            flex: '1 0 0',
            height: `${bar.height}%`,
            borderRadius: '2px 2px 0 0',
            background: `linear-gradient(to top, ${accentColor}, ${accentColor}44)`,
            transformOrigin: 'bottom',
            willChange: 'transform',
            animation: isPlaying
              ? `eq-bounce ${bar.duration}s ${bar.delay}s ease-in-out infinite`
              : 'none',
            transform: 'scaleY(0.15)',
            transition: 'transform 0.4s ease',
            opacity: 0.85,
          }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState({ accentColor }: { accentColor: string }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 20px',
        gap: 12,
      }}
    >
      {/* Muted bars — visual consistency with the playing state */}
      <div style={{ marginBottom: 4, padding: '0 4px', width: '100%' }}>
        <VisualizerBars isPlaying={false} accentColor={accentColor} />
      </div>
      <Music2 size={28} style={{ color: '#334155' }} aria-hidden="true" />
      <div style={{ textAlign: 'center' }}>
        <p style={{ fontSize: 14, fontWeight: 600, color: '#475569', margin: 0 }}>
          No music playing
        </p>
        <p style={{ fontSize: 11, color: '#334155', marginTop: 4, marginBottom: 0 }}>
          Music will appear here when something is playing on Echo Dot
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Track view — rendered when real track data is provided
// ---------------------------------------------------------------------------

interface TrackViewProps {
  track: Track;
}

function TrackView({ track }: TrackViewProps) {
  const isPlaying = track.isPlaying ?? false;
  const progress = track.progressSeconds ?? 0;
  const progressPercent = Math.min((progress / track.duration) * 100, 100);

  return (
    <div style={{ padding: '20px 20px 16px' }}>
      {/* Track info */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
        {/* Spinning disc */}
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: '50%',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1px solid rgba(255,255,255,0.1)',
            background: `conic-gradient(from 0deg, ${track.accentColor}66, #0E0E1E, ${track.accentColor}44, #0E0E1E, ${track.accentColor}66)`,
            animation: isPlaying ? 'spin 4s linear infinite' : 'none',
          }}
          aria-hidden="true"
        >
          <div
            style={{
              width: 20,
              height: 20,
              borderRadius: '50%',
              border: '1px solid rgba(255,255,255,0.2)',
              background: '#0E0E1E',
            }}
          />
        </div>

        <div style={{ minWidth: 0, flex: 1 }}>
          <h3
            style={{
              fontSize: 15,
              fontWeight: 700,
              color: '#E2E8F0',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              lineHeight: 1.2,
              margin: 0,
            }}
          >
            {track.title}
          </h3>
          <p
            style={{
              fontSize: 12,
              color: '#94A3B8',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              marginTop: 2,
              marginBottom: 0,
            }}
          >
            {track.artist}
          </p>
          <p
            style={{
              fontSize: 10,
              color: '#475569',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              margin: 0,
            }}
          >
            {track.album}
          </p>
        </div>
      </div>

      {/* Visualizer */}
      <div style={{ marginBottom: 16, padding: '0 4px' }}>
        <VisualizerBars isPlaying={isPlaying} accentColor={track.accentColor} />
      </div>

      {/* Progress bar */}
      <div style={{ marginBottom: 4 }}>
        <div
          style={{
            height: 4,
            borderRadius: 9999,
            background: 'rgba(255,255,255,0.05)',
            overflow: 'hidden',
          }}
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={track.duration}
          aria-label={`Playback progress: ${formatTime(progress)} of ${formatTime(track.duration)}`}
        >
          <div
            style={{
              height: '100%',
              borderRadius: 9999,
              width: `${progressPercent}%`,
              background: `linear-gradient(to right, ${track.accentColor}, ${track.accentColor}bb)`,
              boxShadow: `0 0 6px ${track.accentColor}66`,
              transition: 'width 1s linear',
            }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 6 }}>
          <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>{formatTime(progress)}</span>
          <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>{formatTime(track.duration)}</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MusicVisualizer({ track }: MusicVisualizerProps = {}) {
  // When no track is playing, use a neutral accent color for the empty state bars
  const accentColor = track?.accentColor ?? '#7C3AED';
  const isPlaying = track?.isPlaying ?? false;

  return (
    <div
      style={{
        borderRadius: 16,
        border: `1px solid ${accentColor}30`,
        overflow: 'hidden',
        position: 'relative',
        background: `linear-gradient(135deg, #0E0E1E 0%, #12122A 60%, ${accentColor}18 100%)`,
      }}
    >
      {/* Ambient glow */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background: `radial-gradient(ellipse at 70% 30%, ${accentColor}12 0%, transparent 65%)`,
          transition: 'background 0.8s ease',
        }}
        aria-hidden="true"
      />

      <div style={{ position: 'relative', zIndex: 10 }}>
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            padding: '16px 20px',
            borderBottom: '1px solid rgba(255,255,255,0.05)',
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
              background: `${accentColor}20`,
              border: `1px solid ${accentColor}30`,
            }}
          >
            <Music2 size={14} style={{ color: accentColor }} aria-hidden="true" />
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
              Now Playing
            </h2>
            <p
              style={{
                fontSize: 11,
                color: '#64748B',
                marginTop: 2,
                marginBottom: 0,
              }}
            >
              Echo Dot &middot; Living Room
            </p>
          </div>
          {isPlaying && (
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: accentColor,
                  boxShadow: `0 0 6px ${accentColor}`,
                  animation: 'pulse 1.5s ease-in-out infinite',
                  display: 'block',
                }}
                aria-hidden="true"
              />
              <span
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.1em',
                  color: accentColor,
                }}
              >
                Playing
              </span>
            </div>
          )}
        </div>

        {/* Body: track view when data present, empty state otherwise */}
        {track ? <TrackView track={track} /> : <EmptyState accentColor={accentColor} />}
      </div>
    </div>
  );
}
