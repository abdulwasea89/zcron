"use client";

import { useEffect, useState } from "react";
import { SettingsView } from "./SettingsView";

/* A modal shell around the shared settings view, modelled on Notion's settings:
   a near-full-height panel with the section rail inside and a floating close
   button, no title bar. Escape and a click on the scrim both dismiss it, and
   the panel plays a short exit before it unmounts. */
export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [closing, setClosing] = useState(false);

  function close() {
    if (closing) return;
    setClosing(true);
    window.setTimeout(onClose, 130);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-3 sm:p-6">
      <div
        className={`absolute inset-0 bg-black/40 backdrop-blur-[2px] ${closing ? "animate-fade-out" : "animate-fade-in"}`}
        onClick={close}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        className={`relative z-10 flex h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border border-[var(--border)] bg-background shadow-2xl ${
          closing ? "animate-dialog-out" : "animate-dialog-in"
        }`}
      >
        <button
          type="button"
          onClick={close}
          aria-label="Close settings"
          className="absolute right-3 top-3 z-20 flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        <div className="min-h-0 flex-1 overflow-hidden py-6 pl-4 pr-12 sm:pl-6 sm:pr-14">
          <SettingsView onNavigate={close} />
        </div>
      </div>
    </div>
  );
}
