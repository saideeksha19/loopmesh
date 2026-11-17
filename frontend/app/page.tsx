import { redirect } from "next/navigation";

import { HomePage } from "@/components/public/home-page";
import { loadSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function PublicHomePage() {
  const state = await loadSession();

  if (state.status === "authenticated") {
    redirect("/overview");
    return null;
  }

  // If unavailable, do not treat as sign-out; still render the public homepage.
  return <HomePage />;
}
