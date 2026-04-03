"use client";

import { useState, useCallback } from "react";
import {
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
  type LucideProps,
} from "lucide-react";
import type { Scene } from "@/lib/types";

// Explicit map of string names → Lucide components (avoids dynamic imports and `any`).
const ICON_MAP: Record<string, React.ComponentType<LucideProps>> = {
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
};

interface SceneButtonProps {
  scene: Scene;
  onPress: (scene: Scene) => Promise<void>;
}

export function SceneButton({ scene, onPress }: SceneButtonProps) {
  const [loading, setLoading]   = useState(false);
  const [rippling, setRippling] = useState(false);
  const [error, setError]       = useState(false);

  const Icon = ICON_MAP[scene.icon] ?? Zap;

  const handlePress = useCallback(async () => {
    if (loading) return;

    setRippling(true);
    setTimeout(() => setRippling(false), 600);

    setLoading(true);
    setError(false);

    try {
      await onPress(scene);
    } catch {
      setError(true);
      setTimeout(() => setError(false), 3000);
    } finally {
      setLoading(false);
    }
  }, [loading, onPress, scene]);

  const isActive = scene.active && !error;
  const isError  = error;

  return (
    <button
      onClick={handlePress}
      disabled={loading}
      aria-label={`Activate ${scene.name} scene`}
      aria-pressed={isActive}
      title={scene.description}
      className={[
        // Layout
        "relative flex flex-col items-center justify-center gap-2",
        "rounded-2xl p-4 min-h-[100px] w-full",
        "overflow-hidden",
        // Interaction feel
        "transition-all duration-200 ease-out",
        "select-none touch-none",
        loading ? "opacity-70 cursor-wait" : "cursor-pointer active:scale-95",
        // Focus ring
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
        // State-driven appearance
        isError
          ? "border border-aura-red/40"
          : isActive
          ? "scene-active border"
          : "glass-card hover:border-aura-purple/30",
      ]
        .filter(Boolean)
        .join(" ")}
      style={
        isError
          ? {
              background: "rgba(239,68,68,0.10)",
              boxShadow: "0 0 15px rgba(239,68,68,0.22)",
            }
          : undefined
      }
    >
      {/* Ripple layer */}
      {rippling && (
        <span
          aria-hidden="true"
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <span
            className="block rounded-full bg-white/10"
            style={{
              width: 200,
              height: 200,
              marginTop: -100,
              marginLeft: -100,
              animation: "ripple 0.6s linear",
            }}
          />
        </span>
      )}

      {/* Active gradient overlay */}
      {isActive && (
        <span
          aria-hidden="true"
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "linear-gradient(135deg, rgba(124,58,237,0.22) 0%, rgba(59,130,246,0.12) 100%)",
          }}
        />
      )}

      {/* Icon container */}
      <span
        className={[
          "relative z-10 rounded-xl p-2 transition-colors",
          isError
            ? "text-aura-red bg-aura-red/15"
            : isActive
            ? "text-aura-purple-light bg-aura-purple/20"
            : "text-aura-text-muted bg-white/5",
        ].join(" ")}
      >
        <Icon
          size={22}
          strokeWidth={isActive ? 2.5 : 1.75}
          aria-hidden="true"
        />
      </span>

      {/* Label */}
      <span
        className={[
          "relative z-10 text-xs font-semibold leading-tight text-center",
          isError
            ? "text-aura-red"
            : isActive
            ? "text-aura-text"
            : "text-aura-text-muted",
        ].join(" ")}
      >
        {loading ? (
          <span className="flex items-center gap-1">
            <span
              className="w-3 h-3 rounded-full border border-aura-text-muted/40 border-t-aura-text-muted"
              style={{ animation: "spin 0.8s linear infinite" }}
            />
          </span>
        ) : (
          scene.name
        )}
      </span>

      {/* Active dot */}
      {isActive && (
        <span
          aria-hidden="true"
          className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full status-online animate-pulse"
        />
      )}
    </button>
  );
}
