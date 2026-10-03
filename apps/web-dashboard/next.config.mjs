/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  env: {
    TICKET_SERVICE_URL: process.env.TICKET_SERVICE_URL || 'http://localhost:3001',
    DEV_AGENT_SERVICE_URL: process.env.DEV_AGENT_SERVICE_URL || 'http://localhost:3007',
  },
};

export default nextConfig;
