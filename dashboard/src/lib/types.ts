// Home Assistant entity state as returned by the REST API
export interface HAState {
  entity_id: string;
  state: string;
  attributes: Record<string, unknown>;
  last_changed: string;
  last_updated: string;
  context: {
    id: string;
    parent_id: string | null;
    user_id: string | null;
  };
}

// A scene tile on the dashboard — maps to an HA webhook or script
export interface Scene {
  id: string;
  name: string;
  /** Lucide icon component name */
  icon: string;
  /** HA webhook ID to fire when the scene is activated */
  webhook_id: string;
  description: string;
  /** Whether this scene is currently the active one */
  active: boolean;
}

// A room in the apartment with its associated devices
export interface Room {
  name: string;
  icon: string;
  devices: Device[];
  /** Current ambient temperature in Celsius, null if no sensor */
  temperature: number | null;
}

// A single smart device entity
export interface Device {
  entity_id: string;
  /** HA domain: light, switch, media_player, climate, lock, etc. */
  domain: string;
  friendly_name: string;
  state: string;
  attributes: Record<string, unknown>;
}

// A single daily habit entry for the accountability tracker
export interface HabitEntry {
  id: string;
  name: string;
  completed: boolean;
  /** Suggested target time e.g. "07:30" */
  target_time: string;
  /** Current consecutive days streak */
  streak: number;
  /** Icon name from lucide-react */
  icon: string;
}

// Status of a single background service
export interface ServiceStatus {
  name: string;
  running: boolean;
  last_seen: string | null;
}

// Overall AURA system health for the status bar
export interface AuraStatus {
  pi_online: boolean;
  services: ServiceStatus[];
  last_command: string | null;
  last_command_time: string | null;
  /** ISO duration string e.g. "P0DT4H22M" or human string */
  uptime: string | null;
}

// Presence entry — who is currently home
export interface ResidentPresence {
  name: string;
  home: boolean;
  /** HA device_tracker entity ID */
  entity_id: string;
  /** Last seen timestamp */
  last_seen: string | null;
}

// HA WebSocket message envelope
export interface HAWebSocketMessage {
  type: string;
  id?: number;
  event?: {
    event_type: string;
    data: {
      entity_id?: string;
      new_state?: HAState;
      old_state?: HAState;
    };
    time_fired: string;
  };
  result?: unknown;
  error?: {
    code: string;
    message: string;
  };
  success?: boolean;
}

// Payload sent when calling an HA service
export interface HAServiceCallPayload {
  entity_id?: string;
  [key: string]: unknown;
}

// Music / media player state parsed from HA media_player attributes
export interface NowPlayingState {
  entity_id: string;
  state: "playing" | "paused" | "idle" | "off" | "unavailable";
  title: string | null;
  artist: string | null;
  album: string | null;
  album_art_url: string | null;
  volume: number;
  shuffle: boolean;
  repeat: "off" | "one" | "all";
}

// Climate entity state parsed from HA climate attributes
export interface ClimateState {
  entity_id: string;
  current_temp: number | null;
  target_temp: number | null;
  mode: "heat" | "cool" | "heat_cool" | "auto" | "dry" | "fan_only" | "off";
  humidity: number | null;
}
