'use client';

import { useState, useEffect } from 'react';
import { Play, Pause, SkipForward, SkipBack, Music2, Disc3 } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Track {
  title: string;
  artist: string;
  album: string;
  duration: number; // seconds
  accentColor: string;
}

// ---------------------------------------------------------------------------
// Mock tracks
// ---------------------------------------------------------------------------

const MOCK_TRACKS: Track[] = [
  { title: 'Midnight City',     artist: 'M83',               album: 'Hurry Up, We\'re Dreaming', duration: 244, accentColor: '#7C3AED' },
  { title: 'Breathe (In the Air)', artist: 'Pink Floyd',     album: 'The Dark Side of the Moon',  duration: 169, accentColor: '#60A5FA' },
  { title: 'Circles',           artist: 'Mac Miller',        album: 'Circles',                    duration: 215, accentColor: '#34D399' },
  { title: 'Nights',            artist: 'Frank Ocean',       album: 'Blonde',                     duration: 307, accentColor: '#F59E0B' },
  { title: 'Digital World',     artist: 'OASIS AI',          album: 'AURA Soundtrack',            duration: 198, accentColor: '#A78BFA' },
];

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
      {/* Inline keyframes injected once via a style tag in the component */}
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
            transform: isPlaying ? undefined : 'scaleY(0.15)',
            transition: isPlaying ? undefined : 'transform 0.4s ease',
            opacity: 0.85,
          }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MusicVisualizer() {
  const [trackIndex, setTrackIndex] = useState(0);
  const [isPlaying, setIsPlaying]   = useState(true);
  const [progress, setProgress]     = useState(32); // seconds elapsed

  const track = MOCK_TRACKS[trackIndex];

  // Advance progress every second while playing
  useEffect(() => {
    if (!isPlaying) return;
    const id = setInterval(() => {
      setProgress((prev) => {
        if (prev >= track.duration) {
          // Auto-advance to next track
          setTrackIndex((ti) => (ti + 1) % MOCK_TRACKS.length);
          return 0;
        }
        return prev + 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [isPlaying, track.duration]);

  const handlePrev = () => {
    setProgress(0);
    setTrackIndex((prev) => (prev - 1 + MOCK_TRACKS.length) % MOCK_TRACKS.length);
  };

  const handleNext = () => {
    setProgress(0);
    setTrackIndex((prev) => (prev + 1) % MOCK_TRACKS.length);
  };

  const progressPercent = Math.min((progress / track.duration) * 100, 100);

  return (
    <div
      style={{
        borderRadius: 16,
        border: `1px solid ${track.accentColor}30`,
        overflow: 'hidden',
        position: 'relative',
        background: `linear-gradient(135deg, #0E0E1E 0%, #12122A 60%, ${track.accentColor}18 100%)`,
      }}
    >
      {/* Ambient glow */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background: `radial-gradient(ellipse at 70% 30%, ${track.accentColor}12 0%, transparent 65%)`,
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
              background: `${track.accentColor}20`,
              border: `1px solid ${track.accentColor}30`,
            }}
          >
            <Music2 size={14} style={{ color: track.accentColor }} aria-hidden="true" />
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
              Now Visualizing
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
                  background: track.accentColor,
                  boxShadow: `0 0 6px ${track.accentColor}`,
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
                  color: track.accentColor,
                }}
              >
                Playing
              </span>
            </div>
          )}
        </div>

        {/* Main content */}
        <div style={{ padding: '20px 20px 16px' }}>
          {/* Track info + disc */}
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
              <Disc3 size={10} style={{ color: track.accentColor, marginBottom: 4, display: 'block' }} aria-hidden="true" />
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
          <div style={{ marginBottom: 12 }}>
            <div
              style={{
                height: 4,
                borderRadius: 9999,
                background: 'rgba(255,255,255,0.05)',
                overflow: 'hidden',
                cursor: 'pointer',
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

          {/* Controls */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20 }}>
            <button
              onClick={handlePrev}
              aria-label="Previous track"
              style={{
                color: '#64748B',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 6,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'color 0.2s ease',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = '#E2E8F0'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = '#64748B'; }}
            >
              <SkipBack size={18} aria-hidden="true" />
            </button>

            <button
              onClick={() => setIsPlaying((p) => !p)}
              aria-label={isPlaying ? 'Pause' : 'Play'}
              style={{
                width: 44,
                height: 44,
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: `1px solid ${track.accentColor}50`,
                background: `${track.accentColor}25`,
                color: track.accentColor,
                boxShadow: isPlaying ? `0 0 16px ${track.accentColor}40` : 'none',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
            >
              {isPlaying ? (
                <Pause size={18} fill="currentColor" aria-hidden="true" />
              ) : (
                <Play size={18} fill="currentColor" style={{ marginLeft: 2 }} aria-hidden="true" />
              )}
            </button>

            <button
              onClick={handleNext}
              aria-label="Next track"
              style={{
                color: '#64748B',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: 6,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'color 0.2s ease',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = '#E2E8F0'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = '#64748B'; }}
            >
              <SkipForward size={18} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
