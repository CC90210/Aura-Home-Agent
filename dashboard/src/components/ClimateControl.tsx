"use client";

import { useState } from "react";
import { Thermometer, Droplets, Wind, Minus, Plus } from "lucide-react";
import type { ClimateState } from "@/lib/types";

interface ClimateControlProps {
  state: ClimateState | null;
  /** Called when the user adjusts the target temperature.
   *  newTemp is in Celsius. Maps to HA climate.set_temperature service. */
  onSetTemperature: (entityId: string, newTemp: number) => Promise<void>;
}

const MODE_LABELS: Record<string, string> = {
  heat: "Heating",
  cool: "Cooling",
  heat_cool: "Auto",
  auto: "Auto",
  dry: "Dry",
  fan_only: "Fan",
  off: "Off",
};

const MODE_COLORS: Record<string, string> = {
  heat: "text-aura-amber",
  cool: "text-aura-blue-light",
  heat_cool: "text-aura-purple-light",
  auto: "text-aura-purple-light",
  dry: "text-aura-blue",
  fan_only: "text-aura-text-muted",
  off: "text-aura-border",
};

const MIN_TEMP = 16;
const MAX_TEMP = 28;

export function ClimateControl({ state, onSetTemperature }: ClimateControlProps) {
  const [pendingTemp, setPendingTemp] = useState<number | null>(null);
  const [adjusting, setAdjusting] = useState(false);

  const displayTarget = pendingTemp ?? state?.target_temp ?? null;
  const isOff = !state || state.mode === "off";
  const modeColor = state ? (MODE_COLORS[state.mode] ?? "text-aura-text-muted") : "text-aura-border";

  const adjust = async (delta: number) => {
    if (!state || adjusting || isOff) return;

    const currentTarget = displayTarget ?? 20;
    const newTemp = Math.min(MAX_TEMP, Math.max(MIN_TEMP, currentTarget + delta));
    if (newTemp === currentTarget) return;

    setPendingTemp(newTemp);
    setAdjusting(true);

    try {
      await onSetTemperature(state.entity_id, newTemp);
      // Keep pending until server reflects the change
    } catch {
      // Revert optimistic update on error
      setPendingTemp(null);
    } finally {
      setAdjusting(false);
    }
  };

  return (
    <div className="glass-card rounded-2xl p-4 flex flex-col gap-4 animate-[slide-up_0.4s_ease-out]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Thermometer size={16} className="text-aura-amber" aria-hidden="true" />
          <h2 className="text-sm font-semibold text-aura-text-muted uppercase tracking-wider">
            Climate
          </h2>
        </div>
        {state && (
          <span className={`text-xs font-medium ${modeColor}`}>
            {MODE_LABELS[state.mode] ?? state.mode}
          </span>
        )}
      </div>

      {/* Temperature display */}
      <div className="flex items-center justify-between gap-4">
        {/* Current temperature */}
        <div className="flex flex-col items-center gap-1">
          <span className="text-xs text-aura-text-muted">Current</span>
          <span className="text-4xl font-bold text-aura-text tabular-nums">
            {state?.current_temp != null
              ? `${state.current_temp}°`
              : "--°"}
          </span>
          <span className="text-xs text-aura-text-muted">Celsius</span>
        </div>

        {/* Divider */}
        <div className="h-16 w-px bg-aura-border" aria-hidden="true" />

        {/* Target temperature control */}
        <div className="flex flex-col items-center gap-2">
          <span className="text-xs text-aura-text-muted">Target</span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => adjust(-0.5)}
              disabled={isOff || adjusting || (displayTarget ?? 20) <= MIN_TEMP}
              aria-label="Decrease target temperature"
              className={[
                "w-8 h-8 rounded-full flex items-center justify-center",
                "border border-aura-border transition-all",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
                isOff || adjusting
                  ? "opacity-30 cursor-not-allowed"
                  : "hover:border-aura-blue hover:text-aura-blue active:scale-90 cursor-pointer",
              ].join(" ")}
            >
              <Minus size={14} aria-hidden="true" />
            </button>

            <span className="text-3xl font-bold text-aura-purple-light tabular-nums w-16 text-center">
              {displayTarget != null ? `${displayTarget}°` : "--°"}
            </span>

            <button
              onClick={() => adjust(0.5)}
              disabled={isOff || adjusting || (displayTarget ?? 20) >= MAX_TEMP}
              aria-label="Increase target temperature"
              className={[
                "w-8 h-8 rounded-full flex items-center justify-center",
                "border border-aura-border transition-all",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aura-purple",
                isOff || adjusting
                  ? "opacity-30 cursor-not-allowed"
                  : "hover:border-aura-amber hover:text-aura-amber active:scale-90 cursor-pointer",
              ].join(" ")}
            >
              <Plus size={14} aria-hidden="true" />
            </button>
          </div>
          <span className="text-xs text-aura-text-muted">Celsius</span>
        </div>
      </div>

      {/* Humidity + fan speed row (if available) */}
      {state?.humidity != null && (
        <div className="flex items-center gap-2 rounded-xl bg-aura-card-hover/60 px-3 py-2">
          <Droplets size={14} className="text-aura-blue shrink-0" aria-hidden="true" />
          <span className="text-xs text-aura-text-muted">Humidity</span>
          <span className="text-xs font-semibold text-aura-text ml-auto">
            {state.humidity}%
          </span>
        </div>
      )}

      {/* Offline placeholder */}
      {!state && (
        <div className="flex items-center gap-2 rounded-xl bg-aura-amber/10 border border-aura-amber/20 px-3 py-2">
          <Wind size={14} className="text-aura-amber shrink-0" aria-hidden="true" />
          <p className="text-xs text-aura-text-muted">
            No thermostat connected. Configure a climate entity in HA.
          </p>
        </div>
      )}
    </div>
  );
}
