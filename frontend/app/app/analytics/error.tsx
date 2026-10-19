"use client";

import { useEffect } from "react";
import { Button, Card } from "@/components/ui";
import { toast } from "sonner";

export default function AnalyticsErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    toast.error("Analytics could not load. Please try again.");
  }, [error.digest]);

  return (
    <div className="flex items-start justify-center py-16">
      <Card className="w-full max-w-sm p-8 text-center">
        <div className="mb-4 text-5xl">⚠</div>
        <h1 className="mb-2 font-heading text-2xl tracking-tight text-[var(--foreground)]">Could not load analytics</h1>
        <p className="mb-6 text-sm text-[var(--foreground-muted)]">
          An error occurred while loading the analytics data.
        </p>
        {error.digest && (
          <p className="mb-4 text-[10px] break-all text-[var(--muted)]">
            Error ID: {error.digest}
          </p>
        )}
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
          <Button onClick={reset}>Try again</Button>
          <Button variant="secondary" onClick={() => (window.location.href = "/app")}>
            Back to dashboard
          </Button>
        </div>
      </Card>
    </div>
  );
}
