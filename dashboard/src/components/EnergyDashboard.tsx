'use client';

import { useState } from 'react';
import { Zap, TrendingUp, TrendingDown } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DeviceEnergy {
  name: string;
  entity_id: string;
  watts: number;
  dailyKwh: number;
  weeklyKwh: number;
  color: string;
  trend: 'up' | 'down' | 'stable';
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const DEVICES: DeviceEnergy[] = [
  { name: 'Echo Dot (x3)',     entity_id: 'media_player.living_room_speaker', watts: 15, dailyKwh: 0.36,  weeklyKwh: 2.5,  color: '#A78BFA', trend: 'stable' },
  { name: 'Gaming PC',        entity_id: 'switch.gaming_pc',     watts: 320, dailyKwh: 4.80,  weeklyKwh: 22.1, color: '#F59E0B', trend: 'up'     },
  { name: 'Living Room LEDs', entity_id: 'light.living_room',    watts: 22,  dailyKwh: 0.35,  weeklyKwh: 1.9,  color: '#60A5FA', trend: 'down'   },
  { name: 'Studio Key Light', entity_id: 'switch.key_light',     watts: 45,  dailyKwh: 0.68,  weeklyKwh: 3.1,  color: '#34D399', trend: 'stable' },
  { name: 'Air Purifier',     entity_id: 'switch.air_purifier',  watts: 28,  dailyKwh: 0.67,  weeklyKwh: 4.5,  color: '#F87171', trend: 'up'     },
  { name: 'Coffee Maker',     entity_id: 'switch.coffee_maker',  watts: 1200,dailyKwh: 0.24,  weeklyKwh: 1.6,  color: '#FB923C', trend: 'stable' },
];

// Totals
const DAILY_KWH_TOTAL  = DEVICES.reduce((s, d) => s + d.dailyKwh,  0);
const WEEKLY_KWH_TOTAL = DEVICES.reduce((s, d) => s + d.weeklyKwh, 0);
const DAILY_LIMIT      = 12;   // kWh goal
const WEEKLY_LIMIT     = 80;   // kWh goal

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function colorFromRatio(ratio: number): string {
  if (ratio < 0.6) return '#34D399'; // green
  if (ratio < 0.85) return '#F59E0B'; // yellow
  return '#F87171'; // red
}

// ---------------------------------------------------------------------------
// Circular ring SVG
// ---------------------------------------------------------------------------

interface RingProps {
  value: number;
  max: number;
  size: number;
  strokeWidth: number;
  label: string;
  sublabel: string;
}

function CircularRing({ value, max, size, strokeWidth, label, sublabel }: RingProps) {
  const ratio     = Math.min(value / max, 1);
  const radius    = (size - strokeWidth) / 2;
  const circ      = 2 * Math.PI * radius;
  const dashOffset = circ * (1 - ratio);
  const ringColor  = colorFromRatio(ratio);
  const cx         = size / 2;
  const cy         = size / 2;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }} aria-hidden="true">
          {/* Track */}
          <circle
            cx={cx} cy={cy} r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.05)"
            strokeWidth={strokeWidth}
          />
          {/* Progress */}
          <circle
            cx={cx} cy={cy} r={radius}
            fill="none"
            stroke={ringColor}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={dashOffset}
            style={{
              transition: 'stroke-dashoffset 1s ease, stroke 0.5s ease',
              filter: `drop-shadow(0 0 6px ${ringColor}88)`,
            }}
          />
        </svg>
        {/* Center text */}
        <div
          className="absolute inset-0 flex flex-col items-center justify-center"
          style={{ gap: 1 }}
        >
          <span className="text-[18px] font-bold text-slate-100" style={{ color: ringColor }}>
            {value.toFixed(1)}
          </span>
          <span className="text-[9px] text-slate-500 tracking-widest uppercase">kWh</span>
        </div>
      </div>
      <div className="text-center">
        <div className="text-[12px] font-semibold text-slate-200">{label}</div>
        <div className="text-[10px] text-slate-500">{sublabel}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Device bar row
// ---------------------------------------------------------------------------

interface DeviceBarProps {
  device: DeviceEnergy;
  maxKwh: number;
  view: 'daily' | 'weekly';
}

