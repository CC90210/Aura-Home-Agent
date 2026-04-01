"use client";

import { useState } from "react";
import { Lightbulb, Power, Thermometer, ChevronDown, ChevronUp } from "lucide-react";
import type { Room, Device } from "@/lib/types";

interface DeviceRowProps {
  device: Device;
  onToggle: (device: Device) => Promise<void>;
}

function DeviceRow({ device, onToggle }: DeviceRowProps) {
  const [loading, setLoading] = useState(false);
  const isOn = device.state === "on";
  const isToggleable = ["light", "switch", "fan", "input_boolean"].includes(
    device.domain
  );

  const handleToggle = async () => {
    if (!isToggleable || loading) return;
    setLoading(true);
    try {
      await onToggle(device);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-between py-2 border-b border-aura-border/40 last:border-0">
      <div className="flex items-center gap-2.5 min-w-0">
        <span
          className={[
            "shrink-0 w-1.5 h-1.5 rounded-full",
            isOn ? "status-online" : "bg-aura-border",
          ].join(" ")}
          aria-hidden="true"
        />
        <span className="text-sm text-aura-text truncate">
          {device.friendly_name}
        </span>
        {/* Show brightness % if available */}
        {device.domain === "light" &&
          isOn &&
          typeof device.attributes["brightness"] === "number" && (
            <span className="shrink-0 text-xs text-aura-text-muted">
              {Math.round(
                ((device.attributes["brightness"] as number) / 255) * 100
              )}
              %
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
            "transition-colors duration-200 focus-visible:outline-none",
            "focus-visible:ring-2 focus-visible:ring-aura-purple focus-visible:ring-offset-2",
            "focus-visible:ring-offset-aura-card",
            loading ? "opacity-50 cursor-wait" : "cursor-pointer",
            isOn ? "bg-aura-purple" : "bg-aura-border",
          ].join(" ")}
        >
          <span
            className={[
              "inline-block h-3.5 w-3.5 rounded-full bg-white shadow",
              "transition-transform duration-200",
              isOn ? "translate-x-[18px]" : "translate-x-[3px]",
            ].join(" ")}
          />
        </button>
      )}
    </div>
  );
}

interface RoomCardProps {
  room: Room;
  onDeviceToggle: (device: Device) => Promise<void>;
}

export function RoomCard({ room, onDeviceToggle }: RoomCardProps) {
  const [expanded, setExpanded] = useState(false);

  const onlineCount = room.devices.filter((d) => d.state === "on").length;
  const totalCount = room.devices.length;

  // Show up to 3 devices collapsed, all when expanded
  const visibleDevices = expanded ? room.devices : room.devices.slice(0, 3);
  const hasMore = room.devices.length > 3;

  return (
    <div className="glass-card rounded-2xl p-4 flex flex-col gap-3 animate-[slide-up_0.4s_ease-out]">
      {/* Room header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg" aria-hidden="true">
            {room.icon}
          </span>
          <h3 className="font-semibold text-aura-text">{room.name}</h3>
        </div>

        <div className="flex items-center gap-3">
          {/* Temperature badge */}
          {room.temperature !== null && (
            <div className="flex items-center gap-1 text-xs text-aura-text-muted">
              <Thermometer size={12} className="text-aura-blue" aria-hidden="true" />
              <span>{room.temperature}°C</span>
            </div>
          )}

          {/* Active device count */}
          <div className="flex items-center gap-1.5 text-xs">
            {onlineCount > 0 ? (
              <>
                <span className="status-online w-1.5 h-1.5 rounded-full" aria-hidden="true" />
                <span className="text-aura-green font-medium">
                  {onlineCount}/{totalCount}
                </span>
              </>
            ) : (
              <>
                <span className="bg-aura-border w-1.5 h-1.5 rounded-full" aria-hidden="true" />
                <span className="text-aura-text-muted">All off</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Devices list */}
      {room.devices.length === 0 ? (
        <p className="text-xs text-aura-text-muted italic">
          No devices configured for this room yet.
        </p>
      ) : (
        <div className="flex flex-col">
          {visibleDevices.map((device) => (
            <DeviceRow
              key={device.entity_id}
              device={device}
              onToggle={onDeviceToggle}
            />
          ))}

          {hasMore && (
            <button
              onClick={() => setExpanded((prev) => !prev)}
              className="mt-2 flex items-center gap-1 text-xs text-aura-text-muted hover:text-aura-purple-light transition-colors self-start"
              aria-expanded={expanded}
            >
              {expanded ? (
                <>
                  <ChevronUp size={14} aria-hidden="true" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown size={14} aria-hidden="true" />
                  {room.devices.length - 3} more device
                  {room.devices.length - 3 !== 1 ? "s" : ""}
                </>
              )}
            </button>
          )}
        </div>
      )}

      {/* Placeholder notice when no real HA data yet */}
      {room.devices.length === 0 && (
        <div className="flex items-center gap-2 rounded-xl bg-aura-purple/10 border border-aura-purple/20 px-3 py-2">
          <Lightbulb size={14} className="text-aura-purple shrink-0" aria-hidden="true" />
          <p className="text-xs text-aura-text-muted">
            Connect HA to see live device states.
          </p>
        </div>
      )}

      {/* Room-level all-off shortcut when devices are active */}
      {onlineCount > 0 && (
        <button
          onClick={async () => {
            for (const device of room.devices.filter((d) => d.state === "on")) {
              await onDeviceToggle(device);
            }
          }}
          className="mt-1 flex items-center justify-center gap-1.5 rounded-xl border border-aura-border/60 py-1.5 text-xs text-aura-text-muted hover:border-aura-red/50 hover:text-aura-red transition-all"
        >
          <Power size={12} aria-hidden="true" />
          Turn off all
        </button>
      )}
    </div>
  );
}
