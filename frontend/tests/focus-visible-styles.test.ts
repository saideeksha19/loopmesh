import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// jsdom does not evaluate :focus-visible, so this guards the stylesheet contract
// that restores a visible keyboard indicator over the `outline-none` utility.
const css = readFileSync(path.resolve(process.cwd(), "app/globals.css"), "utf8");
const marker = "Keyboard focus must stay visible";
const start = css.indexOf(marker);
const focusBlock = css.slice(start, css.indexOf("@layer components", start));

describe("workspace keyboard focus styles", () => {
  it("declares the focus override block that follows the base focus token", () => {
    expect(start).toBeGreaterThan(-1);
    expect(focusBlock).toContain("@layer utilities");
  });

  it("covers the interactive element types that suppress outlines", () => {
    for (const selector of [
      "input:focus-visible",
      "select:focus-visible",
      "textarea:focus-visible",
      "button:focus-visible",
      "a:focus-visible",
    ]) {
      expect(focusBlock).toContain(selector);
    }
  });

  it("reuses the LoopMesh lime focus token with a non-animated outline", () => {
    expect(focusBlock).toContain("outline: 2px solid var(--color-lime-400)");
    expect(focusBlock).toContain("outline-offset: 2px");
    expect(focusBlock).toContain("box-shadow: 0 0 0 1px");
    // Outlines are not transitioned, so reduced-motion users get no animation.
    expect(focusBlock).not.toContain("transition");
  });

  it("keeps component-level focus-visible ring treatments untouched", () => {
    // Public components use `focus-visible:outline-none` (specificity 0,2,0),
    // which outranks the element-level rule, so their own ring still decides.
    expect(css).toContain("focus-visible:outline-none");
  });
});
