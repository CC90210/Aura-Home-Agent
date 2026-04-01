import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        "aura-purple": "#7C3AED",
        "aura-purple-light": "#9F67FF",
        "aura-purple-dim": "#4C1D95",
        "aura-blue": "#3B82F6",
        "aura-blue-light": "#60A5FA",
        "aura-dark": "#0F0F1A",
        "aura-darker": "#080810",
        "aura-card": "#1A1A2E",
        "aura-card-hover": "#212140",
        "aura-border": "#2D2D50",
        "aura-text": "#E2E8F0",
        "aura-text-muted": "#94A3B8",
        "aura-green": "#10B981",
        "aura-red": "#EF4444",
        "aura-amber": "#F59E0B",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "aura-glow":
          "radial-gradient(ellipse at center, rgba(124,58,237,0.15) 0%, transparent 70%)",
        "card-glass":
          "linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)",
      },
      boxShadow: {
        "aura-purple": "0 0 20px rgba(124,58,237,0.4)",
        "aura-purple-sm": "0 0 10px rgba(124,58,237,0.25)",
        "aura-blue": "0 0 20px rgba(59,130,246,0.4)",
        "aura-green": "0 0 15px rgba(16,185,129,0.35)",
        glass: "inset 0 1px 0 rgba(255,255,255,0.08), 0 4px 24px rgba(0,0,0,0.4)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "glow-pulse": "glow-pulse 2s ease-in-out infinite",
        ripple: "ripple 0.6s linear",
        "fade-in": "fade-in 0.3s ease-out",
        "slide-up": "slide-up 0.4s ease-out",
      },
      keyframes: {
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 10px rgba(124,58,237,0.3)" },
          "50%": { boxShadow: "0 0 25px rgba(124,58,237,0.7)" },
        },
        ripple: {
          "0%": { transform: "scale(0)", opacity: "0.5" },
          "100%": { transform: "scale(4)", opacity: "0" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { transform: "translateY(12px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
    },
  },
  plugins: [],
};

export default config;
