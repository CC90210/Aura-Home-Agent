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
  { name: 'Echo Dot (x3)',     entity_id: 'media_player.living_room_speaker', watts: 15,   dailyKwh: 0.36, weeklyKwh: 2.5,  color: '#A78BFA', trend: 'stable' },
  { name: 'Gaming PC',         entity_id: 'switch.gaming_pc',                 watts: 320,  dailyKwh: 4.80, weeklyKwh: 22.1, color: '#F59E0B', trend: 'up'     },
  { name: 'Living Room LEDs',  entity_id: 'light.living_room',                watts: 22,   dailyKwh: 0.35, weeklyKwh: 1.9,  color: '#60A5FA', trend: 'down'   },
  { name: 'Studio Key Light',  entity_id: 'switch.key_light',                 watts: 45,   dailyKwh: 0.68, weeklyKwh: 3.1,  color: '#34D399', trend: 'stable' },
  { name: 'Air Purifier',      entity_id: 'switch.air_purifier',              watts: 28,   dailyKwh: 0.67, weeklyKwh: 4.5,  color: '#F87171', trend: 'up'     },
  { name: 'Coffee Maker',      entity_id: 'switch.coffee_maker',              watts: 1200, dailyKwh: 0.24, weeklyKwh: 1.6,  color: '#FB923C', trend: 'stable' },
];

// Totals
const DAILY_KWH_TOTAL  = DEVICES.reduce((s, d) => s + d.dailyKwh,  0);
const WEEKLY_KWH_TOTAL = DEVICES.reduce((s, d) => s + d.weeklyKwh, 0);
const DAILY_LIMIT      = 12;  // kWh goal
const WEEKLY_LIMIT     = 80;  // kWh goal

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
  const ratio      = Math.min(value / max, 1);
  const radius     = (size - strokeWidth) / 2;
  const circ       = 2 * Math.PI * radius;
  const dashOffset = circ * (1 - ratio);
  const ringColor  = colorFromRatio(ratio);
  const cx         = size / 2;
  const cy         = size / 2;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <div style={{ position: 'relative', width: size, height: size }}>
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
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 1,
          }}
        >
          <span style={{ fontSize: 18, fontWeight: 700, color: ringColor }}>
            {value.toFixed(1)}
          </span>
          <span
            style={{
              fontSize: 9,
              color: '#64748B',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
            }}
          >
            kWh
          </span>
        </div>
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#E2E8F0' }}>{label}</div>
        <div style={{ fontSize: 10, color: '#64748B' }}>{sublabel}</div>
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
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      {/* Color dot */}
      <div
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          flexShrink: 0,
          background: device.color,
          boxShadow: `0 0 5px ${device.color}88`,
        }}
        aria-hidden="true"
      />

      {/* Name */}
      <span
        style={{
          fontSize: 12,
          color: '#94A3B8',
          width: 144,
          flexShrink: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {device.name}
      </span>

      {/* Bar */}
      <div
        style={{
          flex: 1,
          height: 6,
          borderRadius: 9999,
          background: 'rgba(255,255,255,0.05)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            borderRadius: 9999,
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
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          width: 64,
          justifyContent: 'flex-end',
          flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#CBD5E1' }}>{kwh.toFixed(2)}</span>
        {device.trend === 'up' && (
          <TrendingUp size={10} style={{ color: '#F87171' }} aria-label="trending up" />
        )}
        {device.trend === 'down' && (
          <TrendingDown size={10} style={{ color: '#34D399' }} aria-label="trending down" />
        )}
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
    <div
      style={{
        borderRadius: 16,
        border: '1px solid rgba(88, 28, 135, 0.3)',
        background: 'rgba(14, 14, 30, 0.9)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '16px 20px',
          borderBottom: '1px solid rgba(88, 28, 135, 0.2)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 32,
            height: 32,
            borderRadius: 8,
            background: 'rgba(245, 158, 11, 0.1)',
            border: '1px solid rgba(245, 158, 11, 0.25)',
          }}
        >
          <Zap size={14} style={{ color: '#FBBF24' }} aria-hidden="true" />
        </div>
        <div>
          <h2
            style={{
              fontSize: 14,
              fontWeight: 600,
              color: '#E2E8F0',
              letterSpacing: '0.025em',
              margin: 0,
            }}
          >
            Energy
          </h2>
          <p style={{ fontSize: 11, color: '#64748B', marginTop: 2, marginBottom: 0 }}>
            Smart plug power usage
          </p>
        </div>

        {/* Toggle */}
        <div
          style={{
            marginLeft: 'auto',
            display: 'flex',
            borderRadius: 8,
            overflow: 'hidden',
            border: '1px solid rgba(88, 28, 135, 0.3)',
          }}
          role="group"
          aria-label="View period"
        >
          {(['daily', 'weekly'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              style={{
                padding: '4px 12px',
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
                border: 'none',
                cursor: 'pointer',
                transition: 'background 0.2s ease, color 0.2s ease',
                background: view === v ? 'rgba(109, 40, 217, 0.4)' : 'transparent',
                color: view === v ? '#C4B5FD' : '#64748B',
              }}
            >
              {v === 'daily' ? 'Today' : 'Week'}
            </button>
          ))}
        </div>
      </div>

      {/* Rings */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-around',
          padding: '24px 20px',
          borderBottom: '1px solid rgba(88, 28, 135, 0.15)',
        }}
      >
        <CircularRing
          value={DAILY_KWH_TOTAL}
          max={DAILY_LIMIT}
          size={110}
          strokeWidth={8}
          label="Today"
          sublabel={`of ${DAILY_LIMIT} kWh`}
        />
        <div
          style={{ height: 64, width: 1, background: 'rgba(88, 28, 135, 0.25)' }}
          aria-hidden="true"
        />
        <CircularRing
          value={WEEKLY_KWH_TOTAL}
          max={WEEKLY_LIMIT}
          size={110}
          strokeWidth={8}
          label="This Week"
          sublabel={`of ${WEEKLY_LIMIT} kWh`}
        />
        {/* % of goal — hidden on smallest screens via a media query workaround: always show on md+ */}
        <div
          style={{ height: 64, width: 1, background: 'rgba(88, 28, 135, 0.25)' }}
          aria-hidden="true"
        />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <span
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: colorFromRatio(totalKwh / limit),
            }}
          >
            {Math.round((totalKwh / limit) * 100)}%
          </span>
          <span
            style={{
              fontSize: 10,
              color: '#64748B',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
            }}
          >
            {view === 'daily' ? 'of daily' : 'of weekly'} goal
          </span>
        </div>
      </div>

      {/* Device bars */}
      <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 4,
          }}
        >
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: '#64748B',
              textTransform: 'uppercase',
              letterSpacing: '0.1em',
            }}
          >
            By Device
          </span>
          <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>
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
