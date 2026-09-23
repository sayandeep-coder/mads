import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Reachable from the iPhone (or any device on the same Wi-Fi) via the
  // Mac's LAN IP — see README for the `next dev -- --hostname 0.0.0.0` setup.
  allowedDevOrigins: ["192.168.0.215"],
};

export default nextConfig;
