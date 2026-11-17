/**
 * Server-side base URL of the LOOPMESH API.
 *
 * Kept dependency-free so route handlers and the server client can import it
 * without pulling request-scoped helpers into their module graph.
 */
export const API_BASE =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000";
