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

// Map of string icon names to Lucide components.
// Kept explicit — avoids dynamic imports and satisfies no-any rule.
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
  const [loading, setLoading] = useState(false);
  const [rippling, setRippling] = useState(false);
  const [error, setError] = useState(false);

  const Icon = ICON_MAP[scene.icon] ?? Zap;

  const handlePress = useCallback(async () => {
    if (loading) return;

    // Trigger ripple animation
    setRippling(true);
    setTimeout(() => setRippling(false), 600);

    setLoading(true);
    setError(false);

    try {
      await onPress(scene);
    } catch {
      setError(true);
      // Clear error indicator after 3 s so it resets visually
      setTimeout(() => setError(false), 3000);
    } finally {
      setLoading(false);
    }
  }, [loading, onPress, scene]);

  const isActive = scene.active && !error;
  const isError = error;

  return (
    <button
      onClick={handlePress}
      disabled={loading}
      aria-label={`Activate ${scene.name} scene`}
      aria-pressed={isActive}
      title={scene.description}
      className={[
        // Base
        "relative flex flex-col items-center justify-center gap-2",
        "rounded-2xl p-4 min-h-[100px] w-full",
        "overflow-hidden",
        "transition-all duration-200 ease-out",
        "select-none touch-none",
        // Border
        "border",
        // Hover / focus
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
        // States
        isError
          ? "bg-aura-red/10 border-aura-red/40 shadow-[0_0_15px_rgba(239,68,68,0.25)]"
          : isActive
          ? "scene-active"
          : "glass-card border-aura-border hover:border-aura-purple/40 hover:bg-aura-card-hover",
        loading ? "opacity-70 cursor-wait" : "cursor-pointer active:scale-95",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {/* Ripple layer */}
      {rippling && (
        <span
          aria-hidden="true"
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <span
            className="block rounded-full bg-white/10 animate-[ripple_0.6s_linear]"
            style={{ width: 200, height: 200, marginTop: -100, marginLeft: -100 }}
          />
        </span>
      )}

      {/* Active glow background */}
      {isActive && (
        <span
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-br from-aura-purple/20 to-aura-blue/10 pointer-events-none"
        />
      )}

      {/* Icon */}
      <span
        className={[
          "relative z-10 rounded-xl p-2",
          isError
            ? "text-aura-red"
            : isActive
            ? "text-aura-purple-light"
            : "text-aura-text-muted",
          isActive ? "bg-aura-purple/20" : "bg-white/5",
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
        {loading ? "..." : scene.name}
      </span>

      {/* Active indicator dot */}
      {isActive && (
        <span
          aria-hidden="true"
          className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full status-online animate-pulse"
        />
      )}
    </button>
  );
}