function DeviceBar({ device, maxKwh, view }: DeviceBarProps) {
  const kwh   = view === 'daily' ? device.dailyKwh : device.weeklyKwh;
  const ratio = Math.min(kwh / maxKwh, 1);

  return (
    <div className="flex items-center gap-3 group">
      {/* Color dot */}
      <div
        className="w-2 h-2 rounded-full flex-shrink-0"
        style={{ background: device.color, boxShadow: `0 0 5px ${device.color}88` }}
        aria-hidden="true"
      />

      {/* Name */}
      <span className="text-[12px] text-slate-400 w-36 flex-shrink-0 truncate">{device.name}</span>

      {/* Bar */}
      <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${ratio * 100}%`,
            background: device.color,
            boxShadow: `0 0 4px ${device.color}66`,
            transition: 'width 0.8s ease',
          }}
          role="progressbar"
          aria-valuenow={kwh}
          aria-valuemax={maxKwh}
          aria-label={`${device.name}: ${kwh} kWh`}
        />
      </div>

      {/* kWh + trend */}
      <div className="flex items-center gap-1 w-16 justify-end flex-shrink-0">
        <span className="text-[11px] font-mono text-slate-300">{kwh.toFixed(2)}</span>
        {device.trend === 'up' && <TrendingUp size={10} className="text-red-400" aria-label="trending up" />}
        {device.trend === 'down' && <TrendingDown size={10} className="text-emerald-400" aria-label="trending down" />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function EnergyDashboard() {
  const [view, setView] = useState<'daily' | 'weekly'>('daily');

  const maxKwh = view === 'daily'
    ? Math.max(...DEVICES.map((d) => d.dailyKwh))
    : Math.max(...DEVICES.map((d) => d.weeklyKwh));

  const totalKwh = view === 'daily' ? DAILY_KWH_TOTAL : WEEKLY_KWH_TOTAL;
  const limit    = view === 'daily' ? DAILY_LIMIT     : WEEKLY_LIMIT;

  return (
    <div className="rounded-2xl border border-purple-900/30 bg-[#0E0E1E]/90 backdrop-blur-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-purple-900/20">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/25">
          <Zap size={14} className="text-amber-400" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-100 tracking-wide">Energy</h2>
          <p className="text-[11px] text-slate-500 mt-0.5">Smart plug power usage</p>
        </div>

        {/* Toggle */}
        <div
          className="ml-auto flex rounded-lg overflow-hidden border border-purple-900/30"
          role="group"
          aria-label="View period"
        >
          {(['daily', 'weekly'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={[
                'px-3 py-1 text-[11px] font-semibold tracking-wide uppercase transition-colors',
                view === v
                  ? 'bg-purple-700/40 text-violet-300'
                  : 'bg-transparent text-slate-500 hover:text-slate-300',
              ].join(' ')}
            >
              {v === 'daily' ? 'Today' : 'Week'}
            </button>
          ))}
        </div>
      </div>

      {/* Rings */}
      <div className="flex items-center justify-around px-5 py-6 border-b border-purple-900/15">
        <CircularRing
          value={DAILY_KWH_TOTAL}
          max={DAILY_LIMIT}
          size={110}
          strokeWidth={8}
          label="Today"
          sublabel={`of ${DAILY_LIMIT} kWh`}
        />
        <div className="h-16 w-px bg-purple-900/25" aria-hidden="true" />
        <CircularRing
          value={WEEKLY_KWH_TOTAL}
          max={WEEKLY_LIMIT}
          size={110}
          strokeWidth={8}
          label="This Week"
          sublabel={`of ${WEEKLY_LIMIT} kWh`}
        />
        <div className="hidden sm:block h-16 w-px bg-purple-900/25" aria-hidden="true" />
        <div className="hidden sm:flex flex-col items-center gap-1">
          <span className="text-[22px] font-bold" style={{ color: colorFromRatio(totalKwh / limit) }}>
            {Math.round((totalKwh / limit) * 100)}%
          </span>
          <span className="text-[10px] text-slate-500 uppercase tracking-widest">
            {view === 'daily' ? 'of daily' : 'of weekly'} goal
          </span>
        </div>
      </div>

      {/* Device bars */}
      <div className="px-5 py-4 flex flex-col gap-3">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest">
            By Device
          </span>
          <span className="text-[10px] text-slate-600 font-mono">
            kWh / {view === 'daily' ? 'day' : 'week'}
          </span>
        </div>
        {DEVICES.sort((a, b) =>
          view === 'daily' ? b.dailyKwh - a.dailyKwh : b.weeklyKwh - a.weeklyKwh
        ).map((device) => (
          <DeviceBar key={device.entity_id} device={device} maxKwh={maxKwh} view={view} />
        ))}
      </div>
    </div>
  );
}
