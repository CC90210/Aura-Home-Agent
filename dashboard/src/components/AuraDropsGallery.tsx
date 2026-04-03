'use client';

import { useState } from 'react';
import { Plus, Play, Layers } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AuraDrop {
  id: string;
  name: string;
  description: string;
  /** Small array of hex color strings representing the scene palette */
  palette: string[];
  /** HA webhook ID to fire */
  webhook_id: string;
  /** When this drop was saved */
  savedAt: string;
  /** Who saved it */
  savedBy: 'CC' | 'Adon';
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const MOCK_DROPS: AuraDrop[] = [
  {
    id: 'drop-1',
    name: 'Midnight Grind',
    description: 'Deep purple LEDs, lo-fi, max focus',
    palette: ['#2D1B69', '#7C3AED', '#1E1B4B', '#0A0A14'],
    webhook_id: 'aura_drop_midnight_grind',
    savedAt: '2026-03-28T23:14:00Z',
    savedBy: 'CC',
  },
  {
    id: 'drop-2',
    name: 'Golden Hour',
    description: 'Warm amber, Spotify mood playlist, 70%',
    palette: ['#92400E', '#F59E0B', '#FCD34D', '#FFFBEB'],
    webhook_id: 'aura_drop_golden_hour',
    savedAt: '2026-03-30T18:45:00Z',
    savedBy: 'Adon',
  },
  {
    id: 'drop-3',
    name: 'Blue Archive',
    description: 'Cool blue light, chill beats, 55% brightness',
    palette: ['#1E3A5F', '#2563EB', '#60A5FA', '#BFDBFE'],
    webhook_id: 'aura_drop_blue_archive',
    savedAt: '2026-04-01T09:30:00Z',
    savedBy: 'CC',
  },
  {
    id: 'drop-4',
    name: 'Crimson Studio',
    description: 'Red accents, key light 100%, stream ready',
    palette: ['#450A0A', '#DC2626', '#F87171', '#FEE2E2'],
    webhook_id: 'aura_drop_crimson_studio',
    savedAt: '2026-04-02T20:11:00Z',
    savedBy: 'CC',
  },
  {
    id: 'drop-5',
    name: 'Emerald Rest',
    description: 'Soft green, white noise, wind-down mode',
    palette: ['#064E3B', '#059669', '#34D399', '#D1FAE5'],
    webhook_id: 'aura_drop_emerald_rest',
    savedAt: '2026-04-03T22:00:00Z',
    savedBy: 'Adon',
  },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface DropCardProps {
  drop: AuraDrop;
  onActivate: (drop: AuraDrop) => Promise<void>;
}

function DropCard({ drop, onActivate }: DropCardProps) {
  const [loading, setLoading] = useState(false);
  const [activated, setActivated] = useState(false);

  const handleActivate = async () => {
    if (loading) return;
    setLoading(true);
    try {
      await onActivate(drop);
      setActivated(true);
      setTimeout(() => setActivated(false), 2500);
    } finally {
      setLoading(false);
    }
  };

  const dominantColor = drop.palette[1] ?? '#7C3AED';

  return (
    <div
      style={{
        position: 'relative',
        borderRadius: 12,
        border: `1px solid ${dominantColor}30`,
        overflow: 'hidden',
        cursor: 'default',
        background: 'linear-gradient(135deg, #0E0E1E 0%, #12122A 100%)',
      }}
    >
      {/* Color palette strip */}
      <div style={{ display: 'flex', height: 8, width: '100%' }} aria-hidden="true">
        {drop.palette.map((color, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              background: color,
              transition: 'height 0.5s ease',
            }}
          />
        ))}
      </div>

      {/* Card body */}
      <div style={{ padding: 16 }}>
        {/* Name + who saved */}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 8,
            marginBottom: 4,
          }}
        >
          <h3
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: '#E2E8F0',
              lineHeight: 1.3,
              margin: 0,
            }}
          >
            {drop.name}
          </h3>
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              padding: '2px 6px',
              borderRadius: 6,
              flexShrink: 0,
              background: `${dominantColor}20`,
              color: dominantColor,
              border: `1px solid ${dominantColor}30`,
            }}
          >
            {drop.savedBy}
          </span>
        </div>

        <p style={{ fontSize: 11, color: '#64748B', marginBottom: 12, lineHeight: 1.5, marginTop: 0 }}>
          {drop.description}
        </p>

        {/* Palette swatches */}
        <div
          style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 16 }}
          aria-label="Color palette"
        >
          {drop.palette.map((color, i) => (
            <div
              key={i}
              style={{
                width: 16,
                height: 16,
                borderRadius: '50%',
                border: '1px solid rgba(255,255,255,0.1)',
                background: color,
                boxShadow: `0 0 4px ${color}55`,
              }}
              aria-hidden="true"
            />
          ))}
        </div>

        {/* Activate button */}
        <button
          onClick={handleActivate}
          disabled={loading}
          aria-label={`Activate ${drop.name} scene`}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            padding: '8px 0',
            borderRadius: 8,
            fontSize: 12,
            fontWeight: 600,
            border: activated
              ? '1px solid rgba(16, 185, 129, 0.4)'
              : '1px solid rgba(124, 58, 237, 0.3)',
            background: activated
              ? 'rgba(16, 185, 129, 0.2)'
              : 'rgba(124, 58, 237, 0.15)',
            color: activated ? '#34D399' : '#C4B5FD',
            opacity: loading ? 0.6 : 1,
            cursor: loading ? 'wait' : 'pointer',
            transition: 'all 0.2s ease',
          }}
        >
          {loading ? (
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: '50%',
                border: '2px solid rgba(167, 139, 250, 0.3)',
                borderTopColor: '#A78BFA',
                animation: 'spin 0.7s linear infinite',
                display: 'block',
              }}
              aria-hidden="true"
            />
          ) : activated ? (
            <>
              <span aria-hidden="true">&#x2713;</span> Activated
            </>
          ) : (
            <>
              <Play size={12} aria-hidden="true" fill="currentColor" />
              Activate Drop
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function AddDropCard() {
  return (
    <button
      aria-label="Save current state as new AURA Drop"
      style={{
        position: 'relative',
        borderRadius: 12,
        border: '1px dashed rgba(88, 28, 135, 0.4)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        padding: 24,
        minHeight: 180,
        background: 'transparent',
        cursor: 'pointer',
        transition: 'border-color 0.2s ease, background 0.2s ease',
      }}
      onMouseEnter={(e) => {
        const el = e.currentTarget as HTMLButtonElement;
        el.style.borderColor = 'rgba(124, 58, 237, 0.5)';
        el.style.background = 'rgba(88, 28, 135, 0.1)';
      }}
      onMouseLeave={(e) => {
        const el = e.currentTarget as HTMLButtonElement;
        el.style.borderColor = 'rgba(88, 28, 135, 0.4)';
        el.style.background = 'transparent';
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px dashed rgba(124, 58, 237, 0.4)',
          transition: 'all 0.2s ease',
        }}
      >
        <Plus size={18} style={{ color: '#8B5CF6' }} aria-hidden="true" />
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#94A3B8' }}>
          Save Current State
        </div>
        <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>
          Snapshot your vibe as a Drop
        </div>
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AuraDropsGallery() {
  const [drops] = useState<AuraDrop[]>(MOCK_DROPS);

  const handleActivate = async (drop: AuraDrop): Promise<void> => {
    // In production: POST /api/scene with { webhook_id: drop.webhook_id }
    await new Promise<void>((resolve) => setTimeout(resolve, 600));
  };

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
            background: 'rgba(124, 58, 237, 0.15)',
            border: '1px solid rgba(124, 58, 237, 0.25)',
          }}
        >
          <Layers size={14} style={{ color: '#A78BFA' }} aria-hidden="true" />
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
            AURA Drops
          </h2>
          <p style={{ fontSize: 11, color: '#64748B', marginTop: 2, marginBottom: 0 }}>
            Saved scene snapshots — one tap to activate
          </p>
        </div>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#64748B', fontFamily: 'monospace' }}>
          {drops.length} saved
        </span>
      </div>

      {/* Grid */}
      <div
        style={{
          padding: 16,
          display: 'grid',
          gap: 12,
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
        }}
      >
        {drops.map((drop) => (
          <DropCard key={drop.id} drop={drop} onActivate={handleActivate} />
        ))}
        <AddDropCard />
      </div>
    </div>
  );
}
