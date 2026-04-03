'use client';

import { useState, useEffect } from 'react';
import { Server, Cpu, MemoryStick, Clock, Mic, Brain, Wifi, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type HealthStatus = 'healthy' | 'warning' | 'error' | 'offline';

interface ServiceHealth {
  id: string;
  name: string;
  status: HealthStatus;
  detail: string;
  uptime: string | null;
  /** Lucide icon component */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>;
}

interface SystemMetrics {
  cpuTemp: number;    // Celsius
  cpuUsage: number;   // 0-100
  memUsed: number;    // GB
  memTotal: number;   // GB
  diskUsed: number;   // GB
  diskTotal: number;  // GB
  uptime: string;     // human-readable
  piOnline: boolean;
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const INITIAL_METRICS: SystemMetrics = {
  cpuTemp:   54,
  cpuUsage:  23,
  memUsed:   2.1,
  memTotal:  8,
  diskUsed:  14.2,
  diskTotal: 64,
  uptime:    '4d 11h 22m',
  piOnline:  true,
};

const MOCK_SERVICES: ServiceHealth[] = [
  {
    id: 'voice-agent',
    name: 'Voice Agent',
    status: 'healthy',
    detail: '"Hey Aura" listening',
    uptime: '4d 11h',
    icon: Mic,
  },
  {
    id: 'clap-detector',
    name: 'Clap Detector',
    status: 'healthy',
    detail: 'USB mic active',
    uptime: '4d 11h',
    icon: Wifi,
  },
  {
    id: 'learning-engine',
    name: 'Learning Engine',
    status: 'warning',
    detail: 'Pattern sync pending',
    uptime: '3d 07h',
    icon: Brain,
  },
  {
    id: 'ha-mcp',
    name: 'HA MCP Bridge',
    status: 'healthy',
    detail: '70+ tools connected',
    uptime: '4d 11h',
    icon: Server,
  },
  {
    id: 'ha-core',
    name: 'Home Assistant',
    status: 'healthy',
    detail: 'v2026.3.4 · 14 entities',
    uptime: '4d 11h',
    icon: Wifi,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_CONFIG: Record<HealthStatus, { color: string; label: string; dotColor: string }> = {
  healthy: { color: '#10B981', label: 'Healthy', dotColor: '#34D399' },
  warning: { color: '#F59E0B', label: 'Warning',  dotColor: '#FBBF24' },
  error:   { color: '#F87171', label: 'Error',    dotColor: '#F87171' },
  offline: { color: '#64748B', label: 'Offline',  dotColor: '#64748B' },
};

function tempColor(c: number): string {
  if (c < 55) return '#10B981';
  if (c < 70) return '#F59E0B';
  return '#F87171';
}

function usageColor(pct: number): string {
  if (pct < 60) return '#10B981';
  if (pct < 80) return '#F59E0B';
  return '#F87171';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface MetricBarProps {
  label: string;
  value: number;
  max: number;
  unit: string;
  color: string;
}

function MetricBar({ label, value, max, unit, color }: MetricBarProps) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          marginBottom: 4,
        }}
      >
        <span style={{ fontSize: 11, color: '#64748B' }}>{label}</span>
        <span style={{ fontSize: 11, fontFamily: 'monospace', color }}>
          {value.toFixed(1)}{unit}
        </span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 9999,
          background: 'rgba(255,255,255,0.05)',
          overflow: 'hidden',
        }}
        role="progressbar"
        aria-valuenow={value}
        aria-valuemax={max}
        aria-label={`${label}: ${value}${unit}`}
      >
        <div
          style={{
            height: '100%',
            borderRadius: 9999,
            width: `${pct}%`,
            background: color,
            boxShadow: `0 0 4px ${color}66`,
            transition: 'width 0.8s ease, background 0.3s ease',
          }}
        />
      </div>
    </div>
  );
}

interface StatusDotProps {
  status: HealthStatus;
  animated?: boolean;
}

function StatusDot({ status, animated = false }: StatusDotProps) {
  const { color, dotColor } = STATUS_CONFIG[status];
  return (
    <div
      style={{ position: 'relative', flexShrink: 0, width: 10, height: 10 }}
      aria-hidden="true"
    >
      {animated && status === 'healthy' && (
        <span
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            background: dotColor,
            opacity: 0.5,
            animation: 'ping 1.8s cubic-bezier(0,0,0.2,1) infinite',
          }}
        />
      )}
      <span
        style={{
          position: 'relative',
          display: 'block',
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: dotColor,
          boxShadow: `0 0 5px ${color}88`,
        }}
      />
    </div>
  );
}

