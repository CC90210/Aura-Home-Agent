"use client";

import { useState, useEffect, useCallback } from "react";
import { Wifi, WifiOff, RefreshCw } from "lucide-react";
import { SceneButton } from "@/components/SceneButton";
import { RoomCard } from "@/components/RoomCard";
import { NowPlaying } from "@/components/NowPlaying";
import { ClimateControl } from "@/components/ClimateControl";
import { HabitTracker } from "@/components/HabitTracker";
import { StatusBar } from "@/components/StatusBar";
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
// Seed / placeholder data — replaced by live HA data once connected
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
  { name: "Living Room", icon: "Sofa",    temperature: null, devices: [] },
  { name: "Bedroom",     icon: "BedDouble", temperature: null, devices: [] },
  { name: "Kitchen",     icon: "UtensilsCrossed", temperature: null, devices: [] },
];

const DEFAULT_HABITS: HabitEntry[] = [
  { id: "gym",       name: "Gym",                icon: "Dumbbell", target_time: "09:00", completed: false, streak: 0 },
  { id: "meals",     name: "Meals tracked",       icon: "Salad",    target_time: "20:00", completed: false, streak: 0 },
  { id: "deep-work", name: "Deep work",            icon: "Monitor",  target_time: "13:00", completed: false, streak: 0 },
  { id: "bedtime",   name: "Bedtime by midnight",  icon: "Moon",     target_time: "23:59", completed: false, streak: 0 },
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

function useCurrentTime(): string {
  const [time, setTime] = useState(() =>
    new Date().toLocaleTimeString("en-CA", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })
  );

  useEffect(() => {
    const tick = () =>
      setTime(
        new Date().toLocaleTimeString("en-CA", {
          hour: "2-digit",
          minute: "2-digit",
          hour12: false,
        })
      );
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return time;
}

function useCurrentDate(): string {
  return new Date().toLocaleDateString("en-CA", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const currentTime = useCurrentTime();
  const currentDate = useCurrentDate();

  const [scenes, setScenes]   = useState<Scene[]>(PLACEHOLDER_SCENES);
  const [rooms]               = useState<Room[]>(PLACEHOLDER_ROOMS);
  const [habits, setHabits]   = useState<HabitEntry[]>(DEFAULT_HABITS);
  const [residents]           = useState<ResidentPresence[]>(PLACEHOLDER_RESIDENTS);
  const [auraStatus]          = useState<AuraStatus>(PLACEHOLDER_STATUS);
  const [haConnected]         = useState(false);

  const nowPlaying: NowPlayingState | null  = null;
  const climateState: ClimateState | null   = null;

  // Scene activation — fires HA webhook, optimistic update
  const handleScenePress = useCallback(async (pressedScene: Scene) => {
    setScenes((prev) =>
      prev.map((s) => ({ ...s, active: s.id === pressedScene.id }))
    );

    const res = await fetch(`/api/scene`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ webhook_id: pressedScene.webhook_id }),
    });

    if (!res.ok) {
      setScenes((prev) => prev.map((s) => ({ ...s, active: false })));
      throw new Error(`Webhook failed: ${res.status}`);
    }
  }, []);

  // Device toggle — calls HA service via server-side route
  const handleDeviceToggle = useCallback(async (device: Device) => {
    const service = device.state === "on" ? "turn_off" : "turn_on";
    const res = await fetch(`/api/service`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain: device.domain, service, entity_id: device.entity_id }),
    });
    if (!res.ok) throw new Error(`Service call failed: ${res.status}`);
  }, []);

  // Media player controls
  const handleMediaAction = useCallback(
    async (
      action: "media_play_pause" | "media_next_track" | "media_previous_track" | "volume_mute",
      entityId: string
    ) => {
      const res = await fetch(`/api/service`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain: "media_player", service: action, entity_id: entityId }),
      });
      if (!res.ok) throw new Error(`Media service call failed: ${res.status}`);
    },
    []
  );

  // Climate control
  const handleSetTemperature = useCallback(
    async (entityId: string, newTemp: number) => {
      const res = await fetch(`/api/service`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: "climate",
          service: "set_temperature",
          entity_id: entityId,
          data: { temperature: newTemp },
        }),
      });
      if (!res.ok) throw new Error(`Climate service call failed: ${res.status}`);
    },
    []
  );

  // Habit toggle
  const handleHabitToggle = useCallback((habitId: string) => {
    setHabits((prev) =>
      prev.map((h) =>
        h.id === habitId
          ? {
              ...h,
              completed: !h.completed,
              streak: !h.completed ? h.streak + 1 : Math.max(0, h.streak - 1),
            }
          : h
      )
    );
  }, []);

  const anyoneHome = residents.some((r) => r.home);

  return (
    <main className="min-h-dvh px-4 py-6 max-w-2xl mx-auto">

      {/* ── HEADER ──────────────────────────────────────────────── */}
      <header
        className="flex items-start justify-between mb-8"
        style={{ animation: "fade-in 0.4s ease-out" }}
      >
        {/* Left — wordmark + status */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline gap-2.5">
            <h1
              className="text-3xl font-black tracking-[0.22em] text-transparent bg-clip-text"
              style={{
                backgroundImage:
                  "linear-gradient(135deg, #9F67FF 0%, #60A5FA 50%, #9F67FF 100%)",
              }}
            >
              AURA
            </h1>
            <span className="text-xs font-semibold text-aura-text-muted tracking-widest uppercase">
              by OASIS
            </span>
          </div>

          {/* Date + connection badge */}
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-xs text-aura-text-muted">{currentDate}</p>
            <span className="text-aura-border" aria-hidden="true">·</span>
            {haConnected ? (
              <div className="flex items-center gap-1.5 bg-aura-green/10 border border-aura-green/20 rounded-full px-2 py-0.5">
                <Wifi size={9} className="text-aura-green" aria-hidden="true" />
                <span className="text-xs text-aura-green font-medium">Connected</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 bg-aura-amber/10 border border-aura-amber/20 rounded-full px-2 py-0.5">
                <WifiOff size={9} className="text-aura-amber" aria-hidden="true" />
                <span className="text-xs text-aura-amber font-medium">Scaffold</span>
              </div>
            )}
          </div>
        </div>

        {/* Right — clock + presence */}
        <div className="flex flex-col items-end gap-2">
          <p
            className="text-5xl font-black tabular-nums text-aura-text tracking-tight leading-none"
            aria-label={`Current time: ${currentTime}`}
          >
            {currentTime}
          </p>

          {/* Presence indicators */}
          <div className="flex items-center gap-3" aria-label="Who is home">
            {residents.map((resident) => (
              <div key={resident.name} className="flex items-center gap-1.5">
                <span
                  className={[
                    "w-2 h-2 rounded-full shrink-0",
                    resident.home ? "status-online" : "bg-aura-border",
                  ].join(" ")}
                  aria-hidden="true"
                />
                <span
                  className={[
                    "text-xs font-medium",
                    resident.home ? "text-aura-text" : "text-aura-text-muted",
                  ].join(" ")}
                >
                  {resident.name}
                </span>
              </div>
            ))}
          </div>

          {anyoneHome && (
            <span className="text-xs bg-aura-green/12 text-aura-green border border-aura-green/22 rounded-full px-2 py-0.5 font-medium">
              Home
            </span>
          )}
        </div>
      </header>

      {/* ── SCENES ──────────────────────────────────────────────── */}
      <section
        aria-label="Quick scenes"
        className="mb-6"
        style={{ animation: "slide-up 0.4s ease-out 0.05s both" }}
      >
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold text-aura-text-muted uppercase tracking-wider">
            Scenes
          </h2>
          <button
            className="flex items-center gap-1.5 text-xs text-aura-text-muted hover:text-aura-purple-light transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple rounded"
            aria-label="Refresh scene states"
          >
            <RefreshCw size={11} aria-hidden="true" />
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-3 gap-2.5">
          {scenes.map((scene) => (
            <SceneButton key={scene.id} scene={scene} onPress={handleScenePress} />
          ))}
        </div>
      </section>

      {/* ── MUSIC + CLIMATE ─────────────────────────────────────── */}
      <section
        aria-label="Media and climate"
        className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4"
        style={{ animation: "slide-up 0.4s ease-out 0.10s both" }}
      >
        <NowPlaying state={nowPlaying} onAction={handleMediaAction} />
        <ClimateControl state={climateState} onSetTemperature={handleSetTemperature} />
      </section>

      {/* ── ROOMS ───────────────────────────────────────────────── */}
      <section
        aria-label="Room controls"
        className="mb-4"
        style={{ animation: "slide-up 0.4s ease-out 0.15s both" }}
      >
        <h2 className="text-xs font-semibold text-aura-text-muted uppercase tracking-wider mb-3">
          Rooms
        </h2>
        <div className="grid grid-cols-1 gap-4">
          {rooms.map((room) => (
            <RoomCard key={room.name} room={room} onDeviceToggle={handleDeviceToggle} />
          ))}
        </div>
      </section>

      {/* ── HABITS + STATUS ─────────────────────────────────────── */}
      <section
        aria-label="Habits and system status"
        className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8"
        style={{ animation: "slide-up 0.4s ease-out 0.20s both" }}
      >
        <HabitTracker habits={habits} onToggle={handleHabitToggle} />
        <StatusBar status={auraStatus} />
      </section>

      {/* ── FOOTER ──────────────────────────────────────────────── */}
      <footer className="text-center pb-safe">
        <p className="text-xs text-aura-text-muted/35 tracking-wide">
          AURA by OASIS AI Solutions &middot; v0.1.0
        </p>
      </footer>
    </main>
  );
}
