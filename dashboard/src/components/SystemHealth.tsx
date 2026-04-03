'use client';

import { Server, Cpu, MemoryStick, Clock, Mic, Brain, Wifi, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types — exported so callers can pass real data from /api/health
// ---------------------------------------------------------------------------

export type HealthStatus = 'healthy' | 'warning' | 'error' | 'offline';

export interface ServiceHealth {
  id: string;
  name: string;
  status: HealthStatus;
  detail: string;
  uptime: string | null;
}

export interface SystemMetrics {
  cpuTemp: number;    // Celsius
  cpuUsage: number;   // 0-100
  memUsed: number;    // GB
  memTotal: number;   // GB
  diskUsed: number;   // GB
  diskTotal: number;  // GB
  uptime: string;     // human-readable
}

export interface SystemHealthProps {
  metrics?: SystemMetrics;
  services?: ServiceHealth[];
  lastRefresh?: string;
}

// ---------------------------------------------------------------------------
// Default offline service definitions (names and icons only — no fake data)
// ---------------------------------------------------------------------------

const DEFAULT_SERVICES: (Omit<ServiceHealth, 'status' | 'detail' | 'uptime'> & {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  icon: React.ComponentType<any>;
})[] = [
  { id: 'voice-agent',    name: 'Voice Agent',    icon: Mic    },
  { id: 'clap-detector',  name: 'Clap Detector',  icon: Wifi   },
  { id: 'learning-engine',name: 'Learning Engine', icon: Brain  },
  { id: 'ha-mcp',         name: 'HA MCP Bridge',  icon: Server },
  { id: 'ha-core',        name: 'Home Assistant', icon: Wifi   },
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
  value: number | null; // null = no data
  max: number;
  unit: string;
  color: string;
}

function MetricBar({ label, value, max, unit, color }: MetricBarProps) {
  const pct = value !== null ? Math.min((value / max) * 100, 100) : 0;
  const displayValue = value !== null ? `${value.toFixed(1)}${unit}` : '--';
  const displayColor = value !== null ? color : '#334155';

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
        <span style={{ fontSize: 11, fontFamily: 'monospace', color: displayColor }}>
          {displayValue}
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
        aria-valuenow={value ?? 0}
        aria-valuemax={max}
        aria-label={`${label}: ${displayValue}`}
      >
        <div
          style={{
            height: '100%',
            borderRadius: 9999,
            width: `${pct}%`,
            background: value !== null ? color : 'transparent',
            boxShadow: value !== null ? `0 0 4px ${color}66` : 'none',
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

export default function SystemHealth({
  metrics,
  services,
  lastRefresh,
}: SystemHealthProps = {}) {
  const isConnected = metrics !== undefined;

  // Determine overall status
  const overallHealth: HealthStatus = !isConnected
    ? 'offline'
    : services?.some((s) => s.status === 'error')   ? 'error'
    : services?.some((s) => s.status === 'warning')  ? 'warning'
    : 'healthy';

  const { color: overallColor } = STATUS_CONFIG[overallHealth];

  // Build the service rows — use real data if available, otherwise show defaults as offline
  const serviceRows: (ServiceHealth & {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    icon: React.ComponentType<any>;
  })[] = DEFAULT_SERVICES.map((def) => {
    const real = services?.find((s) => s.id === def.id);
    return {
      ...def,
      status:  real?.status  ?? 'offline',
      detail:  real?.detail  ?? (isConnected ? 'Not running' : 'Pi offline'),
      uptime:  real?.uptime  ?? null,
    };
  });

  const healthyCount = serviceRows.filter((s) => s.status === 'healthy').length;

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
            Raspberry Pi 5
            {lastRefresh && isConnected ? ` \u00b7 Updated ${lastRefresh}` : ''}
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
          <StatusDot status={overallHealth} animated={isConnected} />
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
              value={metrics ? Math.round(metrics.cpuTemp) : null}
              max={85}
              unit="°C"
              color={metrics ? tempColor(metrics.cpuTemp) : '#334155'}
            />
            <MetricBar
              label="CPU Usage"
              value={metrics ? Math.round(metrics.cpuUsage) : null}
              max={100}
              unit="%"
              color={metrics ? usageColor(metrics.cpuUsage) : '#334155'}
            />
            <MetricBar
              label={metrics
                ? `Memory  (${metrics.memUsed.toFixed(1)} / ${metrics.memTotal} GB)`
                : 'Memory'}
              value={metrics ? metrics.memUsed : null}
              max={metrics?.memTotal ?? 8}
              unit=" GB"
              color={metrics ? usageColor((metrics.memUsed / metrics.memTotal) * 100) : '#334155'}
            />
            <MetricBar
              label={metrics
                ? `Disk  (${metrics.diskUsed} / ${metrics.diskTotal} GB)`
                : 'Disk'}
              value={metrics ? metrics.diskUsed : null}
              max={metrics?.diskTotal ?? 64}
              unit=" GB"
              color={metrics ? usageColor((metrics.diskUsed / metrics.diskTotal) * 100) : '#334155'}
            />
          </div>

          {/* Uptime row */}
          <div style={{ marginTop: 12, paddingLeft: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Clock size={11} style={{ color: '#475569' }} aria-hidden="true" />
            <span style={{ fontSize: 11, color: '#475569' }}>Uptime:</span>
            <span style={{ fontSize: 11, fontFamily: 'monospace', color: metrics ? '#94A3B8' : '#334155' }}>
              {metrics?.uptime ?? '--'}
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
              {isConnected ? (
                <>
                  <span style={{ color: '#10B981' }}>{healthyCount}</span>/{serviceRows.length} running
                </>
              ) : (
                <span style={{ color: '#334155' }}>Connect Pi to see status</span>
              )}
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {serviceRows.map((svc, idx) => {
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

          {/* Connection hint */}
          {!isConnected && (
            <p
              style={{
                fontSize: 11,
                color: '#334155',
                marginTop: 16,
                marginBottom: 0,
                textAlign: 'center',
              }}
            >
              Connect your Raspberry Pi to see live metrics
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
