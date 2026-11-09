import type { NextConfig } from "next";

// The browser talks only to this Next.js server; it forwards /api/* to the FastAPI service,
// which holds the Anthropic key (spec: the API key stays on the server). API_URL is the
// FastAPI address, not a secret.
const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  turbopack: { root: import.meta.dirname }, // this folder, not a lockfile further up
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default config;
