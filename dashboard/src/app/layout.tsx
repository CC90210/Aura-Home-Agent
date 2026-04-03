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
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
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
          background: "#0A0A14",
          color: "#E2E8F0",
          fontFamily: "'Inter', -apple-system, system-ui, sans-serif",
          WebkitFontSmoothing: "antialiased",
          MozOsxFontSmoothing: "grayscale",
          minHeight: "100dvh",
        }}
      >
        {/* Ambient background glow — guaranteed via inline styles */}
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
          <div
            style={{
              position: "absolute",
              top: "-10%",
              left: "50%",
              transform: "translateX(-50%)",
              width: 800,
              height: 600,
              borderRadius: "50%",
              background: "rgba(124,58,237,0.06)",
              filter: "blur(120px)",
            }}
          />
          <div
            style={{
              position: "absolute",
              top: "33%",
              left: "-10%",
              width: 400,
              height: 400,
              borderRadius: "50%",
              background: "rgba(59,130,246,0.04)",
              filter: "blur(100px)",
            }}
          />
          <div
            style={{
              position: "absolute",
              top: "66%",
              right: "-10%",
              width: 400,
              height: 400,
              borderRadius: "50%",
              background: "rgba(124,58,237,0.04)",
              filter: "blur(100px)",
            }}
          />
        </div>

        <div style={{ position: "relative", zIndex: 1, minHeight: "100dvh" }}>
          {children}
        </div>
      </body>
    </html>
  );
}
