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
  Menu,
  X,
  ChevronRight,
  type LucideProps,
} from "lucide-react";
import Image from "next/image";
import s from "./dashboard.module.css";
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
// Icon maps
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

// ---------------------------------------------------------------------------
// Seed / placeholder data  (identical to before — API patterns preserved)
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
// Cookie helper
// ---------------------------------------------------------------------------

type AuraUser = "conaugh" | "adon";

/**
 * Reads the `aura-user` cookie set by /api/auth at login.
 * Returns "conaugh" when the cookie is absent or unrecognised.
 * Runs client-side only — safe to call inside useEffect or useState initialisers.
 */
function readAuraUserCookie(): AuraUser {
  if (typeof document === "undefined") return "conaugh";
  const match = document.cookie.split("; ").find((row) => row.startsWith("aura-user="));
  if (!match) return "conaugh";
  const value = match.split("=")[1];
  return value === "adon" ? "adon" : "conaugh";
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

function useCurrentTime(): { time: string; date: string; greeting: string } {
  const [time, setTime] = useState(() =>
    new Date().toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit", hour12: false })
  );
  const [date] = useState(() =>
    new Date().toLocaleDateString("en-CA", { weekday: "long", month: "long", day: "numeric" })
  );

  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  };

  const [greeting] = useState(getGreeting);

  useEffect(() => {
    const tick = () =>
      setTime(new Date().toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit", hour12: false }));
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return { time, date, greeting };
}

// ---------------------------------------------------------------------------
// SceneCard — compact grid card
// ---------------------------------------------------------------------------

interface SceneCardProps {
  scene: Scene;
  onPress: (scene: Scene) => Promise<void>;
}

function SceneCard({ scene, onPress }: SceneCardProps) {
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
      className={[s.sceneCard, scene.active ? s.sceneCardActive : ""].join(" ")}
    >
      {scene.active && <span className={s.sceneActiveDot} aria-hidden="true" />}
      <span className={s.sceneIconWrap}>
        {loading ? (
          <span className={s.spinner} aria-hidden="true" />
        ) : (
          <Icon size={20} strokeWidth={scene.active ? 2.5 : 1.75} aria-hidden="true" />
        )}
      </span>
      <span className={s.sceneName}>{scene.name}</span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// NowPlayingCard
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
    <div className={s.infoCard} style={isPlaying ? { background: "linear-gradient(135deg, rgba(18,18,42,1) 0%, rgba(28,18,52,1) 100%)" } : undefined}>
      <div className={s.nowPlayingHeader}>
        <Music2 size={14} style={{ color: "#7C3AED" }} aria-hidden="true" />
        <span className={s.nowPlayingTitle}>Now Playing</span>
        {isPlaying && (
          <span className={s.eqBars} aria-label="Playing">
            <span className={[s.eqBar, s.eqBar1].join(" ")} style={{ height: 6 }} />
            <span className={[s.eqBar, s.eqBar2].join(" ")} style={{ height: 10 }} />
            <span className={[s.eqBar, s.eqBar3].join(" ")} style={{ height: 14 }} />
            <span className={[s.eqBar, s.eqBar4].join(" ")} style={{ height: 8 }} />
            <span className={[s.eqBar, s.eqBar5].join(" ")} style={{ height: 5 }} />
          </span>
        )}
      </div>

      {isUnavailable ? (
        <div className={s.offlineNote}>
          <div className={s.offlineArtPlaceholder}>
            <Music2 size={20} style={{ color: "#1E1E40" }} aria-hidden="true" />
          </div>
          <div>
            <div className={s.offlineLabel}>Nothing playing</div>
            <div className={s.offlineSub}>Speaker offline or idle</div>
          </div>
        </div>
      ) : (
        <div className={s.trackInfo}>
          <div className={s.albumArt}>
            {state.album_art_url ? (
              <Image
                src={state.album_art_url}
                alt={`Album art for ${state.album ?? "current track"}`}
                fill
                sizes="52px"
                style={{ objectFit: "cover" }}
              />
            ) : (
              <Music2 size={20} style={{ color: "#A78BFA" }} aria-hidden="true" />
            )}
          </div>
          <div className={s.trackMeta}>
            <div className={s.trackTitle}>{state.title ?? "Unknown Track"}</div>
            <div className={s.trackArtist}>{state.artist ?? "Unknown Artist"}</div>
          </div>
        </div>
      )}

      <div className={s.mediaControls}>
        <button
          onClick={() => { /* shuffle — Phase 2 */ }}
          disabled={isUnavailable}
          aria-label="Toggle shuffle"
          className={s.mediaBtn}
        >
          <Shuffle size={14} aria-hidden="true" />
        </button>
        <button
          onClick={() => handleAction("media_previous_track")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Previous track"
          className={s.mediaBtn}
        >
          <SkipBack size={18} aria-hidden="true" />
        </button>
        <button
          onClick={() => handleAction("media_play_pause")}
          disabled={isUnavailable || !!actionLoading}
          aria-label={isPlaying ? "Pause" : "Play"}
          className={s.playBtn}
        >
          {actionLoading === "media_play_pause" ? (
            <span className={s.spinner} aria-hidden="true" />
          ) : isPlaying ? (
            <Pause size={18} fill="currentColor" aria-hidden="true" />
          ) : (
            <Play size={18} fill="currentColor" style={{ marginLeft: 2 }} aria-hidden="true" />
          )}
        </button>
        <button
          onClick={() => handleAction("media_next_track")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Next track"
          className={s.mediaBtn}
        >
          <SkipForward size={18} aria-hidden="true" />
        </button>
        <button
          onClick={() => handleAction("volume_mute")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Toggle mute"
          className={s.mediaBtn}
        >
          {state?.volume === 0 ? <VolumeX size={14} aria-hidden="true" /> : <Volume2 size={14} aria-hidden="true" />}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// HabitsCard
// ---------------------------------------------------------------------------

interface HabitsCardProps {
  habits: HabitEntry[];
  onToggle: (id: string) => void;
}

function HabitsCard({ habits, onToggle }: HabitsCardProps) {
  const completedCount = habits.filter((h) => h.completed).length;
  const totalCount     = habits.length;

  return (
    <div className={s.infoCard}>
      <div className={s.habitsHeader}>
        <span className={s.habitsTitle}>Today&apos;s Habits</span>
        <span className={s.habitsProgress}>
          <span className={s.habitsProgressCount}>{completedCount}</span>/{totalCount}
        </span>
      </div>
      {habits.map((habit) => {
        const HabitIcon = HABIT_ICON_MAP[habit.icon] ?? Star;
        return (
          <div
            key={habit.id}
            className={s.habitRow}
            onClick={() => onToggle(habit.id)}
            role="checkbox"
            aria-checked={habit.completed}
            aria-label={`${habit.name} — ${habit.completed ? "completed" : "pending"}`}
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === " " || e.key === "Enter") onToggle(habit.id); }}
          >
            <div className={[s.habitCheckbox, habit.completed ? s.habitCheckboxDone : ""].join(" ")} aria-hidden="true">
              {habit.completed && <Check size={11} strokeWidth={3} style={{ color: "white" }} />}
            </div>
            <HabitIcon
              size={13}
              style={{ color: habit.completed ? "#10B981" : "#64748B", flexShrink: 0 }}
              aria-hidden="true"
            />
            <span className={[s.habitName, habit.completed ? s.habitNameDone : ""].join(" ")}>
              {habit.name}
            </span>
            {habit.streak > 0 && (
              <span className={s.habitStreak}>
                <Flame size={11} aria-hidden="true" />
                {habit.streak}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ClimateCard
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
    <div className={s.climateCard}>
      <div className={s.climateHeader}>
        <Thermometer size={14} style={{ color: "#F59E0B" }} aria-hidden="true" />
        <span className={s.climateTitle}>Climate</span>
        {state && (
          <span className={s.climateMode}>{MODE_LABELS[state.mode] ?? state.mode}</span>
        )}
      </div>

      <div className={s.climateBody}>
        <div className={s.climateTempBlock}>
          <span className={s.climateTempLabel}>Current</span>
          <span className={s.climateTempValue}>
            {state?.current_temp != null ? `${state.current_temp}` : "--"}
          </span>
          <span className={s.climateTempUnit}>°C</span>
        </div>

        <div className={s.climateDivider} aria-hidden="true" />

        <div className={s.climateTempBlock}>
          <span className={s.climateTempLabel}>Target</span>
          <div className={s.climateTargetControls}>
            <button
              onClick={() => adjust(-0.5)}
              disabled={isOff || adjusting}
              aria-label="Decrease target temperature"
              className={s.climateAdjBtn}
            >
              <Minus size={12} aria-hidden="true" />
            </button>
            <span className={s.climateTargetValue}>
              {displayTarget != null ? `${displayTarget}°` : "--°"}
            </span>
            <button
              onClick={() => adjust(0.5)}
              disabled={isOff || adjusting}
              aria-label="Increase target temperature"
              className={s.climateAdjBtn}
            >
              <Plus size={12} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>

      {state?.humidity != null && (
        <div
          style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "8px 12px", marginTop: 12, borderRadius: 10,
            background: "rgba(26,26,62,0.5)",
            border: "1px solid rgba(30,30,64,0.5)",
          }}
        >
          <Droplets size={12} style={{ color: "#60A5FA", flexShrink: 0 }} aria-hidden="true" />
          <span style={{ fontSize: 12, color: "#64748B" }}>Humidity</span>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#E2E8F0", marginLeft: "auto" }}>
            {state.humidity}%
          </span>
        </div>
      )}

      {!state && (
        <div
          style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "8px 12px", marginTop: 12, borderRadius: 10,
            background: "rgba(245,158,11,0.06)",
            border: "1px solid rgba(245,158,11,0.18)",
          }}
        >
          <Wind size={12} style={{ color: "#F59E0B", flexShrink: 0 }} aria-hidden="true" />
          <span style={{ fontSize: 12, color: "#64748B" }}>No thermostat connected</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DeviceRow
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
    <div className={s.deviceRow}>
      <span
        className={[s.deviceDot, isOn ? s.deviceDotOn : s.deviceDotOff].join(" ")}
        aria-hidden="true"
      />
      <span className={s.deviceName}>{device.friendly_name}</span>
      {device.domain === "light" && isOn && typeof device.attributes["brightness"] === "number" && (
        <span className={s.deviceBrightness}>
          {Math.round(((device.attributes["brightness"] as number) / 255) * 100)}%
        </span>
      )}
      {isToggleable && (
        <button
          onClick={handleToggle}
          disabled={loading}
          aria-label={`Toggle ${device.friendly_name}`}
          aria-checked={isOn}
          role="switch"
          className={[s.toggleSwitch, isOn ? s.toggleSwitchOn : s.toggleSwitchOff].join(" ")}
          style={loading ? { opacity: 0.5, cursor: "wait" } : undefined}
        >
          <span className={[s.toggleThumb, isOn ? s.toggleThumbOn : s.toggleThumbOff].join(" ")} />
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// RoomExpandableCard
// ---------------------------------------------------------------------------

function RoomExpandableCard({ room, onDeviceToggle }: { room: Room; onDeviceToggle: (device: Device) => Promise<void> }) {
  const [expanded, setExpanded] = useState(false);
  const RoomIcon    = ROOM_ICON_MAP[room.icon] ?? Home;
  const onlineCount = room.devices.filter((d) => d.state === "on").length;
  const totalCount  = room.devices.length;

  return (
    <div className={s.roomCard}>
      <button
        onClick={() => setExpanded((p) => !p)}
        className={s.roomCardHeader}
        aria-expanded={expanded}
      >
        <div className={s.roomIconWrap}>
          <RoomIcon size={16} aria-hidden="true" />
        </div>
        <div className={s.roomInfo}>
          <div className={s.roomName}>{room.name}</div>
          <div className={s.roomDeviceCount}>
            {totalCount === 0 ? "No devices" : `${totalCount} device${totalCount !== 1 ? "s" : ""}`}
          </div>
        </div>
        <div className={s.roomStatus}>
          {onlineCount > 0 ? (
            <span className={s.roomOnlineCount}>
              <span className={[s.deviceDot, s.deviceDotOn].join(" ")} aria-hidden="true" />
              {onlineCount} on
            </span>
          ) : (
            <span style={{ fontSize: 11, color: "#64748B" }}>All off</span>
          )}
          <span className={s.roomChevron}>
            {expanded
              ? <ChevronUp size={14} aria-hidden="true" />
              : <ChevronDown size={14} aria-hidden="true" />
            }
          </span>
        </div>
      </button>

      {expanded && (
        <div className={s.roomDeviceList}>
          {room.devices.length === 0 ? (
            <div className={s.noDevicesNote}>
              <Lightbulb size={14} style={{ color: "#7C3AED", flexShrink: 0 }} aria-hidden="true" />
              Connect HA to see live device states.
            </div>
          ) : (
            <>
              {room.devices.map((device) => (
                <DeviceRow key={device.entity_id} device={device} onToggle={onDeviceToggle} />
              ))}
              {onlineCount > 0 && (
                <button
                  onClick={async () => {
                    for (const device of room.devices.filter((d) => d.state === "on")) {
                      await onDeviceToggle(device);
                    }
                  }}
                  className={s.turnOffAllBtn}
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
// formatRelativeTime helper
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

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

interface SidebarProps {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  residents: ResidentPresence[];
  activeUser: AuraUser;
  isOpen: boolean;
}

function Sidebar({ activeTab, onTabChange, residents, activeUser, isOpen }: SidebarProps) {
  const TABS: { id: Tab; icon: React.ComponentType<LucideProps>; label: string; section: string }[] = [
    { id: "home",    icon: Home,     label: "Dashboard", section: "OVERVIEW" },
    { id: "scenes",  icon: Grid3X3,  label: "Scenes",    section: "CONTROLS" },
    { id: "rooms",   icon: DoorOpen, label: "Rooms",     section: "CONTROLS" },
    { id: "profile", icon: User,     label: "System",    section: "SYSTEM"   },
  ];

  const sections = Array.from(new Set(TABS.map((t) => t.section)));

  return (
    <nav
      className={[s.sidebar, isOpen ? s.sidebarOpen : ""].join(" ")}
      aria-label="Main navigation"
    >
      <div className={s.logo}>
        <span className={s.logoText}>AURA</span>
        <span className={s.logoSub}>by OASIS AI</span>
      </div>

      {sections.map((section) => (
        <div key={section} className={s.navSection}>
          <span className={s.navLabel}>{section}</span>
          {TABS.filter((t) => t.section === section).map((tab) => {
            const isActive = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                aria-label={`Go to ${tab.label}`}
                aria-current={isActive ? "page" : undefined}
                className={[s.navItem, isActive ? s.navItemActive : ""].join(" ")}
              >
                <Icon size={18} strokeWidth={isActive ? 2.5 : 1.75} aria-hidden="true" />
                {tab.label}
              </button>
            );
          })}
        </div>
      ))}

      <div className={s.presenceSection}>
        <span className={s.presenceSectionLabel}>Who&apos;s Home</span>
        {[...residents].sort((a) =>
          a.name.toLowerCase() === activeUser || a.name.toLowerCase() === (activeUser === "conaugh" ? "cc" : activeUser)
            ? -1
            : 1
        ).map((r) => {
          const isCurrentUser =
            r.name.toLowerCase() === activeUser ||
            (activeUser === "conaugh" && r.name.toLowerCase() === "cc");
          return (
            <div key={r.name} className={s.presenceRow}>
              <span
                className={[s.presenceDot, r.home ? s.presenceOnline : s.presenceOffline].join(" ")}
                aria-hidden="true"
              />
              <span className={r.home ? s.presenceNameOnline : undefined}>
                {r.name}
              </span>
              {isCurrentUser && (
                <span
                  style={{
                    marginLeft: "auto",
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    color: "#7C3AED",
                    background: "rgba(124,58,237,0.12)",
                    border: "1px solid rgba(124,58,237,0.25)",
                    borderRadius: 6,
                    padding: "2px 6px",
                  }}
                >
                  You
                </span>
              )}
            </div>
          );
        })}
      </div>
    </nav>
  );
}

// ---------------------------------------------------------------------------
// HomeView
// ---------------------------------------------------------------------------

interface HomeViewProps {
  time: string;
  date: string;
  greeting: string;
  activeUser: AuraUser;
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
  greeting,
  activeUser,
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
  const activeScene = scenes.find((s) => s.active);

  // Stat card data
  const statCards = [
    {
      label: "Active Scene",
      value: activeScene?.name ?? "None",
      sub: activeScene ? "Active" : "No scene active",
      iconBg: "rgba(124,58,237,0.15)",
      iconColor: "#A78BFA",
      icon: <Grid3X3 size={18} aria-hidden="true" />,
    },
    {
      label: "Temperature",
      value: climate?.current_temp != null ? `${climate.current_temp}°` : "--°",
      sub: climate?.mode ? MODE_LABELS[climate.mode] ?? climate.mode : "No thermostat",
      iconBg: "rgba(245,158,11,0.15)",
      iconColor: "#F59E0B",
      icon: <Thermometer size={18} aria-hidden="true" />,
    },
    {
      label: "Gym Streak",
      value: String(habits.find((h) => h.id === "gym")?.streak ?? 0),
      sub: "consecutive days",
      iconBg: "rgba(16,185,129,0.15)",
      iconColor: "#10B981",
      icon: <Flame size={18} aria-hidden="true" />,
    },
    {
      label: "Habits Done",
      value: `${habits.filter((h) => h.completed).length}/${habits.length}`,
      sub: "today",
      iconBg: "rgba(96,165,250,0.15)",
      iconColor: "#60A5FA",
      icon: <Check size={18} aria-hidden="true" />,
    },
    {
      label: "AURA Status",
      value: haConnected ? "Live" : "Offline",
      sub: haConnected ? "HA connected" : "Scaffold mode",
      iconBg: haConnected ? "rgba(16,185,129,0.15)" : "rgba(100,116,139,0.12)",
      iconColor: haConnected ? "#10B981" : "#64748B",
      icon: <Wifi size={18} aria-hidden="true" />,
    },
  ];

  const quickActions = [
    { label: "Control Lights", sub: "Adjust all rooms", iconBg: "rgba(245,158,11,0.15)", iconColor: "#F59E0B", icon: <Zap size={18} aria-hidden="true" /> },
    { label: "Play Music",     sub: "Spotify + Sonos",  iconBg: "rgba(124,58,237,0.15)", iconColor: "#A78BFA", icon: <Music2 size={18} aria-hidden="true" /> },
    { label: "Set Climate",    sub: "Temperature control", iconBg: "rgba(96,165,250,0.15)", iconColor: "#60A5FA", icon: <Thermometer size={18} aria-hidden="true" /> },
    { label: "Lock Down",      sub: "Secure all locks",  iconBg: "rgba(16,185,129,0.15)", iconColor: "#10B981", icon: <Server size={18} aria-hidden="true" /> },
  ];

  return (
    <div>
      {/* Header */}
      <div className={s.header}>
        <div className={s.headerLeft}>
          <div className={s.greeting}>
            {greeting},{" "}
            <span className={s.greetingName}>
              {activeUser === "adon" ? "Adon" : "Conaugh"}
            </span>
          </div>
          <div className={s.headerDate}>{date}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            {[...residents].sort((a) =>
              a.name.toLowerCase() === activeUser ||
              (activeUser === "conaugh" && a.name.toLowerCase() === "cc")
                ? -1
                : 1
            ).map((r) => {
              const isCurrentUser =
                r.name.toLowerCase() === activeUser ||
                (activeUser === "conaugh" && r.name.toLowerCase() === "cc");
              return (
                <div
                  key={r.name}
                  className={[s.presencePill, r.home ? s.presencePillHome : s.presencePillAway].join(" ")}
                  style={
                    isCurrentUser
                      ? {
                          border: "1px solid rgba(124,58,237,0.45)",
                          background: "rgba(124,58,237,0.12)",
                          color: "#A78BFA",
                        }
                      : undefined
                  }
                >
                  <span
                    className={[s.presenceDot, r.home ? s.presenceOnline : s.presenceOffline].join(" ")}
                    aria-hidden="true"
                  />
                  {r.name}
                  {isCurrentUser && (
                    <span
                      style={{
                        marginLeft: 2,
                        fontSize: 9,
                        fontWeight: 700,
                        opacity: 0.7,
                      }}
                    >
                      (you)
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        <div className={s.headerRight}>
          <div className={s.clockDisplay} aria-label={`Current time: ${time}`}>{time}</div>
          <div className={[s.statusBadge, haConnected ? "" : s.statusBadgeOffline].join(" ")}>
            <span className={s.statusDot} aria-hidden="true" />
            {haConnected ? "Connected" : "Scaffold mode"}
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className={s.statsGrid} role="list" aria-label="System stats">
        {statCards.map((card) => (
          <div key={card.label} className={s.statCard} role="listitem">
            <div className={s.statIcon} style={{ background: card.iconBg, color: card.iconColor }}>
              {card.icon}
            </div>
            <div className={s.statLabel}>{card.label}</div>
            <div className={s.statValue}>{card.value}</div>
            <div className={s.statSub}>{card.sub}</div>
          </div>
        ))}
      </div>

      {/* Quick Scenes */}
      <div className={s.sectionTitle}>
        <span className={s.sectionTitleBar} aria-hidden="true" />
        Quick Scenes
      </div>
      <div className={s.scenesGrid} role="list" aria-label="Quick scene selection">
        {scenes.map((scene) => (
          <div key={scene.id} role="listitem">
            <SceneCard scene={scene} onPress={onScenePress} />
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div className={s.sectionTitle}>
        <span className={s.sectionTitleBar} aria-hidden="true" />
        Quick Actions
      </div>
      <div className={s.quickActions} role="list" aria-label="Quick actions">
        {quickActions.map((action) => (
          <button key={action.label} className={s.quickAction} role="listitem" aria-label={action.label}>
            <div className={s.quickActionIcon} style={{ background: action.iconBg, color: action.iconColor }}>
              {action.icon}
            </div>
            <div className={s.quickActionText}>
              <div className={s.quickActionTitle}>{action.label}</div>
              <div className={s.quickActionSub}>{action.sub}</div>
            </div>
            <ChevronRight size={16} className={s.quickActionArrow} aria-hidden="true" />
          </button>
        ))}
      </div>

      {/* Now Playing + Habits side by side */}
      <div className={s.sectionTitle}>
        <span className={s.sectionTitleBar} aria-hidden="true" />
        Live Status
      </div>
      <div className={s.infoGrid}>
        <NowPlayingCard state={nowPlaying} onAction={onMediaAction} />
        <HabitsCard habits={habits} onToggle={onHabitToggle} />
      </div>

      {/* Climate */}
      <div className={s.sectionTitle}>
        <span className={s.sectionTitleBar} aria-hidden="true" />
        Climate
      </div>
      <ClimateCard state={climate} onSetTemperature={onSetTemperature} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// ScenesView
// ---------------------------------------------------------------------------

function ScenesView({ scenes, onScenePress }: { scenes: Scene[]; onScenePress: (scene: Scene) => Promise<void> }) {
  return (
    <div>
      <div className={s.sectionTitle}>
        <span className={s.sectionTitleBar} aria-hidden="true" />
        All Scenes
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
          gap: 14,
        }}
        role="list"
        aria-label="All scenes"
      >
        {scenes.map((scene) => {
          const Icon = SCENE_ICON_MAP[scene.icon] ?? Zap;
          return (
            <div key={scene.id} role="listitem">
              <button
                onClick={async () => { await onScenePress(scene); }}
                aria-label={`Activate ${scene.name} scene`}
                aria-pressed={scene.active}
                className={[s.sceneCard, scene.active ? s.sceneCardActive : ""].join(" ")}
                style={{ padding: "20px 16px", gap: 12 }}
              >
                {scene.active && <span className={s.sceneActiveDot} aria-hidden="true" />}
                <span className={s.sceneIconWrap} style={{ width: 52, height: 52, borderRadius: 14 }}>
                  <Icon size={24} strokeWidth={scene.active ? 2.5 : 1.75} aria-hidden="true" />
                </span>
                <span className={s.sceneName} style={{ fontSize: 13 }}>{scene.name}</span>
                <span className={s.sceneDesc}>{scene.description}</span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// RoomsView
// ---------------------------------------------------------------------------

function RoomsView({ rooms, onDeviceToggle }: { rooms: Room[]; onDeviceToggle: (device: Device) => Promise<void> }) {
  return (
    <div>
      <div className={s.sectionTitle}>
        <span className={s.sectionTitleBar} aria-hidden="true" />
        Rooms
      </div>
      {rooms.length === 0 ? (
        <div className={s.emptyState}>
          <DoorOpen size={48} style={{ color: "#1E1E40" }} aria-hidden="true" />
          <div className={s.emptyStateTitle}>No rooms configured</div>
          <div className={s.emptyStateSub}>Connect Home Assistant to see your rooms</div>
        </div>
      ) : (
        <div className={s.roomsGrid}>
          {rooms.map((room) => (
            <RoomExpandableCard key={room.name} room={room} onDeviceToggle={onDeviceToggle} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ProfileView
// ---------------------------------------------------------------------------

function ProfileView({ residents, status }: { residents: ResidentPresence[]; status: AuraStatus }) {
  const runningServices = status.services.filter((svc) => svc.running).length;
  const totalServices   = status.services.length;

  return (
    <div>
      {/* Wordmark */}
      <div className={s.wordmark}>
        <span className={s.wordmarkText}>AURA</span>
        <span className={s.wordmarkSub}>by OASIS AI Solutions</span>
      </div>

      {/* Who's home */}
      <div className={s.profileSection}>
        <div className={s.sectionTitle}>
          <span className={s.sectionTitleBar} aria-hidden="true" />
          Who&apos;s Home
        </div>
        <div className={s.systemCard}>
          {residents.map((r, idx) => (
            <div key={r.name}>
              <div className={s.systemRow}>
                <div
                  className={s.systemRowIcon}
                  style={r.home ? { background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.25)", color: "#10B981" } : undefined}
                >
                  <span style={{ fontSize: 13, fontWeight: 700 }}>{r.name.slice(0, 2).toUpperCase()}</span>
                </div>
                <div>
                  <div className={s.systemRowLabel}>{r.name}</div>
                  <div className={s.systemRowSub}>
                    {r.home ? "At home" : r.last_seen ? `Last seen ${formatRelativeTime(r.last_seen)}` : "Away"}
                  </div>
                </div>
                <span
                  className={[s.presenceDot, r.home ? s.presenceOnline : s.presenceOffline].join(" ")}
                  style={{ marginLeft: "auto" }}
                  aria-hidden="true"
                />
              </div>
              {idx < residents.length - 1 && <div className={s.systemDivider} aria-hidden="true" />}
            </div>
          ))}
        </div>
      </div>

      {/* System status */}
      <div className={s.profileSection}>
        <div className={s.sectionTitle}>
          <span className={s.sectionTitleBar} aria-hidden="true" />
          System Status
        </div>
        <div className={s.systemCard}>
          {/* Pi */}
          <div className={s.systemRow}>
            <div className={s.systemRowIcon}>
              <Server size={15} aria-hidden="true" />
            </div>
            <div>
              <div className={s.systemRowLabel}>Raspberry Pi</div>
              <div className={s.systemRowSub}>{status.uptime ? `Uptime: ${status.uptime}` : "No uptime data"}</div>
            </div>
            <span className={[s.systemRowValue, status.pi_online ? s.systemRowValueOnline : s.systemRowValueOffline].join(" ")}>
              {status.pi_online ? "Online" : "Offline"}
            </span>
          </div>

          <div className={s.systemDivider} aria-hidden="true" />

          {/* Services */}
          <div className={s.systemRow}>
            <div className={s.systemRowIcon}>
              <Activity size={15} aria-hidden="true" />
            </div>
            <div>
              <div className={s.systemRowLabel}>Services</div>
              <div className={s.systemRowSub}>
                {totalServices === 0 ? "None configured" : `${runningServices} of ${totalServices} running`}
              </div>
            </div>
          </div>

          {status.services.length > 0 && (
            <div className={s.servicesTable}>
              {status.services.map((svc, idx) => (
                <div key={svc.name} className={s.serviceTableRow} style={idx === 0 ? undefined : undefined}>
                  <div className={s.serviceTableName}>
                    <span
                      className={[s.presenceDot, svc.running ? s.presenceOnline : s.presenceOffline].join(" ")}
                      aria-hidden="true"
                    />
                    {svc.name}
                  </div>
                  <span
                    className={[s.servicePill, svc.running ? s.servicePillRunning : s.servicePillStopped].join(" ")}
                  >
                    {svc.running ? "running" : `stopped`}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className={s.systemDivider} style={{ marginTop: 12 }} aria-hidden="true" />

          {/* Last command */}
          <div className={s.systemRow} style={{ alignItems: "flex-start" }}>
            <div className={s.systemRowIcon}>
              <Terminal size={15} style={{ color: "#7C3AED" }} aria-hidden="true" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className={s.systemRowSub} style={{ marginBottom: 2 }}>Last command</div>
              <div className={s.systemRowLabel} style={{ fontSize: 12, wordBreak: "break-all" }}>
                {status.last_command ?? "None yet"}
              </div>
            </div>
            {status.last_command_time && (
              <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                <Clock3 size={10} style={{ color: "#64748B" }} aria-hidden="true" />
                <span style={{ fontSize: 11, color: "#64748B" }}>{formatRelativeTime(status.last_command_time)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={s.versionText}>AURA v0.1.0 &middot; OASIS AI Solutions</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function DashboardPage() {
  const { time, date, greeting } = useCurrentTime();

  const [activeUser]                = useState<AuraUser>(readAuraUserCookie);
  const [activeTab, setActiveTab]   = useState<Tab>("home");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [scenes, setScenes]         = useState<Scene[]>(PLACEHOLDER_SCENES);
  const [rooms]                     = useState<Room[]>(PLACEHOLDER_ROOMS);
  const [habits, setHabits]         = useState<HabitEntry[]>(DEFAULT_HABITS);
  const [residents]                 = useState<ResidentPresence[]>(PLACEHOLDER_RESIDENTS);
  const [auraStatus]                = useState<AuraStatus>(PLACEHOLDER_STATUS);
  const [haConnected]               = useState(false);

  const nowPlaying: NowPlayingState | null = null;
  const climateState: ClimateState | null  = null;

  // Close sidebar on tab change (mobile)
  const handleTabChange = useCallback((tab: Tab) => {
    setActiveTab(tab);
    setSidebarOpen(false);
  }, []);

  // Scene activation
  const handleScenePress = useCallback(async (pressedScene: Scene) => {
    setScenes((prev) => prev.map((sc) => ({ ...sc, active: sc.id === pressedScene.id })));
    const res = await fetch("/api/scene", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ webhook_id: pressedScene.webhook_id }),
    });
    if (!res.ok) {
      setScenes((prev) => prev.map((sc) => ({ ...sc, active: false })));
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

  const BOTTOM_TABS: { id: Tab; icon: React.ComponentType<LucideProps>; label: string }[] = [
    { id: "home",    icon: Home,     label: "Home"   },
    { id: "scenes",  icon: Grid3X3,  label: "Scenes" },
    { id: "rooms",   icon: DoorOpen, label: "Rooms"  },
    { id: "profile", icon: User,     label: "System" },
  ];

  return (
    <div className={s.container}>
      {/* Mobile hamburger */}
      <button
        className={s.hamburger}
        onClick={() => setSidebarOpen((p) => !p)}
        aria-label={sidebarOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={sidebarOpen}
      >
        {sidebarOpen ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
      </button>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className={s.overlayVisible}
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={handleTabChange}
        residents={residents}
        activeUser={activeUser}
        isOpen={sidebarOpen}
      />

      {/* Main content */}
      <main className={s.main}>
        {activeTab === "home" && (
          <HomeView
            time={time}
            date={date}
            greeting={greeting}
            activeUser={activeUser}
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
      </main>

      {/* Mobile bottom nav */}
      <nav className={s.bottomNav} aria-label="Mobile navigation">
        <div className={s.bottomNavInner}>
          {BOTTOM_TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabChange(tab.id)}
                aria-label={`Go to ${tab.label}`}
                aria-current={isActive ? "page" : undefined}
                className={[s.bottomNavBtn, isActive ? s.bottomNavBtnActive : ""].join(" ")}
              >
                <Icon size={20} strokeWidth={isActive ? 2.5 : 1.5} aria-hidden="true" />
                <span style={{ fontSize: 10, fontWeight: 600 }}>{tab.label}</span>
                {isActive && <span className={s.bottomNavDot} aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