function StatusIcon({ status }: { status: HealthStatus }) {
  if (status === 'healthy') {
    return <CheckCircle2 size={13} style={{ color: '#34D399' }} aria-hidden="true" />;
  }
  if (status === 'warning') {
    return <AlertTriangle size={13} style={{ color: '#FBBF24' }} aria-hidden="true" />;
  }
  if (status === 'error') {
    return <XCircle size={13} style={{ color: '#F87171' }} aria-hidden="true" />;
  }
  return <XCircle size={13} style={{ color: '#64748B' }} aria-hidden="true" />;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SystemHealth() {
  const [metrics, setMetrics]         = useState<SystemMetrics>(INITIAL_METRICS);
  const [services]                    = useState<ServiceHealth[]>(MOCK_SERVICES);
  const [lastRefresh, setLastRefresh] = useState<string>('just now');

  // Simulate live metric fluctuation
  useEffect(() => {
    const id = setInterval(() => {
      setMetrics((prev) => ({
        ...prev,
        cpuTemp:  Math.max(42, Math.min(78, prev.cpuTemp  + (Math.random() * 4 - 2))),
        cpuUsage: Math.max(8,  Math.min(95, prev.cpuUsage + (Math.random() * 10 - 5))),
        memUsed:  Math.max(1.5, Math.min(6.5, prev.memUsed + (Math.random() * 0.1 - 0.05))),
      }));
      setLastRefresh('just now');
    }, 5000);
    return () => clearInterval(id);
  }, []);

  const healthyCount = services.filter((s) => s.status === 'healthy').length;
  const overallHealth: HealthStatus =
    services.some((s) => s.status === 'error')  ? 'error'   :
    services.some((s) => s.status === 'warning') ? 'warning' :
    metrics.piOnline                             ? 'healthy' : 'offline';

  const { color: overallColor } = STATUS_CONFIG[overallHealth];

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
            background: 'rgba(37, 99, 235, 0.15)',
            border: '1px solid rgba(37, 99, 235, 0.25)',
          }}
        >
          <Server size={14} style={{ color: '#60A5FA' }} aria-hidden="true" />
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
            System Health
          </h2>
          <p style={{ fontSize: 11, color: '#64748B', marginTop: 2, marginBottom: 0 }}>
            Raspberry Pi 5 &middot; Updated {lastRefresh}
          </p>
        </div>

        {/* Overall status pill */}
        <div
          style={{
            marginLeft: 'auto',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 12px',
            borderRadius: 9999,
            border: `1px solid ${overallColor}30`,
            background: `${overallColor}15`,
            color: overallColor,
            fontSize: 11,
            fontWeight: 600,
          }}
          role="status"
          aria-label={`Overall system status: ${STATUS_CONFIG[overallHealth].label}`}
        >
          <StatusDot status={overallHealth} animated />
          {STATUS_CONFIG[overallHealth].label}
        </div>
      </div>

      <div
        style={{
          padding: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 20,
        }}
      >
        {/* Pi hardware metrics */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Cpu size={12} style={{ color: '#64748B' }} aria-hidden="true" />
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: '#64748B',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
              }}
            >
              Hardware
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingLeft: 4 }}>
            <MetricBar
              label="CPU Temp"
              value={Math.round(metrics.cpuTemp)}
              max={85}
              unit="°C"
              color={tempColor(metrics.cpuTemp)}
            />
            <MetricBar
              label="CPU Usage"
              value={Math.round(metrics.cpuUsage)}
              max={100}
              unit="%"
              color={usageColor(metrics.cpuUsage)}
            />
            <MetricBar
              label={`Memory  (${metrics.memUsed.toFixed(1)} / ${metrics.memTotal} GB)`}
              value={metrics.memUsed}
              max={metrics.memTotal}
              unit=" GB"
              color={usageColor((metrics.memUsed / metrics.memTotal) * 100)}
            />
            <MetricBar
              label={`Disk  (${metrics.diskUsed} / ${metrics.diskTotal} GB)`}
              value={metrics.diskUsed}
              max={metrics.diskTotal}
              unit=" GB"
              color={usageColor((metrics.diskUsed / metrics.diskTotal) * 100)}
            />
          </div>

          {/* Uptime */}
          <div style={{ marginTop: 12, paddingLeft: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Clock size={11} style={{ color: '#475569' }} aria-hidden="true" />
            <span style={{ fontSize: 11, color: '#475569' }}>Uptime:</span>
            <span style={{ fontSize: 11, fontFamily: 'monospace', color: '#94A3B8' }}>
              {metrics.uptime}
            </span>
          </div>
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: 'rgba(88, 28, 135, 0.2)' }} aria-hidden="true" />

        {/* Services */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <MemoryStick size={12} style={{ color: '#64748B' }} aria-hidden="true" />
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: '#64748B',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
              }}
            >
              Services
            </span>
            <span style={{ marginLeft: 'auto', fontSize: 11, color: '#475569' }}>
              <span style={{ color: '#10B981' }}>{healthyCount}</span>/{services.length} running
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {services.map((svc, idx) => {
              const ServiceIcon = svc.icon;
              const { color } = STATUS_CONFIG[svc.status];
              return (
                <div
                  key={svc.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 12px',
                    borderRadius: 12,
                    background: idx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                  }}
                >
                  {/* Icon */}
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 8,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      border: `1px solid ${color}25`,
                      background: `${color}12`,
                    }}
                  >
                    <ServiceIcon size={13} aria-hidden="true" style={{ color }} />
                  </div>

                  {/* Name + detail */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        color: '#E2E8F0',
                        lineHeight: 1.3,
                      }}
                    >
                      {svc.name}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: '#475569',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {svc.detail}
                    </div>
                  </div>

                  {/* Status */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    <StatusIcon status={svc.status} />
                    {svc.uptime && (
                      <span style={{ fontSize: 10, color: '#475569', fontFamily: 'monospace' }}>
                        {svc.uptime}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
