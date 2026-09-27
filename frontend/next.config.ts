import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server (.next/standalone/server.js) for the Docker image. Vercel packages
  // Next.js apps itself (and sets VERCEL=1 while building), so it builds without it.
  output: process.env.VERCEL ? undefined : "standalone",
};

export default nextConfig;
