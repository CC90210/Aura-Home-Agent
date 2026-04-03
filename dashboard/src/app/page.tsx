"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Home,
  Grid3X3,
  DoorOpen,
  User,
  Sunset,
  Sun,
  Video,
  Film,
  Music,
  Brain,
  Gamepad2,
  Radio,
  PartyPopper,
  Zap,
  Music2,
  Play,
  Pause,
  SkipForward,
  SkipBack,
  Volume2,
  VolumeX,
  Shuffle,
  Thermometer,
  Minus,
  Plus,
  Droplets,
  Wind,
  Flame,
  Check,
  Clock,
  Dumbbell,
  Salad,
  Monitor,
  Moon,
  Star,
  Lightbulb,
  Power,
  ChevronDown,
  ChevronUp,
  Sofa,
  BedDouble,
  UtensilsCrossed,
  Server,
  Terminal,
  Clock3,
  Activity,
  Wifi,
  WifiOff,
  type LucideProps,
} from "lucide-react";
import Image from "next/image";
import type {
  Scene,
  Room,
  Device,
  HabitEntry,
  AuraStatus,
  NowPlayingState,
  ClimateState,
  ResidentPresence,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Tab type
// ---------------------------------------------------------------------------

type Tab = "home" | "scenes" | "rooms" | "profile";

// ---------------------------------------------------------------------------
// Icon maps — avoids dynamic imports and preserves type safety
// ---------------------------------------------------------------------------

const SCENE_ICON_MAP: Record<string, React.ComponentType<LucideProps>> = {
  Sunset, Sun, Video, Film, Music, Brain, Gamepad2, Radio, PartyPopper, Zap,
};

const HABIT_ICON_MAP: Record<string, React.ComponentType<LucideProps>> = {
  Dumbbell, Salad, Monitor, Moon, Star, Flame,
};

const ROOM_ICON_MAP: Record<string, React.ComponentType<LucideProps>> = {
  Sofa, BedDouble, UtensilsCrossed, Home,
};

// Maps scene id → CSS class for the gradient background on full scene cards
const SCENE_GRADIENT_MAP: Record<string, string> = {
  "close-down": "scene-gradient-sunset",
  "open-up":    "scene-gradient-morning",
  studio:       "scene-gradient-studio",
  movie:        "scene-gradient-movie",
  party:        "scene-gradient-party",
  focus:        "scene-gradient-focus",
  gaming:       "scene-gradient-gaming",
  streaming:    "scene-gradient-streaming",
  music:        "scene-gradient-music",
};

// ---------------------------------------------------------------------------
// Seed / placeholder data
// ---------------------------------------------------------------------------

const PLACEHOLDER_SCENES: Scene[] = [
  {
    id: "close-down",
    name: "Close Down",
    icon: "Sunset",
    webhook_id: "aura_close_down",
    description: "Wind down — dim warm lights, lock up, quiet music",
    active: false,
  },
  {
    id: "open-up",
    name: "Open Up",
    icon: "Sun",
    webhook_id: "aura_open_up",
    description: "Good morning — bright lights, blinds open, morning playlist",
    active: false,
  },
  {
    id: "studio",
    name: "Studio",
    icon: "Video",
    webhook_id: "aura_studio_mode",
    description: "Content creation — key lights, blue accents, quiet",
    active: false,
  },
  {
    id: "movie",
    name: "Movie",
    icon: "Film",
    webhook_id: "aura_movie_mode",
    description: "Deep purple lights, blinds closed, cinema audio",
    active: false,
  },
  {
    id: "party",
    name: "Party",
    icon: "PartyPopper",
    webhook_id: "aura_party_mode",
    description: "Music-reactive lights, full volume, party vibes",
    active: false,
  },
  {
    id: "focus",
    name: "Focus",
    icon: "Brain",
    webhook_id: "aura_focus_mode",
    description: "Cool daylight, lo-fi playlist, notifications off",
    active: false,
  },
  {
    id: "gaming",
    name: "Gaming",
    icon: "Gamepad2",
    webhook_id: "aura_gaming_mode",
    description: "RGB lighting, monitor brightness up, surround audio",
    active: false,
  },
  {
    id: "streaming",
    name: "Streaming",
    icon: "Radio",
    webhook_id: "aura_streaming_mode",
    description: "Studio lights + camera-ready scene for live streaming",
    active: false,
  },
  {
    id: "music",
    name: "Music",
    icon: "Music",
    webhook_id: "aura_music_mode",
    description: "Warm ambient lights, speakers on, Spotify vibes",
    active: false,
  },
];

const PLACEHOLDER_ROOMS: Room[] = [
  { name: "Living Room", icon: "Sofa",           temperature: null, devices: [] },
  { name: "Bedroom",     icon: "BedDouble",       temperature: null, devices: [] },
  { name: "Kitchen",     icon: "UtensilsCrossed", temperature: null, devices: [] },
];

const DEFAULT_HABITS: HabitEntry[] = [
  { id: "gym",       name: "Gym",                icon: "Dumbbell", target_time: "09:00", completed: false, streak: 0 },
  { id: "meals",     name: "Meals tracked",       icon: "Salad",    target_time: "20:00", completed: false, streak: 0 },
  { id: "deep-work", name: "Deep work",           icon: "Monitor",  target_time: "13:00", completed: false, streak: 0 },
  { id: "bedtime",   name: "Bedtime by midnight", icon: "Moon",     target_time: "23:59", completed: false, streak: 0 },
];

const PLACEHOLDER_RESIDENTS: ResidentPresence[] = [
  { name: "CC",   home: false, entity_id: "device_tracker.conaugh_phone", last_seen: null },
  { name: "Adon", home: false, entity_id: "device_tracker.adon_phone",    last_seen: null },
];

const PLACEHOLDER_STATUS: AuraStatus = {
  pi_online: false,
  services: [
    { name: "clap-listener", running: false, last_seen: null },
    { name: "ha-mcp",        running: false, last_seen: null },
  ],
  last_command: null,
  last_command_time: null,
  uptime: null,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

function useCurrentTime(): { time: string; date: string } {
  const [time, setTime] = useState(() =>
    new Date().toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit", hour12: false })
  );
  const [date] = useState(() =>
    new Date().toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric" })
  );

  useEffect(() => {
    const tick = () =>
      setTime(new Date().toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit", hour12: false }));
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return { time, date };
}

// ---------------------------------------------------------------------------
// Small shared primitives
// ---------------------------------------------------------------------------

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div
        className="h-4 w-0.5 rounded-full"
        style={{ background: "linear-gradient(180deg, #9F67FF 0%, #3B82F6 100%)" }}
        aria-hidden="true"
      />
      <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#64748B" }}>
        {children}
      </h2>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ScenePill — compact, horizontal-scroll version for the Home tab
// ---------------------------------------------------------------------------

interface ScenePillProps {
  scene: Scene;
  onPress: (scene: Scene) => Promise<void>;
}

function ScenePill({ scene, onPress }: ScenePillProps) {
  const [loading, setLoading] = useState(false);
  const Icon = SCENE_ICON_MAP[scene.icon] ?? Zap;

  const handlePress = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    try {
      await onPress(scene);
    } finally {
      setLoading(false);
    }
  }, [loading, onPress, scene]);

  return (
    <button
      onClick={handlePress}
      disabled={loading}
      aria-label={`Activate ${scene.name} scene`}
      aria-pressed={scene.active}
      className={[
        "flex items-center gap-2 px-4 py-2 rounded-full shrink-0",
        "text-xs font-semibold transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
        "active:scale-95 select-none",
        scene.active
          ? "text-white border border-aura-purple"
          : "border border-aura-border text-aura-text-muted hover:border-aura-purple/40 hover:text-aura-text",
      ].join(" ")}
      style={
        scene.active
          ? {
              background: "linear-gradient(135deg, rgba(124,58,237,0.55) 0%, rgba(59,130,246,0.35) 100%)",
              boxShadow: "0 0 14px rgba(124,58,237,0.45)",
            }
          : { background: "rgba(18,18,42,0.70)" }
      }
    >
      {loading ? (
        <span
          className="w-3 h-3 rounded-full border border-aura-text-muted/40 border-t-aura-text-muted shrink-0"
          style={{ animation: "spin 0.8s linear infinite" }}
          aria-hidden="true"
        />
      ) : (
        <Icon size={13} strokeWidth={scene.active ? 2.5 : 1.75} aria-hidden="true" />
      )}
      {scene.name}
    </button>
  );
}

// ---------------------------------------------------------------------------
// SceneCard — tall gradient card for the Scenes tab
// ---------------------------------------------------------------------------

interface SceneCardProps {
  scene: Scene;
  onPress: (scene: Scene) => Promise<void>;
}

function SceneCard({ scene, onPress }: SceneCardProps) {
  const [loading, setLoading] = useState(false);
  const [rippling, setRippling] = useState(false);
  const Icon = SCENE_ICON_MAP[scene.icon] ?? Zap;
  const gradientClass = SCENE_GRADIENT_MAP[scene.id] ?? "scene-gradient-music";

  const handlePress = useCallback(async () => {
    if (loading) return;
    setRippling(true);
    setTimeout(() => setRippling(false), 600);
    setLoading(true);
    try {
      await onPress(scene);
    } finally {
      setLoading(false);
    }
  }, [loading, onPress, scene]);

  return (
    <button
      onClick={handlePress}
      disabled={loading}
      aria-label={`Activate ${scene.name} scene`}
      aria-pressed={scene.active}
      className={[
        "relative flex flex-col justify-between p-4 rounded-2xl overflow-hidden",
        "aspect-[3/4] w-full text-left",
        "transition-all duration-200 select-none",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
        loading ? "opacity-70 cursor-wait" : "cursor-pointer active:scale-[0.97]",
        gradientClass,
      ].join(" ")}
      style={
        scene.active
          ? { boxShadow: "0 0 0 2px rgba(124,58,237,0.80), 0 0 28px rgba(124,58,237,0.40)" }
          : { boxShadow: "0 4px 24px rgba(0,0,0,0.50)" }
      }
    >
      {/* Ripple */}
      {rippling && (
        <span
          aria-hidden="true"
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <span
            className="block rounded-full bg-white/10"
            style={{ width: 240, height: 240, animation: "ripple 0.6s linear" }}
          />
        </span>
      )}

      {/* Shine overlay when active */}
      {scene.active && (
        <span
          aria-hidden="true"
          className="absolute inset-0 pointer-events-none rounded-2xl"
          style={{ background: "linear-gradient(135deg, rgba(255,255,255,0.07) 0%, transparent 60%)" }}
        />
      )}

      {/* Active dot */}
      {scene.active && (
        <span
          aria-hidden="true"
          className="absolute top-3 right-3 w-2 h-2 rounded-full status-online animate-pulse"
        />
      )}

      {/* Top — icon */}
      <span
        className="relative z-10 w-10 h-10 rounded-xl flex items-center justify-center"
        style={{
          background: scene.active ? "rgba(124,58,237,0.35)" : "rgba(255,255,255,0.08)",
          border: "1px solid rgba(255,255,255,0.10)",
        }}
      >
        {loading ? (
          <span
            className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white"
            style={{ animation: "spin 0.8s linear infinite" }}
            aria-hidden="true"
          />
        ) : (
          <Icon
            size={20}
            strokeWidth={scene.active ? 2.5 : 1.75}
            className={scene.active ? "text-aura-purple-light" : "text-white/70"}
            aria-hidden="true"
          />
        )}
      </span>

      {/* Bottom — name + description */}
      <div className="relative z-10 flex flex-col gap-1">
        <span className="font-bold text-sm text-white leading-tight">{scene.name}</span>
        <span className="text-[10px] leading-tight" style={{ color: "rgba(255,255,255,0.50)" }}>
          {scene.description}
        </span>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// NowPlayingCard — inline on Home tab
// ---------------------------------------------------------------------------

interface NowPlayingCardProps {
  state: NowPlayingState | null;
  onAction: (
    action: "media_play_pause" | "media_next_track" | "media_previous_track" | "volume_mute",
    entityId: string
  ) => Promise<void>;
}

function NowPlayingCard({ state, onAction }: NowPlayingCardProps) {
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const handleAction = async (
    action: "media_play_pause" | "media_next_track" | "media_previous_track" | "volume_mute"
  ) => {
    if (!state || actionLoading) return;
    setActionLoading(action);
    try {
      await onAction(action, state.entity_id);
    } finally {
      setActionLoading(null);
    }
  };

  const isPlaying     = state?.state === "playing";
  const isUnavailable = !state || state.state === "unavailable" || state.state === "off";

  return (
    <div
      className="glass-card rounded-2xl overflow-hidden"
      style={{ animation: "slide-up 0.4s ease-out both" }}
    >
      {/* Gradient header strip */}
      <div
        className="px-4 pt-4 pb-3"
        style={{
          background: isPlaying
            ? "linear-gradient(135deg, rgba(124,58,237,0.20) 0%, rgba(59,130,246,0.12) 100%)"
            : "transparent",
        }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Music2 size={14} className="text-aura-purple" aria-hidden="true" />
          <span className="text-xs font-semibold uppercase tracking-widest text-aura-text-muted">
            Now Playing
          </span>
          {isPlaying && (
            <span className="ml-auto flex items-end gap-0.5 h-4" aria-label="Playing" aria-hidden="true">
              <span className="w-0.5 rounded-full bg-aura-purple-light eq-bar-1" style={{ height: 6 }} />
              <span className="w-0.5 rounded-full bg-aura-purple-light eq-bar-2" style={{ height: 10 }} />
              <span className="w-0.5 rounded-full bg-aura-purple-light eq-bar-3" style={{ height: 14 }} />
              <span className="w-0.5 rounded-full bg-aura-purple-light eq-bar-4" style={{ height: 8 }} />
              <span className="w-0.5 rounded-full bg-aura-purple-light eq-bar-5" style={{ height: 5 }} />
            </span>
          )}
        </div>

        {isUnavailable ? (
          <div className="flex items-center gap-3 py-1">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: "rgba(26,26,62,0.60)", border: "1px solid rgba(124,58,237,0.12)" }}
            >
              <Music2 size={20} aria-hidden="true" style={{ color: "#1E1E40" }} />
            </div>
            <div>
              <p className="text-sm font-medium text-aura-text-muted">Nothing playing</p>
              <p className="text-xs" style={{ color: "rgba(100,116,139,0.60)" }}>Speaker offline or idle</p>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div
              className="relative w-12 h-12 rounded-xl overflow-hidden shrink-0"
              style={{ boxShadow: "0 0 12px rgba(124,58,237,0.30)" }}
            >
              {state.album_art_url ? (
                <Image
                  src={state.album_art_url}
                  alt={`Album art for ${state.album ?? "current track"}`}
                  fill
                  className="object-cover"
                  sizes="48px"
                />
              ) : (
                <div
                  className="w-full h-full flex items-center justify-center"
                  style={{ background: "linear-gradient(135deg, #4C1D95 0%, #12122A 100%)" }}
                >
                  <Music2 size={20} className="text-aura-purple-light" aria-hidden="true" />
                </div>
              )}
            </div>
            <div className="flex flex-col gap-0.5 min-w-0 flex-1">
              <p className="text-sm font-semibold text-aura-text truncate leading-tight">
                {state.title ?? "Unknown Track"}
              </p>
              <p className="text-xs text-aura-text-muted truncate">
                {state.artist ?? "Unknown Artist"}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between px-4 py-3" style={{ borderTop: "1px solid rgba(30,30,64,0.60)" }}>
        <button
          onClick={() => { /* shuffle — Phase 2 */ }}
          disabled={isUnavailable}
          aria-label="Toggle shuffle"
          className={[
            "p-2 rounded-lg transition-colors",
            isUnavailable ? "opacity-30 cursor-not-allowed" : "text-aura-text-muted hover:text-aura-purple-light active:scale-90",
          ].join(" ")}
        >
          <Shuffle size={14} aria-hidden="true" />
        </button>
        <button
          onClick={() => handleAction("media_previous_track")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Previous track"
          className={[
            "p-2 rounded-lg transition-all",
            isUnavailable || actionLoading ? "opacity-30 cursor-not-allowed" : "text-aura-text-muted hover:text-aura-text active:scale-90",
          ].join(" ")}
        >
          <SkipBack size={18} aria-hidden="true" />
        </button>
        <button
          onClick={() => handleAction("media_play_pause")}
          disabled={isUnavailable || !!actionLoading}
          aria-label={isPlaying ? "Pause" : "Play"}
          className={[
            "w-11 h-11 rounded-full flex items-center justify-center transition-all",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
            isUnavailable || actionLoading
              ? "cursor-not-allowed"
              : "active:scale-90",
          ].join(" ")}
          style={
            isUnavailable || actionLoading
              ? { background: "#1E1E40", color: "#64748B" }
              : { background: "linear-gradient(135deg, #7C3AED 0%, #3B82F6 100%)", color: "white", boxShadow: "0 0 16px rgba(124,58,237,0.45)" }
          }
        >
          {actionLoading === "media_play_pause" ? (
            <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white" style={{ animation: "spin 0.8s linear infinite" }} />
          ) : isPlaying ? (
            <Pause size={18} fill="currentColor" aria-hidden="true" />
          ) : (
            <Play size={18} fill="currentColor" className="ml-0.5" aria-hidden="true" />
          )}
        </button>
        <button
          onClick={() => handleAction("media_next_track")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Next track"
          className={[
            "p-2 rounded-lg transition-all",
            isUnavailable || actionLoading ? "opacity-30 cursor-not-allowed" : "text-aura-text-muted hover:text-aura-text active:scale-90",
          ].join(" ")}
        >
          <SkipForward size={18} aria-hidden="true" />
        </button>
        <button
          onClick={() => handleAction("volume_mute")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Toggle mute"
          className={[
            "p-2 rounded-lg transition-colors",
            isUnavailable || actionLoading ? "opacity-30 cursor-not-allowed" : "text-aura-text-muted hover:text-aura-purple-light",
          ].join(" ")}
        >
          {state?.volume === 0 ? <VolumeX size={14} aria-hidden="true" /> : <Volume2 size={14} aria-hidden="true" />}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProgressRing — circular SVG progress indicator for the habit tracker
// ---------------------------------------------------------------------------

function ProgressRing({ percent, size = 72 }: { percent: number; size?: number }) {
  const radius    = (size - 8) / 2;
  const circ      = 2 * Math.PI * radius;
  const offset    = circ - (percent / 100) * circ;
  const allDone   = percent >= 100;

  return (
    <svg width={size} height={size} aria-hidden="true" role="img">
      {/* Track */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#1E1E40"
        strokeWidth={6}
      />
      {/* Fill */}
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={allDone ? "#10B981" : "url(#ring-gradient)"}
        strokeWidth={6}
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        style={{
          transform: "rotate(-90deg)",
          transformOrigin: "50% 50%",
          transition: "stroke-dashoffset 0.6s ease",
          filter: allDone
            ? "drop-shadow(0 0 6px rgba(16,185,129,0.60))"
            : "drop-shadow(0 0 6px rgba(124,58,237,0.50))",
        }}
      />
      <defs>
        <linearGradient id="ring-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#7C3AED" />
          <stop offset="100%" stopColor="#3B82F6" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// HabitChip — toggleable chip for the Home tab habit section
// ---------------------------------------------------------------------------

function HabitChip({ habit, onToggle }: { habit: HabitEntry; onToggle: (id: string) => void }) {
  const HabitIcon = HABIT_ICON_MAP[habit.icon] ?? Star;

  return (
    <button
      onClick={() => onToggle(habit.id)}
      role="checkbox"
      aria-checked={habit.completed}
      aria-label={`${habit.name} — ${habit.completed ? "completed" : "pending"}`}
      className={[
        "flex items-center gap-2 px-3 py-2 rounded-xl",
        "text-xs font-medium transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
        "active:scale-[0.97] select-none",
        habit.completed
          ? "border border-aura-green/30"
          : "border border-aura-border/50 hover:border-aura-border",
      ].join(" ")}
      style={
        habit.completed
          ? { background: "rgba(16,185,129,0.10)" }
          : { background: "rgba(18,18,42,0.60)" }
      }
    >
      <span
        className={[
          "w-4 h-4 rounded-full border flex items-center justify-center shrink-0 transition-all",
          habit.completed ? "border-aura-green" : "border-aura-border",
        ].join(" ")}
        style={habit.completed ? { background: "#10B981" } : undefined}
        aria-hidden="true"
      >
        {habit.completed && <Check size={9} strokeWidth={3} className="text-white" />}
      </span>
      <HabitIcon
        size={12}
        className={habit.completed ? "text-aura-green shrink-0" : "text-aura-text-muted shrink-0"}
        aria-hidden="true"
      />
      <span className={habit.completed ? "text-aura-text line-through opacity-60" : "text-aura-text"}>
        {habit.name}
      </span>
      {habit.streak > 0 && (
        <span className="ml-auto flex items-center gap-0.5 shrink-0">
          <Flame size={10} className="text-aura-amber" aria-hidden="true" />
          <span className="text-aura-amber text-[10px] font-bold tabular-nums">{habit.streak}</span>
        </span>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// ClimateCard — temperature display on Home tab
// ---------------------------------------------------------------------------

const MODE_LABELS: Record<string, string> = {
  heat: "Heating", cool: "Cooling", heat_cool: "Auto",
  auto: "Auto", dry: "Dry", fan_only: "Fan", off: "Off",
};

interface ClimateCardProps {
  state: ClimateState | null;
  onSetTemperature: (entityId: string, newTemp: number) => Promise<void>;
}

function ClimateCard({ state, onSetTemperature }: ClimateCardProps) {
  const [pendingTemp, setPendingTemp] = useState<number | null>(null);
  const [adjusting, setAdjusting]     = useState(false);

  const displayTarget = pendingTemp ?? state?.target_temp ?? null;
  const isOff         = !state || state.mode === "off";

  const adjust = async (delta: number) => {
    if (!state || adjusting || isOff) return;
    const current = displayTarget ?? 20;
    const newTemp = Math.min(28, Math.max(16, current + delta));
    if (newTemp === current) return;
    setPendingTemp(newTemp);
    setAdjusting(true);
    try {
      await onSetTemperature(state.entity_id, newTemp);
    } catch {
      setPendingTemp(null);
    } finally {
      setAdjusting(false);
    }
  };

  return (
    <div className="glass-card rounded-2xl p-4" style={{ animation: "slide-up 0.4s ease-out both" }}>
      <div className="flex items-center gap-2 mb-4">
        <Thermometer size={14} className="text-aura-amber" aria-hidden="true" />
        <span className="text-xs font-semibold uppercase tracking-widest text-aura-text-muted">Climate</span>
        {state && (
          <span className="ml-auto text-xs font-medium text-aura-text-muted">
            {MODE_LABELS[state.mode] ?? state.mode}
          </span>
        )}
      </div>

      <div className="flex items-center justify-between gap-4">
        {/* Current */}
        <div className="flex flex-col items-center gap-0.5">
          <span className="text-[10px] text-aura-text-muted uppercase tracking-wider">Current</span>
          <span className="text-4xl font-black tabular-nums text-aura-text leading-none">
            {state?.current_temp != null ? `${state.current_temp}` : "--"}
          </span>
          <span className="text-xs text-aura-text-muted">°C</span>
        </div>

        <div className="h-12 w-px" style={{ background: "#1E1E40" }} aria-hidden="true" />

        {/* Target */}
        <div className="flex flex-col items-center gap-1">
          <span className="text-[10px] text-aura-text-muted uppercase tracking-wider">Target</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => adjust(-0.5)}
              disabled={isOff || adjusting}
              aria-label="Decrease target temperature"
              className={[
                "w-7 h-7 rounded-full border border-aura-border flex items-center justify-center transition-all",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
                isOff || adjusting ? "opacity-30 cursor-not-allowed" : "hover:border-aura-blue hover:text-aura-blue active:scale-90 cursor-pointer",
              ].join(" ")}
            >
              <Minus size={12} aria-hidden="true" />
            </button>
            <span className="text-2xl font-bold tabular-nums text-aura-purple-light w-12 text-center">
              {displayTarget != null ? `${displayTarget}°` : "--°"}
            </span>
            <button
              onClick={() => adjust(0.5)}
              disabled={isOff || adjusting}
              aria-label="Increase target temperature"
              className={[
                "w-7 h-7 rounded-full border border-aura-border flex items-center justify-center transition-all",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
                isOff || adjusting ? "opacity-30 cursor-not-allowed" : "hover:border-aura-amber hover:text-aura-amber active:scale-90 cursor-pointer",
              ].join(" ")}
            >
              <Plus size={12} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      {state?.humidity != null && (
        <div
          className="flex items-center gap-2 rounded-xl px-3 py-2 mt-3 border border-aura-border/40"
          style={{ background: "rgba(26,26,62,0.50)" }}
        >
          <Droplets size={12} className="text-aura-blue shrink-0" aria-hidden="true" />
          <span className="text-xs text-aura-text-muted">Humidity</span>
          <span className="text-xs font-semibold text-aura-text ml-auto">{state.humidity}%</span>
        </div>
      )}

      {!state && (
        <div
          className="flex items-center gap-2 rounded-xl px-3 py-2 mt-3"
          style={{ background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.20)" }}
        >
          <Wind size={12} className="text-aura-amber shrink-0" aria-hidden="true" />
          <p className="text-xs text-aura-text-muted">No thermostat connected</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DeviceRow — single device toggle row inside an expanded room
// ---------------------------------------------------------------------------

function DeviceRow({ device, onToggle }: { device: Device; onToggle: (device: Device) => Promise<void> }) {
  const [loading, setLoading] = useState(false);
  const isOn         = device.state === "on";
  const isToggleable = ["light", "switch", "fan", "input_boolean"].includes(device.domain);

  const handleToggle = async () => {
    if (!isToggleable || loading) return;
    setLoading(true);
    try { await onToggle(device); }
    finally { setLoading(false); }
  };

  return (
    <div className="flex items-center justify-between py-2.5" style={{ borderBottom: "1px solid rgba(30,30,64,0.50)" }}>
      <div className="flex items-center gap-2.5 min-w-0">
        <span
          className={["shrink-0 w-1.5 h-1.5 rounded-full", isOn ? "status-online" : "bg-aura-border"].join(" ")}
          aria-hidden="true"
        />
        <span className="text-sm text-aura-text truncate">{device.friendly_name}</span>
        {device.domain === "light" && isOn && typeof device.attributes["brightness"] === "number" && (
          <span className="shrink-0 text-xs text-aura-text-muted">
            {Math.round(((device.attributes["brightness"] as number) / 255) * 100)}%
          </span>
        )}
      </div>
      {isToggleable && (
        <button
          onClick={handleToggle}
          disabled={loading}
          aria-label={`Toggle ${device.friendly_name}`}
          aria-checked={isOn}
          role="switch"
          className={[
            "shrink-0 relative inline-flex h-5 w-9 items-center rounded-full",
            "transition-colors duration-200",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple focus-visible:ring-offset-2 focus-visible:ring-offset-aura-card",
            loading ? "opacity-50 cursor-wait" : "cursor-pointer",
            isOn ? "bg-aura-purple" : "bg-aura-border",
          ].join(" ")}
        >
          <span
            className={["inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform duration-200", isOn ? "translate-x-[18px]" : "translate-x-[3px]"].join(" ")}
          />
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RoomExpandableCard — for Rooms tab
// ---------------------------------------------------------------------------

function RoomExpandableCard({ room, onDeviceToggle }: { room: Room; onDeviceToggle: (device: Device) => Promise<void> }) {
  const [expanded, setExpanded] = useState(false);
  const RoomIcon    = ROOM_ICON_MAP[room.icon] ?? Home;
  const onlineCount = room.devices.filter((d) => d.state === "on").length;
  const totalCount  = room.devices.length;

  return (
    <div className="glass-card rounded-2xl overflow-hidden" style={{ animation: "slide-up 0.4s ease-out both" }}>
      {/* Header row — always visible */}
      <button
        onClick={() => setExpanded((p) => !p)}
        className="flex items-center gap-3 w-full p-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple focus-visible:ring-inset"
        aria-expanded={expanded}
      >
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: "rgba(124,58,237,0.12)", border: "1px solid rgba(124,58,237,0.20)" }}
        >
          <RoomIcon size={16} className="text-aura-purple-light" aria-hidden="true" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm text-aura-text">{room.name}</p>
          <p className="text-xs text-aura-text-muted mt-0.5">
            {totalCount === 0 ? "No devices" : `${totalCount} device${totalCount !== 1 ? "s" : ""}`}
          </p>
        </div>

        {/* Status + chevron */}
        <div className="flex items-center gap-3 shrink-0">
          {onlineCount > 0 ? (
            <span className="flex items-center gap-1.5 text-xs font-medium text-aura-green">
              <span className="w-1.5 h-1.5 rounded-full status-online" aria-hidden="true" />
              {onlineCount} on
            </span>
          ) : (
            <span className="text-xs text-aura-text-muted">All off</span>
          )}

          {expanded
            ? <ChevronUp size={14} className="text-aura-text-muted" aria-hidden="true" />
            : <ChevronDown size={14} className="text-aura-text-muted" aria-hidden="true" />
          }
        </div>
      </button>

      {/* Expanded device list */}
      {expanded && (
        <div
          className="px-4 pb-4"
          style={{ borderTop: "1px solid rgba(30,30,64,0.60)" }}
        >
          {room.devices.length === 0 ? (
            <div
              className="flex items-center gap-2 rounded-xl px-3 py-3 mt-3 border border-dashed"
              style={{ borderColor: "rgba(124,58,237,0.20)", background: "rgba(124,58,237,0.05)" }}
            >
              <Lightbulb size={14} className="text-aura-purple shrink-0" aria-hidden="true" />
              <p className="text-xs text-aura-text-muted">Connect HA to see live device states.</p>
            </div>
          ) : (
            <>
              <div className="flex flex-col mt-1">
                {room.devices.map((device) => (
                  <DeviceRow key={device.entity_id} device={device} onToggle={onDeviceToggle} />
                ))}
              </div>
              {onlineCount > 0 && (
                <button
                  onClick={async () => {
                    for (const device of room.devices.filter((d) => d.state === "on")) {
                      await onDeviceToggle(device);
                    }
                  }}
                  className="mt-3 flex items-center justify-center gap-1.5 w-full rounded-xl border border-aura-border/60 py-2 text-xs text-aura-text-muted hover:border-aura-red/50 hover:text-aura-red transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-red/50"
                >
                  <Power size={12} aria-hidden="true" />
                  Turn off all
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab views
// ---------------------------------------------------------------------------

interface HomeViewProps {
  time: string;
  date: string;
  residents: ResidentPresence[];
  scenes: Scene[];
  onScenePress: (scene: Scene) => Promise<void>;
  nowPlaying: NowPlayingState | null;
  onMediaAction: (
    action: "media_play_pause" | "media_next_track" | "media_previous_track" | "volume_mute",
    entityId: string
  ) => Promise<void>;
  climate: ClimateState | null;
  onSetTemperature: (entityId: string, temp: number) => Promise<void>;
  habits: HabitEntry[];
  onHabitToggle: (id: string) => void;
  haConnected: boolean;
}

function HomeView({
  time,
  date,
  residents,
  scenes,
  onScenePress,
  nowPlaying,
  onMediaAction,
  climate,
  onSetTemperature,
  habits,
  onHabitToggle,
  haConnected,
}: HomeViewProps) {
  const completedCount  = habits.filter((h) => h.completed).length;
  const totalCount      = habits.length;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <div className="tab-enter px-4 pt-6 pb-4 flex flex-col gap-6">
      {/* ── Clock hero ─────────────────────────────────────────── */}
      <div className="flex flex-col items-center pt-2 pb-1">
        {/* AURA wordmark */}
        <p
          className="text-xs font-black tracking-[0.35em] uppercase mb-4 wordmark-glow"
          style={{
            backgroundImage: "linear-gradient(135deg, #9F67FF 0%, #60A5FA 60%, #9F67FF 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          AURA
        </p>

        {/* Time */}
        <p
          className="font-black tabular-nums leading-none tracking-tight text-aura-text"
          style={{ fontSize: "clamp(64px, 20vw, 88px)" }}
          aria-label={`Current time: ${time}`}
        >
          {time}
        </p>

        {/* Date */}
        <p className="text-sm text-aura-text-muted mt-2 tracking-wide">{date}</p>

        {/* Connection badge */}
        <div className="mt-3">
          {haConnected ? (
            <div
              className="flex items-center gap-1.5 rounded-full px-3 py-1"
              style={{ background: "rgba(16,185,129,0.10)", border: "1px solid rgba(16,185,129,0.22)" }}
            >
              <Wifi size={10} className="text-aura-green" aria-hidden="true" />
              <span className="text-xs font-medium text-aura-green">Connected</span>
            </div>
          ) : (
            <div
              className="flex items-center gap-1.5 rounded-full px-3 py-1"
              style={{ background: "rgba(245,158,11,0.10)", border: "1px solid rgba(245,158,11,0.22)" }}
            >
              <WifiOff size={10} className="text-aura-amber" aria-hidden="true" />
              <span className="text-xs font-medium text-aura-amber">Scaffold mode</span>
            </div>
          )}
        </div>

        {/* Presence pills */}
        <div className="flex items-center gap-3 mt-4" aria-label="Who is home">
          {residents.map((r) => (
            <div
              key={r.name}
              className="flex items-center gap-2 rounded-full px-4 py-1.5"
              style={{
                background: r.home ? "rgba(16,185,129,0.12)" : "rgba(18,18,42,0.70)",
                border: r.home ? "1px solid rgba(16,185,129,0.28)" : "1px solid rgba(30,30,64,0.80)",
              }}
            >
              <span
                className={["w-2 h-2 rounded-full shrink-0", r.home ? "status-online" : "bg-aura-border"].join(" ")}
                aria-hidden="true"
              />
              <span className={["text-xs font-semibold", r.home ? "text-aura-green" : "text-aura-text-muted"].join(" ")}>
                {r.name}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Quick scenes ────────────────────────────────────────── */}
      <div>
        <SectionHeader>Scenes</SectionHeader>
        <div
          className="flex gap-2 overflow-x-auto scroll-hide pb-1"
          role="list"
          aria-label="Quick scene selection"
        >
          {scenes.map((scene) => (
            <div key={scene.id} role="listitem">
              <ScenePill scene={scene} onPress={onScenePress} />
            </div>
          ))}
        </div>
      </div>

      {/* ── Now Playing ─────────────────────────────────────────── */}
      <div>
        <SectionHeader>Now Playing</SectionHeader>
        <NowPlayingCard state={nowPlaying} onAction={onMediaAction} />
      </div>

      {/* ── Climate ─────────────────────────────────────────────── */}
      <div>
        <SectionHeader>Climate</SectionHeader>
        <ClimateCard state={climate} onSetTemperature={onSetTemperature} />
      </div>

      {/* ── Habit tracker ───────────────────────────────────────── */}
      <div>
        <SectionHeader>Today</SectionHeader>
        <div className="glass-card rounded-2xl p-4">
          {/* Ring + count */}
          <div className="flex items-center gap-4 mb-4">
            <div className="relative shrink-0">
              <ProgressRing percent={progressPercent} size={72} />
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-lg font-black tabular-nums text-aura-text leading-none">
                  {completedCount}
                </span>
                <span className="text-[9px] text-aura-text-muted">/{totalCount}</span>
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-semibold text-sm text-aura-text leading-tight">
                {completedCount === totalCount && totalCount > 0
                  ? "All habits done"
                  : `${totalCount - completedCount} left today`}
              </p>
              <p className="text-xs text-aura-text-muted mt-0.5">
                {progressPercent === 0
                  ? "Tap a habit to mark it complete"
                  : progressPercent < 100
                  ? "Keep going"
                  : "Outstanding work"}
              </p>
            </div>
          </div>

          {/* Habit chips */}
          <div className="flex flex-col gap-2">
            {habits.map((habit) => (
              <HabitChip key={habit.id} habit={habit} onToggle={onHabitToggle} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

interface ScenesViewProps {
  scenes: Scene[];
  onScenePress: (scene: Scene) => Promise<void>;
}

function ScenesView({ scenes, onScenePress }: ScenesViewProps) {
  return (
    <div className="tab-enter px-4 pt-6 pb-4">
      <SectionHeader>All Scenes</SectionHeader>
      <div className="grid grid-cols-2 gap-3" role="list" aria-label="All scenes">
        {scenes.map((scene) => (
          <div key={scene.id} role="listitem">
            <SceneCard scene={scene} onPress={onScenePress} />
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

interface RoomsViewProps {
  rooms: Room[];
  onDeviceToggle: (device: Device) => Promise<void>;
}

function RoomsView({ rooms, onDeviceToggle }: RoomsViewProps) {
  return (
    <div className="tab-enter px-4 pt-6 pb-4 flex flex-col gap-3">
      <SectionHeader>Rooms</SectionHeader>
      {rooms.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <DoorOpen size={48} className="text-aura-border mb-4" aria-hidden="true" />
          <p className="text-aura-text font-semibold">No rooms configured</p>
          <p className="text-aura-text-muted text-sm mt-1">Connect Home Assistant to see your rooms</p>
        </div>
      ) : (
        rooms.map((room) => (
          <RoomExpandableCard key={room.name} room={room} onDeviceToggle={onDeviceToggle} />
        ))
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "never";
  const diff    = Date.now() - new Date(isoString).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

interface ProfileViewProps {
  residents: ResidentPresence[];
  status: AuraStatus;
}

function ProfileView({ residents, status }: ProfileViewProps) {
  const runningServices = status.services.filter((s) => s.running).length;
  const totalServices   = status.services.length;

  return (
    <div className="tab-enter px-4 pt-6 pb-4 flex flex-col gap-6">
      {/* Wordmark */}
      <div className="flex flex-col items-center py-4">
        <p
          className="text-3xl font-black tracking-[0.22em] wordmark-glow"
          style={{
            backgroundImage: "linear-gradient(135deg, #9F67FF 0%, #60A5FA 50%, #9F67FF 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          AURA
        </p>
        <p className="text-xs text-aura-text-muted mt-1 tracking-widest uppercase">by OASIS AI Solutions</p>
      </div>

      {/* Who's home */}
      <div>
        <SectionHeader>Who&apos;s Home</SectionHeader>
        <div className="glass-card rounded-2xl p-4 flex flex-col gap-3">
          {residents.map((r) => (
            <div key={r.name} className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 font-bold text-sm"
                style={{
                  background: r.home ? "rgba(16,185,129,0.15)" : "rgba(18,18,42,0.80)",
                  border: r.home ? "1px solid rgba(16,185,129,0.35)" : "1px solid rgba(30,30,64,0.80)",
                  color: r.home ? "#10B981" : "#64748B",
                }}
              >
                {r.name.slice(0, 2).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-aura-text">{r.name}</p>
                <p className="text-xs text-aura-text-muted">
                  {r.home ? "At home" : r.last_seen ? `Last seen ${formatRelativeTime(r.last_seen)}` : "Away"}
                </p>
              </div>
              <span
                className={["w-2.5 h-2.5 rounded-full shrink-0", r.home ? "status-online animate-pulse" : "bg-aura-border"].join(" ")}
                aria-hidden="true"
              />
            </div>
          ))}
        </div>
      </div>

      {/* System status */}
      <div>
        <SectionHeader>System Status</SectionHeader>
        <div className="glass-card rounded-2xl p-4 flex flex-col gap-3">
          {/* Pi */}
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: "rgba(18,18,42,0.80)", border: "1px solid rgba(30,30,64,0.80)" }}
            >
              <Server size={15} className="text-aura-text-muted" aria-hidden="true" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-aura-text">Raspberry Pi</p>
              <p className={["text-xs font-semibold", status.pi_online ? "text-aura-green" : "text-aura-red"].join(" ")}>
                {status.pi_online ? "Online" : "Offline"}
              </p>
            </div>
            <span
              className={["w-2 h-2 rounded-full shrink-0", status.pi_online ? "status-online animate-pulse" : "status-offline"].join(" ")}
              aria-hidden="true"
            />
          </div>

          <div style={{ height: 1, background: "rgba(30,30,64,0.60)" }} aria-hidden="true" />

          {/* Services */}
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0"
              style={{ background: "rgba(18,18,42,0.80)", border: "1px solid rgba(30,30,64,0.80)" }}
            >
              <Activity size={15} className="text-aura-text-muted" aria-hidden="true" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-aura-text">Services</p>
              <p className="text-xs text-aura-text-muted">
                {totalServices === 0 ? "None configured" : `${runningServices} of ${totalServices} running`}
              </p>
            </div>
          </div>

          {/* Per-service rows */}
          {status.services.length > 0 && (
            <div
              className="rounded-xl overflow-hidden"
              style={{ background: "rgba(18,18,42,0.50)", border: "1px solid rgba(30,30,64,0.50)" }}
            >
              {status.services.map((svc, idx) => (
                <div
                  key={svc.name}
                  className="flex items-center justify-between px-3 py-2"
                  style={idx < status.services.length - 1 ? { borderBottom: "1px solid rgba(30,30,64,0.50)" } : undefined}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={["w-1.5 h-1.5 rounded-full shrink-0", svc.running ? "status-online" : "status-offline"].join(" ")}
                      aria-hidden="true"
                    />
                    <span className="text-xs text-aura-text-muted">{svc.name}</span>
                  </div>
                  <span className="text-xs" style={{ color: "rgba(100,116,139,0.60)" }}>
                    {svc.running ? "running" : `stopped · ${formatRelativeTime(svc.last_seen)}`}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Last command */}
          <div style={{ height: 1, background: "rgba(30,30,64,0.60)" }} aria-hidden="true" />
          <div className="flex items-start gap-2">
            <Terminal size={13} className="text-aura-purple shrink-0 mt-0.5" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="text-xs text-aura-text-muted mb-0.5">Last command</p>
              <p className="text-xs text-aura-text truncate">{status.last_command ?? "None yet"}</p>
            </div>
            {status.last_command_time && (
              <div className="flex items-center gap-1 shrink-0">
                <Clock3 size={10} className="text-aura-text-muted" aria-hidden="true" />
                <span className="text-xs text-aura-text-muted">{formatRelativeTime(status.last_command_time)}</span>
              </div>
            )}
          </div>

          {status.uptime && (
            <p className="text-xs text-aura-text-muted text-center">
              Uptime: <span className="text-aura-text font-medium">{status.uptime}</span>
            </p>
          )}
        </div>
      </div>

      {/* Version */}
      <p className="text-center text-xs pb-2" style={{ color: "rgba(100,116,139,0.40)" }}>
        AURA v0.1.0 &middot; OASIS AI Solutions
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const { time, date } = useCurrentTime();

  const [activeTab, setActiveTab]   = useState<Tab>("home");
  const [scenes, setScenes]         = useState<Scene[]>(PLACEHOLDER_SCENES);
  const [rooms]                     = useState<Room[]>(PLACEHOLDER_ROOMS);
  const [habits, setHabits]         = useState<HabitEntry[]>(DEFAULT_HABITS);
  const [residents]                 = useState<ResidentPresence[]>(PLACEHOLDER_RESIDENTS);
  const [auraStatus]                = useState<AuraStatus>(PLACEHOLDER_STATUS);
  const [haConnected]               = useState(false);

  const nowPlaying: NowPlayingState | null = null;
  const climateState: ClimateState | null  = null;

  // Scene activation
  const handleScenePress = useCallback(async (pressedScene: Scene) => {
    setScenes((prev) => prev.map((s) => ({ ...s, active: s.id === pressedScene.id })));
    const res = await fetch("/api/scene", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ webhook_id: pressedScene.webhook_id }),
    });
    if (!res.ok) {
      setScenes((prev) => prev.map((s) => ({ ...s, active: false })));
      throw new Error(`Webhook failed: ${res.status}`);
    }
  }, []);

  // Device toggle
  const handleDeviceToggle = useCallback(async (device: Device) => {
    const service = device.state === "on" ? "turn_off" : "turn_on";
    const res = await fetch("/api/service", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain: device.domain, service, entity_id: device.entity_id }),
    });
    if (!res.ok) throw new Error(`Service call failed: ${res.status}`);
  }, []);

  // Media controls
  const handleMediaAction = useCallback(
    async (
      action: "media_play_pause" | "media_next_track" | "media_previous_track" | "volume_mute",
      entityId: string
    ) => {
      const res = await fetch("/api/service", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain: "media_player", service: action, entity_id: entityId }),
      });
      if (!res.ok) throw new Error(`Media service call failed: ${res.status}`);
    },
    []
  );

  // Climate control
  const handleSetTemperature = useCallback(async (entityId: string, newTemp: number) => {
    const res = await fetch("/api/service", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain: "climate", service: "set_temperature", entity_id: entityId, data: { temperature: newTemp } }),
    });
    if (!res.ok) throw new Error(`Climate service call failed: ${res.status}`);
  }, []);

  // Habit toggle
  const handleHabitToggle = useCallback((habitId: string) => {
    setHabits((prev) =>
      prev.map((h) =>
        h.id === habitId
          ? { ...h, completed: !h.completed, streak: !h.completed ? h.streak + 1 : Math.max(0, h.streak - 1) }
          : h
      )
    );
  }, []);

  // Tab navigation config
  const TABS: { id: Tab; icon: React.ComponentType<LucideProps>; label: string }[] = [
    { id: "home",    icon: Home,    label: "Home"   },
    { id: "scenes",  icon: Grid3X3, label: "Scenes" },
    { id: "rooms",   icon: DoorOpen, label: "Rooms" },
    { id: "profile", icon: User,    label: "Profile" },
  ];

  return (
    <div className="min-h-dvh pb-24 max-w-lg mx-auto">

      {/* ── Tab content ─────────────────────────────────────────── */}
      {activeTab === "home" && (
        <HomeView
          time={time}
          date={date}
          residents={residents}
          scenes={scenes}
          onScenePress={handleScenePress}
          nowPlaying={nowPlaying}
          onMediaAction={handleMediaAction}
          climate={climateState}
          onSetTemperature={handleSetTemperature}
          habits={habits}
          onHabitToggle={handleHabitToggle}
          haConnected={haConnected}
        />
      )}
      {activeTab === "scenes" && (
        <ScenesView scenes={scenes} onScenePress={handleScenePress} />
      )}
      {activeTab === "rooms" && (
        <RoomsView rooms={rooms} onDeviceToggle={handleDeviceToggle} />
      )}
      {activeTab === "profile" && (
        <ProfileView residents={residents} status={auraStatus} />
      )}

      {/* ── Bottom navigation ───────────────────────────────────── */}
      <nav className="bottom-nav" aria-label="Main navigation">
        <div className="flex items-center justify-around py-2 px-2 max-w-lg mx-auto">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                aria-label={`Go to ${tab.label}`}
                aria-current={isActive ? "page" : undefined}
                className={[
                  "relative flex flex-col items-center gap-1 py-2 px-5 rounded-2xl",
                  "transition-all duration-200 select-none",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
                  "active:scale-95",
                  isActive ? "text-aura-purple-light" : "text-aura-text-muted hover:text-aura-text",
                ].join(" ")}
                style={
                  isActive
                    ? { background: "rgba(124,58,237,0.12)" }
                    : undefined
                }
              >
                <tab.icon
                  size={20}
                  strokeWidth={isActive ? 2.5 : 1.5}
                  aria-hidden="true"
                />
                <span className="text-[10px] font-semibold">{tab.label}</span>
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute -bottom-0 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full"
                    style={{ background: "#9F67FF" }}
                  />
                )}
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
