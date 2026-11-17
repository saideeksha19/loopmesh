"use client";

import { authFetch } from "@/lib/client-auth";

export type MutationFailure = {
  ok: false;
  error: string;
  code?: string;
  details?: Record<string, unknown>;
  fields?: string[];
};
export type MutationSuccess<T> = { ok: true; data: T };
export type MutationResult<T> = MutationSuccess<T> | MutationFailure;

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown> & {
      fields?: { location: string; message: string }[];
    };
  };
};

const NETWORK_ERROR = "The API is not reachable. Start the backend and retry.";
const EXPIRED_ERROR = "Your session has expired. Sign in again.";

async function parseFailure(response: Response): Promise<MutationFailure> {
  let message = `The API rejected the request (${response.status}).`;
  let code: string | undefined;
  let details: Record<string, unknown> | undefined;
  let fields: string[] | undefined;
  try {
    const body = (await response.json()) as ErrorEnvelope;
    if (body.error?.message) message = body.error.message;
    code = body.error?.code;
    details = body.error?.details;
    fields = body.error?.details?.fields?.map(
      (field) => `${field.location}: ${field.message}`,
    );
  } catch {
    /* non-JSON body */
  }
  return { ok: false, error: message, code, details, fields };
}

async function request<T>(
  path: string,
  init: RequestInit,
  { retryOnExpiry = true }: { retryOnExpiry?: boolean } = {},
): Promise<MutationResult<T>> {
  try {
    const response = await authFetch(path, init, { retryOnExpiry });
    if (!response.ok) {
      const failure = await parseFailure(response);
      // A 401 means "session expired" only for credential-bearing requests.
      // Sign-in and renewal failures keep the API's own wording.
      if (response.status === 401 && retryOnExpiry) {
        return { ...failure, code: failure.code ?? "session_expired", error: EXPIRED_ERROR };
      }
      return failure;
    }
    if (response.status === 204) return { ok: true, data: undefined as T };
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return { ok: false, error: NETWORK_ERROR, code: "network_error" };
  }
}

export function postJson<T>(
  path: string,
  body: unknown,
  options: { retryOnExpiry?: boolean } = {},
): Promise<MutationResult<T>> {
  return request<T>(
    path,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    },
    options,
  );
}

export function patchJson<T>(
  path: string,
  body: unknown,
  options: { retryOnExpiry?: boolean } = {},
): Promise<MutationResult<T>> {
  return request<T>(
    path,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    },
    options,
  );
}

export function postFile<T>(path: string, file: File): Promise<MutationResult<T>> {
  const form = new FormData();
  form.append("file", file);
  return request<T>(path, { method: "POST", body: form });
}

export function getJson<T>(path: string): Promise<MutationResult<T>> {
  return request<T>(path, { method: "GET" });
}

export function deleteJson<T>(path: string): Promise<MutationResult<T>> {
  return request<T>(path, { method: "DELETE" });
}
