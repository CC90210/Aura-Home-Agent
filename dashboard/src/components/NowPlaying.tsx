"use client";

import { useState } from "react";
import Image from "next/image";
import {
  Play,
  Pause,
  SkipForward,
  SkipBack,
  Volume2,
  VolumeX,
  Shuffle,
  Repeat,
  Music2,
} from "lucide-react";
import type { NowPlayingState } from "@/lib/types";

interface NowPlayingProps {
  state: NowPlayingState | null;
  /** Called when the user presses a media control button.
   *  The action maps directly to HA media_player service names. */
  onAction: (
    action:
      | "media_play_pause"
      | "media_next_track"
      | "media_previous_track"
      | "volume_mute",
    entityId: string
  ) => Promise<void>;
}

export function NowPlaying({ state, onAction }: NowPlayingProps) {
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const handleAction = async (
    action:
      | "media_play_pause"
      | "media_next_track"
      | "media_previous_track"
      | "volume_mute"
  ) => {
    if (!state || actionLoading) return;
    setActionLoading(action);
    try {
      await onAction(action, state.entity_id);
    } finally {
      setActionLoading(null);
    }
  };

  const isPlaying = state?.state === "playing";
  const isUnavailable = !state || state.state === "unavailable" || state.state === "off";

  return (
    <div className="glass-card rounded-2xl p-4 flex flex-col gap-4 animate-[slide-up_0.4s_ease-out]">
      {/* Section label */}
      <div className="flex items-center gap-2">
        <Music2 size={16} className="text-aura-purple" aria-hidden="true" />
        <h2 className="text-sm font-semibold text-aura-text-muted uppercase tracking-wider">
          Now Playing
        </h2>
        {isPlaying && (
          <span className="ml-auto flex gap-0.5 items-end h-4" aria-hidden="true">
            {[3, 5, 4, 6, 3].map((h, i) => (
              <span
                key={i}
                className="w-0.5 bg-aura-purple rounded-full animate-pulse"
                style={{
                  height: h * 2,
                  animationDelay: `${i * 0.15}s`,
                  animationDuration: "0.8s",
                }}
              />
            ))}
          </span>
        )}
      </div>

      {isUnavailable ? (
        /* Placeholder state — HA not connected or speaker off */
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-xl bg-aura-card-hover border border-aura-border flex items-center justify-center shrink-0">
            <Music2 size={24} className="text-aura-border" aria-hidden="true" />
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <p className="text-aura-text-muted text-sm">Nothing playing</p>
            <p className="text-aura-text-muted/60 text-xs">
              Speaker offline or idle
            </p>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-4">
          {/* Album art */}
          <div className="relative w-16 h-16 rounded-xl overflow-hidden shrink-0 border border-aura-border shadow-aura-purple-sm">
            {state.album_art_url ? (
              <Image
                src={state.album_art_url}
                alt={`Album art for ${state.album ?? "current track"}`}
                fill
                className="object-cover"
                sizes="64px"
              />
            ) : (
              <div className="w-full h-full bg-gradient-to-br from-aura-purple-dim to-aura-card flex items-center justify-center">
                <Music2 size={24} className="text-aura-purple-light" aria-hidden="true" />
              </div>
            )}
          </div>

          {/* Track info */}
          <div className="flex flex-col gap-0.5 min-w-0 flex-1">
            <p className="text-aura-text font-semibold text-sm leading-tight truncate">
              {state.title ?? "Unknown Track"}
            </p>
            <p className="text-aura-text-muted text-xs truncate">
              {state.artist ?? "Unknown Artist"}
            </p>
            {state.album && (
              <p className="text-aura-text-muted/60 text-xs truncate">
                {state.album}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center justify-between">
        {/* Shuffle */}
        <button
          onClick={() => {/* Shuffle toggle — Phase 2 */}}
          disabled={isUnavailable}
          aria-label="Toggle shuffle"
          className={[
            "p-2 rounded-lg transition-colors",
            isUnavailable
              ? "text-aura-border cursor-not-allowed"
              : state?.shuffle
              ? "text-aura-purple hover:bg-aura-purple/10"
              : "text-aura-text-muted hover:text-aura-text hover:bg-white/5",
          ].join(" ")}
        >
          <Shuffle size={16} aria-hidden="true" />
        </button>

        {/* Previous */}
        <button
          onClick={() => handleAction("media_previous_track")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Previous track"
          className={[
            "p-2 rounded-lg transition-all",
            isUnavailable || actionLoading
              ? "text-aura-border cursor-not-allowed"
              : "text-aura-text-muted hover:text-aura-text hover:bg-white/5 active:scale-90",
          ].join(" ")}
        >
          <SkipBack size={20} aria-hidden="true" />
        </button>

        {/* Play / Pause */}
        <button
          onClick={() => handleAction("media_play_pause")}
          disabled={isUnavailable || !!actionLoading}
          aria-label={isPlaying ? "Pause" : "Play"}
          className={[
            "w-12 h-12 rounded-full flex items-center justify-center transition-all",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
            isUnavailable || actionLoading
              ? "bg-aura-border cursor-not-allowed text-aura-text-muted"
              : "bg-aura-purple hover:bg-aura-purple-light active:scale-90 text-white shadow-aura-purple-sm",
          ].join(" ")}
        >
          {actionLoading === "media_play_pause" ? (
            <span className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
          ) : isPlaying ? (
            <Pause size={20} fill="currentColor" aria-hidden="true" />
          ) : (
            <Play size={20} fill="currentColor" className="ml-0.5" aria-hidden="true" />
          )}
        </button>

        {/* Next */}
        <button
          onClick={() => handleAction("media_next_track")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Next track"
          className={[
            "p-2 rounded-lg transition-all",
            isUnavailable || actionLoading
              ? "text-aura-border cursor-not-allowed"
              : "text-aura-text-muted hover:text-aura-text hover:bg-white/5 active:scale-90",
          ].join(" ")}
        >
          <SkipForward size={20} aria-hidden="true" />
        </button>

        {/* Mute */}
        <button
          onClick={() => handleAction("volume_mute")}
          disabled={isUnavailable || !!actionLoading}
          aria-label="Toggle mute"
          className={[
            "p-2 rounded-lg transition-colors",
            isUnavailable || actionLoading
              ? "text-aura-border cursor-not-allowed"
              : "text-aura-text-muted hover:text-aura-text hover:bg-white/5",
          ].join(" ")}
        >
          {state?.volume === 0 ? (
            <VolumeX size={16} aria-hidden="true" />
          ) : (
            <Volume2 size={16} aria-hidden="true" />
          )}
        </button>
      </div>
    </div>
  );
}
