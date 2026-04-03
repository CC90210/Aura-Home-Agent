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
      className="relative rounded-xl border overflow-hidden group cursor-default"
      style={{
        borderColor: `${dominantColor}30`,
        background: 'linear-gradient(135deg, #0E0E1E 0%, #12122A 100%)',
      }}
    >
      {/* Color palette strip */}
      <div className="flex h-2 w-full" aria-hidden="true">
        {drop.palette.map((color, i) => (
          <div
            key={i}
            className="flex-1 transition-all duration-500 group-hover:h-3"
            style={{ background: color }}
          />
        ))}
      </div>

      {/* Card body */}
      <div className="p-4">
        {/* Name + who saved */}
        <div className="flex items-start justify-between gap-2 mb-1">
          <h3 className="text-[13px] font-bold text-slate-100 leading-tight">{drop.name}</h3>
          <span
            className="text-[9px] font-bold tracking-widest uppercase px-1.5 py-0.5 rounded-md flex-shrink-0"
            style={{
              background: `${dominantColor}20`,
              color: dominantColor,
              border: `1px solid ${dominantColor}30`,
            }}
          >
            {drop.savedBy}
          </span>
        </div>

        <p className="text-[11px] text-slate-500 mb-3 leading-relaxed">{drop.description}</p>

        {/* Palette swatches */}
        <div className="flex items-center gap-1.5 mb-4" aria-label="Color palette">
          {drop.palette.map((color, i) => (
            <div
              key={i}
              className="w-4 h-4 rounded-full border border-white/10"
              style={{ background: color, boxShadow: `0 0 4px ${color}55` }}
              aria-hidden="true"
            />
          ))}
        </div>

        {/* Activate button */}
        <button
          onClick={handleActivate}
          disabled={loading}
          aria-label={`Activate ${drop.name} scene`}
          className={[
            'w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[12px] font-semibold',
            'transition-all duration-200 border',
            activated
              ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400'
              : 'bg-purple-600/15 border-purple-600/30 text-violet-300 hover:bg-purple-600/25 hover:border-purple-600/50',
            loading ? 'opacity-60 cursor-wait' : '',
          ].join(' ')}
        >
          {loading ? (
            <span
              className="w-3 h-3 rounded-full border-2 border-violet-400/30 border-t-violet-400"
              style={{ animation: 'spin 0.7s linear infinite' }}
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
      className="relative rounded-xl border border-dashed border-purple-900/40 overflow-hidden
                 flex flex-col items-center justify-center gap-3 p-6
                 hover:border-purple-600/50 hover:bg-purple-900/10
                 transition-all duration-200 group min-h-[180px]"
    >
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center border border-dashed border-purple-600/40
                   group-hover:border-purple-500/60 group-hover:bg-purple-600/15 transition-all duration-200"
      >
        <Plus size={18} className="text-purple-500 group-hover:text-violet-400 transition-colors" aria-hidden="true" />
      </div>
      <div className="text-center">
        <div className="text-[13px] font-semibold text-slate-400 group-hover:text-slate-300 transition-colors">
          Save Current State
        </div>
        <div className="text-[11px] text-slate-600 mt-0.5">Snapshot your vibe as a Drop</div>
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
    <div className="rounded-2xl border border-purple-900/30 bg-[#0E0E1E]/90 backdrop-blur-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-purple-900/20">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-violet-600/15 border border-violet-600/25">
          <Layers size={14} className="text-violet-400" aria-hidden="true" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-100 tracking-wide">AURA Drops</h2>
          <p className="text-[11px] text-slate-500 mt-0.5">Saved scene snapshots — one tap to activate</p>
        </div>
        <span className="ml-auto text-[11px] text-slate-500 font-mono">{drops.length} saved</span>
      </div>

      {/* Grid */}
      <div
        className="p-4 grid gap-3"
        style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}
      >
        {drops.map((drop) => (
          <DropCard key={drop.id} drop={drop} onActivate={handleActivate} />
        ))}
        <AddDropCard />
      </div>
    </div>
  );
}
