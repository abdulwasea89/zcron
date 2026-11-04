"use client";

import { useTransition, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui";
import { WorkspaceAction } from "@/components/WorkspaceAction";

export function DashboardRetry({ children = "This section couldn’t load." }: { children?: ReactNode }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  return <div className="dash-retry" role="status">
    <AlertCircle aria-hidden="true" /><span>{children}</span>
    <Button variant="secondary" className="dash-button dash-secondary" loading={pending} onClick={() => startTransition(() => router.refresh())}>
      <RefreshCw aria-hidden="true" />{pending ? "Retrying…" : "Retry"}
    </Button>
  </div>;
}

export function DashboardEmptyState({ icon, title, children, href, action }: {
  icon: ReactNode; title: string; children: ReactNode; href: string; action: string;
}) {
  return <div className="dash-empty">
    <span className="dash-empty-icon" aria-hidden="true">{icon}</span>
    <h3>{title}</h3><p>{children}</p>
    <WorkspaceAction href={href} className="dash-button dash-secondary">{action}<ArrowRight aria-hidden="true" /></WorkspaceAction>
  </div>;
}
