---
description: "Develop the AURA dashboard (Next.js 15 + React 19). Use for any UI changes to the smart home control panel."
---
Dashboard is at `dashboard/` — Next.js 15 with React 19 and Tailwind 4.

Development:
```bash
cd dashboard && npm run dev
```

Key files:
- `dashboard/src/app/page.tsx` — Main dashboard page
- `dashboard/src/components/AuraDropsGallery.tsx` — Drops gallery
- `dashboard/src/components/EnergyDashboard.tsx` — Energy analytics
- `dashboard/src/components/MusicVisualizer.tsx` — Music visualization
- `dashboard/src/components/SystemHealth.tsx` — System health display
- `dashboard/src/components/VoiceActivityLog.tsx` — Voice activity log

Rules:
- Dark theme by default (matches OASIS brand)
- Mobile-responsive (CC controls from phone)
- Tailwind 4 uses CSS-based config via postcss — no tailwind.config.ts
