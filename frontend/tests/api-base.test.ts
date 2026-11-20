import { describe, expect, it } from "vitest";

import { normaliseApiBase } from "../lib/api-base";

describe("normaliseApiBase", () => {
  it("returns null for unset or blank values", () => {
    expect(normaliseApiBase(undefined)).toBeNull();
    expect(normaliseApiBase("")).toBeNull();
    expect(normaliseApiBase("   ")).toBeNull();
  });

  it("keeps an explicit scheme unchanged", () => {
    expect(normaliseApiBase("http://127.0.0.1:8000")).toBe("http://127.0.0.1:8000");
    expect(normaliseApiBase("https://api.example.com")).toBe("https://api.example.com");
  });

  it("assumes http for a scheme-less private host and port", () => {
    // What Render's `fromService … hostport` provides.
    expect(normaliseApiBase("loopmesh-api:8000")).toBe("http://loopmesh-api:8000");
    expect(normaliseApiBase("loopmesh-api")).toBe("http://loopmesh-api");
  });

  it("trims whitespace and trailing slashes", () => {
    expect(normaliseApiBase("  http://127.0.0.1:8000/  ")).toBe("http://127.0.0.1:8000");
    expect(normaliseApiBase("loopmesh-api:8000///")).toBe("http://loopmesh-api:8000");
  });
});
