import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "AURA — Smart Home Assistant",
  description:
    "AURA by OASIS — Ambient. Unified. Responsive. Automated. Control your smart home from anywhere.",
  manifest: "/manifest.json",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
    ],
    apple: "/favicon.svg",
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "AURA",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: "#0F0F1A",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
      </head>
      <body
        style={{
          margin: 0,
          padding: 0,
          background: "#06060F",
          color: "#E2E8F0",
          fontFamily: "'Inter', -apple-system, system-ui, sans-serif",
          WebkitFontSmoothing: "antialiased",
          MozOsxFontSmoothing: "grayscale",
          minHeight: "100dvh",
        }}
      >
        {/* Animated ambient background — fixed layer behind all content */}
        <div
          aria-hidden="true"
          style={{
            pointerEvents: "none",
            position: "fixed",
            inset: 0,
            overflow: "hidden",
            zIndex: 0,
          }}
        >
          {/* Primary top-center purple bloom — drifts gently */}
          <div
            className="orb-1"
            style={{
              position: "absolute",
              top: "-15%",
              left: "50%",
              transform: "translateX(-50%)",
              width: 900,
              height: 700,
              borderRadius: "50%",
              background: "radial-gradient(ellipse, rgba(124,58,237,0.11) 0%, rgba(124,58,237,0.04) 50%, transparent 75%)",
              filter: "blur(60px)",
            }}
          />
          {/* Left blue accent — mid-page */}
          <div
            className="orb-2"
            style={{
              position: "absolute",
              top: "25%",
              left: "-15%",
              width: 600,
              height: 600,
              borderRadius: "50%",
              background: "radial-gradient(ellipse, rgba(59,130,246,0.07) 0%, transparent 70%)",
              filter: "blur(80px)",
            }}
          />
          {/* Right purple accent — lower third */}
          <div
            className="orb-3"
            style={{
              position: "absolute",
              top: "60%",
              right: "-12%",
              width: 500,
              height: 500,
              borderRadius: "50%",
              background: "radial-gradient(ellipse, rgba(139,92,246,0.06) 0%, transparent 70%)",
              filter: "blur(80px)",
            }}
          />
          {/* Bottom teal hint */}
          <div
            style={{
              position: "absolute",
              bottom: "-5%",
              left: "30%",
              width: 400,
              height: 300,
              borderRadius: "50%",
              background: "radial-gradient(ellipse, rgba(20,184,166,0.04) 0%, transparent 70%)",
              filter: "blur(60px)",
            }}
          />
          {/* Subtle grid overlay — gives depth */}
          <div
            className="grid-layer"
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage: [
                "linear-gradient(rgba(124,58,237,0.025) 1px, transparent 1px)",
                "linear-gradient(90deg, rgba(124,58,237,0.025) 1px, transparent 1px)",
              ].join(", "),
              backgroundSize: "60px 60px",
            }}
          />
          {/* Vignette — keeps edges dark and focused */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "radial-gradient(ellipse 80% 80% at 50% 50%, transparent 40%, rgba(6,6,15,0.6) 100%)",
            }}
          />
        </div>

        <div style={{ position: "relative", zIndex: 1, minHeight: "100dvh" }}>
          {children}
        </div>

        {/* Register service worker for PWA offline support */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              if ('serviceWorker' in navigator) {
                window.addEventListener('load', function() {
                  navigator.serviceWorker.register('/sw.js');
                });
              }
            `,
          }}
        />
      </body>
    </html>
  );
}
