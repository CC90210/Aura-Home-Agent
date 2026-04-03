'use client';

import { useState } from 'react';
import { Zap, TrendingUp, TrendingDown } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types — exported so callers can pass real device data in the future
// ---------------------------------------------------------------------------

export interface DeviceEnergy {
  name: string;
  entity_id: string;
  watts: number;
  dailyKwh: number;
  weeklyKwh: number;
  color: string;
  trend: 'up' | 'down' | 'stable';
}

export interface EnergyDashboardProps {
  devices?: DeviceEnergy[];
  dailyLimitKwh?: number;
  weeklyLimitKwh?: number;
}

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
  isEmpty?: boolean;
}

function CircularRing({ value, max, size, strokeWidth, label, sublabel, isEmpty = false }: RingProps) {
  const ratio      = isEmpty ? 0 : Math.min(value / max, 1);
  const radius     = (size - strokeWidth) / 2;
  const circ       = 2 * Math.PI * radius;
  const dashOffset = circ * (1 - ratio);
  const ringColor  = isEmpty ? '#1E293B' : colorFromRatio(ratio);
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
              filter: isEmpty ? 'none' : `drop-shadow(0 0 6px ${ringColor}88)`,
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
          <span style={{ fontSize: 18, fontWeight: 700, color: isEmpty ? '#334155' : ringColor }}>
            {isEmpty ? '--' : value.toFixed(1)}
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

export default function EnergyDashboard({
  devices = [],
  dailyLimitKwh = 12,
  weeklyLimitKwh = 80,
}: EnergyDashboardProps) {
  const [view, setView] = useState<'daily' | 'weekly'>('daily');

  const hasDevices = devices.length > 0;

  const dailyTotal  = devices.reduce((s, d) => s + d.dailyKwh,  0);
  const weeklyTotal = devices.reduce((s, d) => s + d.weeklyKwh, 0);
  const totalKwh    = view === 'daily' ? dailyTotal  : weeklyTotal;
  const limit       = view === 'daily' ? dailyLimitKwh : weeklyLimitKwh;

  const maxKwh = hasDevices
    ? Math.max(...devices.map((d) => view === 'daily' ? d.dailyKwh : d.weeklyKwh))
    : 1; // avoid division by zero

  const sortedDevices = [...devices].sort((a, b) =>
    view === 'daily' ? b.dailyKwh - a.dailyKwh : b.weeklyKwh - a.weeklyKwh
  );

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

      {/* Rings — always show, use isEmpty flag when no data */}
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
          value={dailyTotal}
          max={dailyLimitKwh}
          size={110}
          strokeWidth={8}
          label="Today"
          sublabel={`of ${dailyLimitKwh} kWh`}
          isEmpty={!hasDevices}
        />
        <div
          style={{ height: 64, width: 1, background: 'rgba(88, 28, 135, 0.25)' }}
          aria-hidden="true"
        />
        <CircularRing
          value={weeklyTotal}
          max={weeklyLimitKwh}
          size={110}
          strokeWidth={8}
          label="This Week"
          sublabel={`of ${weeklyLimitKwh} kWh`}
          isEmpty={!hasDevices}
        />
        <div
          style={{ height: 64, width: 1, background: 'rgba(88, 28, 135, 0.25)' }}
          aria-hidden="true"
        />
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <span
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: hasDevices ? colorFromRatio(totalKwh / limit) : '#334155',
            }}
          >
            {hasDevices ? `${Math.round((totalKwh / limit) * 100)}%` : '--'}
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

      {/* Device list or empty state */}
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

        {hasDevices ? (
          sortedDevices.map((device) => (
            <DeviceBar key={device.entity_id} device={device} maxKwh={maxKwh} view={view} />
          ))
        ) : (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '24px 0',
              gap: 8,
            }}
          >
            <Zap size={22} style={{ color: '#334155' }} aria-hidden="true" />
            <p style={{ fontSize: 13, color: '#475569', margin: 0, textAlign: 'center' }}>
              No devices reporting
            </p>
            <p style={{ fontSize: 11, color: '#334155', margin: 0, textAlign: 'center' }}>
              Connect smart plugs to see power usage
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
