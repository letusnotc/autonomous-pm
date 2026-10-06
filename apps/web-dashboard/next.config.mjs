/** @type {import('next').NextConfig} */
// Service URLs (TICKET_SERVICE_URL, DEV_AGENT_SERVICE_URL) are read by the API
// routes at runtime – don't inline them here, or a Docker image built without
// them would be stuck with the localhost defaults.
const nextConfig = {
  output: 'standalone',
};

export default nextConfig;
