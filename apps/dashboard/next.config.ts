import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  typedRoutes: true,
  // Self-contained server output (server.js + only the node_modules it
  // actually needs) so the Docker runtime stage doesn't have to ship the
  // full workspace node_modules tree — see apps/dashboard/Dockerfile.
  output: 'standalone',
};

export default nextConfig;
