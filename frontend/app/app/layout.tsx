/// <reference types="react/canary" />
import Link from "next/link";
import { redirect } from "next/navigation";
import { ViewTransition } from "react";
import { Sidebar } from "@/components/Sidebar";
import { AssistantChatsProvider } from "@/components/assistant/AssistantChats";
import { AssistantShell } from "@/components/assistant/AssistantShell";
import { RealtimeProvider } from "@/components/Realtime";
import { SettingsProvider } from "@/components/settings/SettingsProvider";
import { RequiredOnboarding } from "@/components/RequiredOnboarding";
import { OfflineSyncStatus } from "@/components/OfflineSyncStatus";
import { BackendError, backend } from "@/lib/backend";
import { isAuthenticated } from "@/lib/session";
import type { OrganizationOut } from "@/lib/types";

// Server-rendered shell for all authenticated admin pages. Fetches the current
// org once (server-side, cookie-authed) and renders the sidebar around it.
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  if (!(await isAuthenticated())) redirect("/login");

  let org: OrganizationOut | null = null;
  try {
    org = await backend<OrganizationOut>("/organizations/me");
  } catch (error) {
    if (error instanceof BackendError && error.status === 401) redirect("/login");
    if (error instanceof TypeError) {
      return (
        <main className="flex min-h-dvh items-center justify-center bg-background px-6 py-12 text-foreground">
          <span hidden data-acron-offline-unavailable="true" />
          <section className="w-full max-w-md border border-[var(--border)] bg-[var(--surface)] p-8 text-center shadow-xl">
            <span className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-warning-bg text-xl text-warning" aria-hidden="true">!</span>
            <p className="mono-label mb-2 text-[10px] text-brand">API CONNECTION</p>
            <h1 className="font-heading text-2xl font-medium tracking-tight">Your workspace API is unavailable</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Acron could not reach the backend. Check that the API is running and that the web app’s BACKEND_URL points to it, then retry.
            </p>
            <Link href="/app" className="mt-6 inline-flex h-9 items-center justify-center bg-brand px-4 text-sm font-medium text-brand-foreground transition hover:brightness-110">
              Retry connection
            </Link>
          </section>
        </main>
      );
    }
    throw error;
  }
  let ownerEmail = "";
  let profile: Record<string, string | null> = {};
  if (!org.onboarding_complete) {
    try {
      profile = await backend<Record<string, string | null>>("/auth/me/profile");
      ownerEmail = profile.email ?? "";
    } catch {
      ownerEmail = "";
    }
  }

  const appShell = (
    <SettingsProvider>
        <div className="min-h-screen bg-background text-foreground noise-overlay">
          {!org.onboarding_complete ? <RequiredOnboarding email={ownerEmail} initial={{
            full_name: profile.full_name, phone: profile.phone, occupation: profile.occupation,
            education: profile.education, address: profile.address, city: profile.city,
            date_of_birth: profile.date_of_birth, gender: profile.gender,
            emergency_contact: profile.emergency_contact, venue: org.name === "Workspace setup" ? "" : org.name,
            industry: org.industry, country: org.country, timezone: org.timezone, currency: org.default_currency,
          }} /> : null}
          {/* The chat list sits above both the sidebar and the pages: the
              sidebar lists recent chats and /app/assistant opens them, and the
              two are siblings here — neither contains the other. Keyed by org
              so switching tenants drops the previous org's chats. */}
          {org.onboarding_complete ? <AssistantChatsProvider key={org.id}>
            <div className="relative lg:flex lg:min-h-screen">
              <OfflineSyncStatus organizationId={org.id} />
              <Sidebar
                orgName={org.name}
                orgCode={org.org_code}
                orgId={org.id}
                industry={org.industry}
                tier={org.saas_tier}
              />
              <div className="relative flex min-w-0 flex-1 flex-col">
                {/* Content column: centered, capped at 1240 (DESIGN §10.2). */}
                <main className="w-full flex-1 self-center px-5 py-8 sm:px-8 lg:max-w-[1240px] lg:py-10">
                  {/* The assistant dock wraps every page here, so the prompt bar
                      is one mount for the whole shell. It stays mounted on
                      /app/assistant too — that is where it hands a prompt over.

                      The ViewTransition names the page region: only
                      navigations tagged transitionTypes={["tab"]} (the
                      sidebar Overview tabs) animate, crossfading the content
                      while the shell stays pinned. CSS lives in globals.css. */}
                  <AssistantShell orgId={org.id}>
                    <ViewTransition
                      name="app-content"
                      default="none"
                      enter={{ default: "none", tab: "auto" }}
                      exit={{ default: "none", tab: "auto" }}
                    >
                      {children}
                    </ViewTransition>
                  </AssistantShell>
                </main>
              </div>
            </div>
          </AssistantChatsProvider> : <div className="relative lg:flex lg:min-h-screen">
            <Sidebar
              orgName={org.name}
              orgCode={org.org_code}
              orgId={org.id}
              industry={org.industry}
              tier={org.saas_tier}
            />
            <div className="relative flex min-w-0 flex-1 flex-col">
              <main className="w-full flex-1 self-center px-5 py-8 sm:px-8 lg:max-w-[1240px] lg:py-10">
                {children}
              </main>
            </div>
          </div>}
        </div>
    </SettingsProvider>
  );
  return org.onboarding_complete ? <RealtimeProvider>{appShell}</RealtimeProvider> : appShell;
}
