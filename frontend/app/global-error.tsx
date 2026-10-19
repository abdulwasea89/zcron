"use client";

import { useEffect } from "react";
import { Toaster, toast } from "sonner";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    toast.error("Acron hit an unexpected problem. Please try again.");
  }, [error.digest]);

  return (
    <html lang="en">
      <body style={{ margin: 0, backgroundColor: "#f1f5f9", color: "#0f172a", fontFamily: "system-ui, -apple-system, sans-serif" }}>
        <Toaster position="bottom-right" richColors closeButton />
        <div style={{ display: "flex", minHeight: "100dvh", alignItems: "center", justifyContent: "center", padding: "1.5rem" }}>
          <div style={{ maxWidth: "400px", width: "100%", textAlign: "center" }}>
            <div style={{ fontSize: "48px", marginBottom: "1rem", lineHeight: 1 }}>⚠</div>
            <h1 style={{ fontSize: "20px", fontWeight: 600, margin: "0 0 0.5rem" }}>Critical error</h1>
            <p style={{ fontSize: "14px", color: "#475569", margin: "0 0 0.25rem", lineHeight: 1.5 }}>
              Something went wrong. Our team has been notified.
            </p>
            {error.digest && (
              <p style={{ fontSize: "11px", color: "#94a3b8", margin: "1rem 0 0", wordBreak: "break-all" }}>
                Error ID: {error.digest}
              </p>
            )}
            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "center", marginTop: "1.5rem" }}>
              <button
                onClick={reset}
                style={{
                  padding: "0.625rem 1.25rem",
                  fontSize: "14px",
                  fontWeight: 600,
                  backgroundColor: "#0a0a0a",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "10px",
                  cursor: "pointer",
                }}
              >
                Try again
              </button>
              <a
                href="/login"
                style={{
                  padding: "0.625rem 1.25rem",
                  fontSize: "14px",
                  fontWeight: 600,
                  backgroundColor: "#ffffff",
                  color: "#0f172a",
                  border: "1px solid #e2e8f0",
                  borderRadius: "10px",
                  textDecoration: "none",
                }}
              >
                Go to login
              </a>
            </div>
          </div>
        </div>
      </body>
    </html>
  );
}
