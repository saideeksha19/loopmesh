"use client";

/**
 * Phase 2A stored a development actor id in localStorage. Real authentication
 * replaces that flow; these exports remain as inert compatibility shims so
 * existing imports do not break while the session UI is being rebuilt.
 */

export const DEFAULT_ACTOR_ID = "";

export function readActorId(): string {
  return "";
}

export function writeActorId(_actorId: string): void {
  /* no-op: identity comes from the authenticated session */
}

export function useActorId(): string {
  return "";
}
