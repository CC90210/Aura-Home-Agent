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
      className="flex items-end gap-0.5 w-full overflow-hidden"
      style={{ height: '80px' }}
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
      className="rounded-2xl border overflow-hidden relative"
      style={{
        borderColor: `${track.accentColor}30`,
        background: `linear-gradient(135deg, #0E0E1E 0%, #12122A 60%, ${track.accentColor}18 100%)`,
      }}
    >
      {/* Ambient glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse at 70% 30%, ${track.accentColor}12 0%, transparent 65%)`,
          transition: 'background 0.8s ease',
        }}
        aria-hidden="true"
      />

      <div className="relative z-10">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/5">
          <div
            className="flex items-center justify-center w-8 h-8 rounded-lg border"
            style={{
              background: `${track.accentColor}20`,
              borderColor: `${track.accentColor}30`,
            }}
          >
            <Music2 size={14} style={{ color: track.accentColor }} aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-100 tracking-wide">Now Visualizing</h2>
            <p className="text-[11px] text-slate-500 mt-0.5">Sonos Era 100 &middot; Living Room</p>
          </div>
          {isPlaying && (
            <div className="ml-auto flex items-center gap-1">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{
                  background: track.accentColor,
                  boxShadow: `0 0 6px ${track.accentColor}`,
                  animation: 'pulse 1.5s ease-in-out infinite',
                }}
                aria-hidden="true"
              />
              <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: track.accentColor }}>
                Playing
              </span>
            </div>
          )}
        </div>

        {/* Main content */}
        <div className="px-5 pt-5 pb-4">
          {/* Track info + disc */}
          <div className="flex items-center gap-4 mb-5">
            {/* Spinning disc */}
            <div
              className="w-14 h-14 rounded-full flex-shrink-0 flex items-center justify-center border border-white/10"
              style={{
                background: `conic-gradient(from 0deg, ${track.accentColor}66, #0E0E1E, ${track.accentColor}44, #0E0E1E, ${track.accentColor}66)`,
                animation: isPlaying ? 'spin 4s linear infinite' : 'none',
              }}
              aria-hidden="true"
            >
              <div
                className="w-5 h-5 rounded-full border border-white/20"
                style={{ background: '#0E0E1E' }}
              />
            </div>

            <div className="min-w-0 flex-1">
              <Disc3 size={10} style={{ color: track.accentColor }} className="mb-1" aria-hidden="true" />
              <h3 className="text-[15px] font-bold text-slate-100 truncate leading-tight">{track.title}</h3>
              <p className="text-[12px] text-slate-400 truncate mt-0.5">{track.artist}</p>
              <p className="text-[10px] text-slate-600 truncate">{track.album}</p>
            </div>
          </div>

          {/* Visualizer */}
          <div className="mb-4 px-1">
            <VisualizerBars isPlaying={isPlaying} accentColor={track.accentColor} />
          </div>

          {/* Progress bar */}
          <div className="mb-3">
            <div
              className="h-1 rounded-full bg-white/5 overflow-hidden cursor-pointer"
              role="progressbar"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={track.duration}
              aria-label={`Playback progress: ${formatTime(progress)} of ${formatTime(track.duration)}`}
            >
              <div
                className="h-full rounded-full transition-all duration-1000 ease-linear"
                style={{
                  width: `${progressPercent}%`,
                  background: `linear-gradient(to right, ${track.accentColor}, ${track.accentColor}bb)`,
                  boxShadow: `0 0 6px ${track.accentColor}66`,
                }}
              />
            </div>
            <div className="flex justify-between mt-1.5">
              <span className="text-[10px] text-slate-600 font-mono">{formatTime(progress)}</span>
              <span className="text-[10px] text-slate-600 font-mono">{formatTime(track.duration)}</span>
            </div>
          </div>

          {/* Controls */}
          <div className="flex items-center justify-center gap-5">
            <button
              onClick={handlePrev}
              aria-label="Previous track"
              className="text-slate-500 hover:text-slate-200 transition-colors p-1.5"
            >
              <SkipBack size={18} aria-hidden="true" />
            </button>

            <button
              onClick={() => setIsPlaying((p) => !p)}
              aria-label={isPlaying ? 'Pause' : 'Play'}
              className="w-11 h-11 rounded-full flex items-center justify-center border transition-all duration-200"
              style={{
                background: `${track.accentColor}25`,
                borderColor: `${track.accentColor}50`,
                color: track.accentColor,
                boxShadow: isPlaying ? `0 0 16px ${track.accentColor}40` : 'none',
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
              className="text-slate-500 hover:text-slate-200 transition-colors p-1.5"
            >
              <SkipForward size={18} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
