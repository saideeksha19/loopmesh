/**
 * Password policy, mirrored from the API for immediate feedback.
 *
 * This is convenience only: `POST /auth/change-password` and invitation
 * acceptance re-run the same rules server-side, so the browser cannot widen
 * what is accepted.
 */

export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MIN_UNIQUE_CHARACTERS = 6;

export type PasswordCheck = { id: string; label: string; met: boolean };

export function passwordChecks(value: string): PasswordCheck[] {
  return [
    {
      id: "length",
      label: `At least ${PASSWORD_MIN_LENGTH} characters`,
      met: value.length >= PASSWORD_MIN_LENGTH,
    },
    {
      id: "case",
      label: "Upper and lower case letters",
      met: /[a-z]/.test(value) && /[A-Z]/.test(value),
    },
    {
      id: "symbol",
      label: "At least one number or symbol",
      met: /[^A-Za-z]/.test(value),
    },
    {
      id: "unique",
      label: `At least ${PASSWORD_MIN_UNIQUE_CHARACTERS} different characters`,
      met: new Set(value).size >= PASSWORD_MIN_UNIQUE_CHARACTERS,
    },
  ];
}

/** The first unmet rule, or null when the password satisfies the policy. */
export function passwordProblem(value: string): string | null {
  const unmet = passwordChecks(value).find((check) => !check.met);
  return unmet ? unmet.label : null;
}

export function passwordStrength(value: string): "empty" | "weak" | "strong" {
  if (!value) return "empty";
  return passwordProblem(value) ? "weak" : "strong";
}
