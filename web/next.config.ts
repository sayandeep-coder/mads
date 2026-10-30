import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Reachable from the iPhone (or any device on the same Wi-Fi) via the
  // Mac's LAN IP — see README for the `next dev -- --hostname 0.0.0.0` setup.
  allowedDevOrigins: ["192.168.0.215"],
  // Without this, Turbopack walks up from web/ looking for the nearest
  // lockfile to infer the workspace root, and picks up an unrelated
  // package-lock.json sitting in the home directory (a different, unrelated
  // project) instead of this one — pinning it here is the fix Next.js's own
  // warning recommends.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
