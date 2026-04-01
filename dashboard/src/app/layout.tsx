import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "AURA Dashboard — Smart Home Control",
  description:
    "AURA by OASIS — Ambient. Unified. Responsive. Automated. Control your smart home from anywhere.",
  manifest: "/manifest.json",
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
    <html lang="en" className={`dark ${inter.variable}`}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
      </head>
      <body className="bg-aura-dark text-aura-text font-sans antialiased">
        {/* Ambient background glow — top center purple radial */}
        <div
          aria-hidden="true"
          className="pointer-events-none fixed inset-0 overflow-hidden"
        >
          <div className="absolute -top-40 left-1/2 -translate-x-1/2 h-[600px] w-[800px] rounded-full bg-aura-purple opacity-[0.06] blur-[120px]" />
          <div className="absolute top-1/3 -left-40 h-[400px] w-[400px] rounded-full bg-aura-blue opacity-[0.04] blur-[100px]" />
          <div className="absolute top-2/3 -right-40 h-[400px] w-[400px] rounded-full bg-aura-purple opacity-[0.04] blur-[100px]" />
        </div>

        <div className="relative z-10 min-h-dvh">{children}</div>
      </body>
    </html>
  );
}
