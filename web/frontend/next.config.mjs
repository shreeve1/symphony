/** @type {import('next').NextConfig} */

// API origin Podium's FastAPI backend (#012a) listens on. Same-origin from the
// browser's perspective: we proxy /api/* through Next rather than calling 8090
// directly, which avoids CORS and keeps every fetch in the app a relative path.
const API_ORIGIN = process.env.PODIUM_API_ORIGIN ?? "http://127.0.0.1:8090";

const nextConfig = {
  // Build output dir. Defaults to .next; deploy.sh overrides it to a staging
  // dir so a rebuild never overwrites the .next the running server serves from.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${API_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
