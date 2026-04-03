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
  Music2,
} from "lucide-react";
import type { NowPlayingState } from "@/lib/types";

interface NowPlayingProps {
  state: NowPlayingState | null;
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

  const isPlaying     = state?.state === "playing";
  const isUnavailable = !state || state.state === "unavailable" || state.state === "off";

  return (
    <div
      className="glass-card rounded-2xl p-4 flex flex-col gap-4"
      style={{ animation: "slide-up 0.4s ease-out both" }}
    >
      {/* Section header */}
      <div className="flex items-center gap-2">
        <Music2 size={15} className="text-aura-purple" aria-hidden="true" />
        <h2 className="text-xs font-semibold text-aura-text-muted uppercase tracking-wider">
          Now Playing
        </h2>
        {/* Animated equalizer bars when music is playing */}
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

      {/* Track info area */}
      {isUnavailable ? (
        <div className="flex items-center gap-4">
          <div
            className="w-16 h-16 rounded-xl flex items-center justify-center shrink-0 border border-aura-border"
            style={{ background: "rgba(26,26,62,0.60)" }}
          >
            <Music2 size={24} className="text-aura-border" aria-hidden="true" />
          </div>
          <div className="flex flex-col gap-1 min-w-0">
            <p className="text-aura-text-muted text-sm font-medium">Nothing playing</p>
            <p className="text-aura-text-muted/60 text-xs">Speaker offline or idle</p>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-4">
          {/* Album art */}
          <div
            className="relative w-16 h-16 rounded-xl overflow-hidden shrink-0 border border-aura-border"
            style={{ boxShadow: "0 0 12px rgba(124,58,237,0.25)" }}
          >
            {state.album_art_url ? (
              <Image
                src={state.album_art_url}
                alt={`Album art for ${state.album ?? "current track"}`}
                fill
                className="object-cover"
                sizes="64px"
              />
            ) : (
              <div
                className="w-full h-full flex items-center justify-center"
                style={{
                  background: "linear-gradient(135deg, #4C1D95 0%, #12122A 100%)",
                }}
              >
                <Music2 size={24} className="text-aura-purple-light" aria-hidden="true" />
              </div>
            )}
          </div>

          {/* Track text */}
          <div className="flex flex-col gap-0.5 min-w-0 flex-1">
            <p className="text-aura-text font-semibold text-sm leading-tight truncate">
              {state.title ?? "Unknown Track"}
            </p>
            <p className="text-aura-text-muted text-xs truncate">
              {state.artist ?? "Unknown Artist"}
            </p>
            {state.album && (
              <p className="text-aura-text-muted/60 text-xs truncate">{state.album}</p>
            )}
          </div>
        </div>
      )}

      {/* Transport controls */}
      <div className="flex items-center justify-between">
        {/* Shuffle */}
        <button
          onClick={() => { /* Shuffle — Phase 2 */ }}
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
          <Shuffle size={15} aria-hidden="true" />
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
              : "bg-aura-purple hover:bg-aura-purple-light active:scale-90 text-white",
          ].join(" ")}
          style={
            !isUnavailable && !actionLoading
              ? { boxShadow: "0 0 16px rgba(124,58,237,0.40)" }
              : undefined
          }
        >
          {actionLoading === "media_play_pause" ? (
            <span
              className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white"
              style={{ animation: "spin 0.8s linear infinite" }}
            />
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
            <VolumeX size={15} aria-hidden="true" />
          ) : (
            <Volume2 size={15} aria-hidden="true" />
          )}
        </button>
      </div>
    </div>
  );
}
