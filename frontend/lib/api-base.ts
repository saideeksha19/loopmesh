/**
 * Server-side base URL of the LOOPMESH API.
 *
 * Kept dependency-free so route handlers and the server client can import it
 * without pulling request-scoped helpers into their module graph.
 *
 * Managed platforms expose a private service as a bare ``host:port`` (Render's
 * ``fromService … hostport``, for example), which is not a valid URL for
 * ``fetch``. A missing scheme is therefore treated as plain HTTP on the private
 * network, and a trailing slash is removed because callers append
 * ``/api/v1/...`` to this value.
 */
export function normaliseApiBase(value: string | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed) return null;

  const hasScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed);
  const withScheme = hasScheme ? trimmed : `http://${trimmed}`;
  return withScheme.replace(/\/+$/, "");
}

export const API_BASE =
  normaliseApiBase(process.env.API_INTERNAL_URL) ??
  normaliseApiBase(process.env.NEXT_PUBLIC_API_URL) ??
  "http://127.0.0.1:8000";
