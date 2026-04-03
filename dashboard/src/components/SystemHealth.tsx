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
  cpuTemp: number;      // Celsius
  cpuUsage: number;     // 0-100
  memUsed: number;      // GB
  memTotal: number;     // GB
  diskUsed: number;     // GB
  diskTotal: number;    // GB
  uptime: string;       // human-readable
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

const STATUS_CONFIG: Record<HealthStatus, { color: string; label: string; dotClass: string }> = {
  healthy: { color: '#10B981', label: 'Healthy', dotClass: 'bg-emerald-400' },
  warning: { color: '#F59E0B', label: 'Warning',  dotClass: 'bg-amber-400'  },
  error:   { color: '#F87171', label: 'Error',    dotClass: 'bg-red-400'    },
  offline: { color: '#64748B', label: 'Offline',  dotClass: 'bg-slate-500'  },
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
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-[11px] text-slate-500">{label}</span>
        <span className="text-[11px] font-mono" style={{ color }}>
          {value.toFixed(1)}{unit}
        </span>
      </div>
      <div
        className="h-1.5 rounded-full bg-white/5 overflow-hidden"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemax={max}
        aria-label={`${label}: ${value}${unit}`}
      >
        <div
          className="h-full rounded-full"
          style={{
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
  const { color, dotClass } = STATUS_CONFIG[status];
  return (
    <div className="relative flex-shrink-0 w-2.5 h-2.5" aria-hidden="true">
      {animated && status === 'healthy' && (
        <span
          className={`absolute inset-0 rounded-full ${dotClass} opacity-50`}
          style={{ animation: 'ping 1.8s cubic-bezier(0,0,0.2,1) infinite' }}
        />
      )}
      <span
        className={`relative block w-2.5 h-2.5 rounded-full ${dotClass}`}
        style={{ boxShadow: `0 0 5px ${color}88` }}
      />
    </div>
  );
}

function StatusIcon({ status }: { status: HealthStatus }) {
  if (status === 'healthy') return <CheckCircle2 size={13} className="text-emerald-400" aria-hidden="true" />;
  if (status === 'warning') return <AlertTriangle size={13} className="text-amber-400" aria-hidden="true" />;
  if (status === 'error')   return <XCircle size={13} className="text-red-400" aria-hidden="true" />;
  return <XCircle size={13} className="text-slate-500" aria-hidden="true" />;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SystemHealth() {
  const [metrics, setMetrics]   = useState<SystemMetrics>(INITIAL_METRICS);
  const [services]              = useState<ServiceHealth[]>(MOCK_SERVICES);
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
    services.some((s) => s.status === 'error')   ? 'error'   :
    services.some((s) => s.status === 'warning')  ? 'warning' :
    metrics.piOnline                              ? 'healthy' : 'offline';

  const { color: overallColor } = STATUS_CONFIG[overallHealth];

  return (
    <div className="rounded-2xl border border-purple-900/30 bg-[#0E0E1E]/90 backdrop-blur-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-purple-900/20">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-600/15 border border-blue-600/25">
          <Server size={14} className="text-blue-400" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-100 tracking-wide">System Health</h2>
          <p className="text-[11px] text-slate-500 mt-0.5">Raspberry Pi 5 &middot; Updated {lastRefresh}</p>
        </div>

        {/* Overall status pill */}
        <div
          className="ml-auto flex items-center gap-2 px-3 py-1.5 rounded-full border text-[11px] font-semibold"
          style={{
            background: `${overallColor}15`,
            borderColor: `${overallColor}30`,
            color: overallColor,
          }}
          role="status"
          aria-label={`Overall system status: ${STATUS_CONFIG[overallHealth].label}`}
        >
          <StatusDot status={overallHealth} animated />
          {STATUS_CONFIG[overallHealth].label}
        </div>
      </div>

      <div className="p-5 flex flex-col gap-5">
        {/* Pi hardware metrics */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Cpu size={12} className="text-slate-500" aria-hidden="true" />
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest">Hardware</span>
          </div>
          <div className="flex flex-col gap-3 pl-1">
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
          <div className="mt-3 pl-1 flex items-center gap-2">
            <Clock size={11} className="text-slate-600" aria-hidden="true" />
            <span className="text-[11px] text-slate-600">Uptime:</span>
            <span className="text-[11px] font-mono text-slate-400">{metrics.uptime}</span>
          </div>
        </div>

        {/* Divider */}
        <div className="h-px bg-purple-900/20" aria-hidden="true" />

        {/* Services */}
        <div>
          <div className="flex items-center gap-2 mb-3">
            <MemoryStick size={12} className="text-slate-500" aria-hidden="true" />
            <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest">Services</span>
            <span className="ml-auto text-[11px] text-slate-600">
              <span style={{ color: '#10B981' }}>{healthyCount}</span>/{services.length} running
            </span>
          </div>

          <div className="flex flex-col gap-1">
            {services.map((svc, idx) => {
              const ServiceIcon = svc.icon;
              const { color } = STATUS_CONFIG[svc.status];
              return (
                <div
                  key={svc.id}
                  className={[
                    'flex items-center gap-3 py-2.5 px-3 rounded-xl',
                    idx % 2 === 0 ? 'bg-white/[0.02]' : '',
                  ].join(' ')}
                >
                  {/* Icon */}
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 border"
                    style={{
                      background: `${color}12`,
                      borderColor: `${color}25`,
                    }}
                  >
                    <ServiceIcon size={13} className="" aria-hidden="true" style={{ color }} />
                  </div>

                  {/* Name + detail */}
                  <div className="flex-1 min-w-0">
                    <div className="text-[12px] font-semibold text-slate-200 leading-tight">{svc.name}</div>
                    <div className="text-[10px] text-slate-600 truncate">{svc.detail}</div>
                  </div>

                  {/* Status */}
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <StatusIcon status={svc.status} />
                    {svc.uptime && (
                      <span className="text-[10px] text-slate-600 font-mono hidden sm:block">{svc.uptime}</span>
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
