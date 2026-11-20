import type { Metadata } from "next";

import { HomePage } from "@/components/public/home-page";

export const metadata: Metadata = {
  title: {
    absolute: "LOOPMESH — Industrial Resource Intelligence",
  },
  description:
    "LOOPMESH connects industrial producers and receivers through structured material profiles, deterministic compatibility screening and evidence-backed recovery accounting.",
};

/**
 * The public product homepage.
 *
 * `/` is deliberately not a redirect: signed-in operators and prospective
 * visitors both get the real landing page, and every call to action is a real
 * link (`/login`, section anchors). `/login` forwards an already-authenticated
 * visitor into their workspace, so the workspace remains one click away.
 */
export default function PublicHomePage() {
  return <HomePage />;
}
