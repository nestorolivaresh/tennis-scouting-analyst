import type { NextConfig } from "next";

// The browser talks only to this Next.js server; it forwards the three routes the app uses to
// the FastAPI service, which holds the Anthropic key (spec: the API key stays on the server).
// Nothing else on the API (its docs, POST /report) is reachable through this app. API_URL is
// the FastAPI address, not a secret.
const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";
const ROUTES = ["players/search", "report/stream", "chat"];

const config: NextConfig = {
  turbopack: { root: import.meta.dirname }, // this folder, not a lockfile further up
  experimental: {
    // The proxy closes a response that has been silent this long. Next's default is 30
    // seconds; a model call can run longer (the agent's limit is 60 seconds per request), and
    // the API's keep-alives may not come while the model thinks before its first token.
    proxyTimeout: 90_000,
  },
  async rewrites() {
    return ROUTES.map((route) => ({ source: `/api/${route}`, destination: `${apiUrl}/${route}` }));
  },
};

export default config;
