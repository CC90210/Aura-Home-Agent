"use client";

import { Server, Terminal, Clock3, Activity } from "lucide-react";
import type { AuraStatus } from "@/lib/types";

interface StatusBarProps {
  status: AuraStatus | null;
}

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "never";
  const diff    = Date.now() - new Date(isoString).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

// Consistent inner-tile style used in the status grid
const tileCls =
  "flex items-center gap-2.5 rounded-xl px-3 py-2.5 border border-aura-border/40";
const tileStyle = { background: "rgba(18,18,42,0.60)" };

export function StatusBar({ status }: StatusBarProps) {
  const runningServices = status?.services.filter((s) => s.running).length ?? 0;
  const totalServices   = status?.services.length ?? 0;

  return (
    <div
      className="glass-card rounded-2xl p-4 flex flex-col gap-3"
      style={{ animation: "slide-up 0.4s ease-out both" }}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <Activity size={15} className="text-aura-purple" aria-hidden="true" />
        <h2 className="text-xs font-semibold text-aura-text-muted uppercase tracking-wider">
          AURA Status
        </h2>
      </div>

      {/* Pi + Services grid */}
      <div className="grid grid-cols-2 gap-2">
        {/* Pi */}
        <div className={tileCls} style={tileStyle}>
          <span
            className={[
              "w-2 h-2 rounded-full shrink-0",
              status == null
                ? "status-unknown"
                : status.pi_online
                ? "status-online animate-pulse"
                : "status-offline",
            ].join(" ")}
            aria-hidden="true"
          />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <Server size={11} className="text-aura-text-muted shrink-0" aria-hidden="true" />
              <span className="text-xs text-aura-text-muted">Pi</span>
            </div>
            <p
              className={[
                "text-xs font-semibold",
                status == null
                  ? "text-aura-amber"
                  : status.pi_online
                  ? "text-aura-green"
                  : "text-aura-red",
              ].join(" ")}
            >
              {status == null ? "Unknown" : status.pi_online ? "Online" : "Offline"}
            </p>
          </div>
        </div>

        {/* Services */}
        <div className={tileCls} style={tileStyle}>
          <span
            className={[
              "w-2 h-2 rounded-full shrink-0",
              runningServices === totalServices && totalServices > 0
                ? "status-online"
                : totalServices === 0
                ? "status-unknown"
                : "status-offline",
            ].join(" ")}
            aria-hidden="true"
          />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <Activity size={11} className="text-aura-text-muted shrink-0" aria-hidden="true" />
              <span className="text-xs text-aura-text-muted">Services</span>
            </div>
            <p className="text-xs font-semibold text-aura-text tabular-nums">
              {totalServices === 0 ? "—" : `${runningServices}/${totalServices}`}
            </p>
          </div>
        </div>
      </div>

      {/* Service detail rows */}
      {status && status.services.length > 0 && (
        <div className="flex flex-col gap-1">
          {status.services.map((svc) => (
            <div key={svc.name} className="flex items-center justify-between px-2 py-1">
              <div className="flex items-center gap-2">
                <span
                  className={[
                    "w-1.5 h-1.5 rounded-full shrink-0",
                    svc.running ? "status-online" : "status-offline",
                  ].join(" ")}
                  aria-hidden="true"
                />
                <span className="text-xs text-aura-text-muted">{svc.name}</span>
              </div>
              <span className="text-xs text-aura-text-muted/60">
                {svc.running
                  ? "running"
                  : `stopped · ${formatRelativeTime(svc.last_seen)}`}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Last voice command */}
      <div className={`${tileCls} items-start`} style={tileStyle}>
        <Terminal size={12} className="text-aura-purple shrink-0 mt-0.5" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-xs text-aura-text-muted mb-0.5">Last command</p>
          <p className="text-xs text-aura-text truncate">
            {status?.last_command ?? "None yet"}
          </p>
        </div>
        {status?.last_command_time && (
          <div className="flex items-center gap-1 shrink-0">
            <Clock3 size={10} className="text-aura-text-muted" aria-hidden="true" />
            <span className="text-xs text-aura-text-muted">
              {formatRelativeTime(status.last_command_time)}
            </span>
          </div>
        )}
      </div>

      {/* Uptime */}
      {status?.uptime && (
        <p className="text-xs text-aura-text-muted text-center">
          Uptime:{" "}
          <span className="text-aura-text font-medium">{status.uptime}</span>
        </p>
      )}
    </div>
  );
}
