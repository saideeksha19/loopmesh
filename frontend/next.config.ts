import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Keep Turbopack scoped to this app instead of inferring a workspace root
  // from parent directories.
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
