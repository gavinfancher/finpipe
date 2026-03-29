const raw = import.meta.env.VITE_API_URL as string | undefined;

// Default to localhost:8080 for local dev
const base = (raw ?? `http://${window.location.hostname}:8080`).replace(/\/+$/, "");

export const API_BASE = base;

// Derive ws(s) from http(s)
export const WS_BASE = base.replace(/^http/, "ws");
