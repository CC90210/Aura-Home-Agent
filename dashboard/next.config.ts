import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      {
        // Allow Home Assistant local media (album art, camera feeds)
        protocol: "http",
        hostname: "homeassistant.local",
        port: "8123",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;
