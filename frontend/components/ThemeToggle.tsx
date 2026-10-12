"use client";

import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { THEME_OPTIONS } from "@/lib/themes";

function cx(...parts: (string | false | undefined | null)[]): string {
  return parts.filter(Boolean).join(" ");
}

function ThemeIcon() {
  return (
    <svg
      className="h-[15px] w-[15px]"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {/* sun */}
      <path d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
      {/* moon */}
      <path d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
    </svg>
  );
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Hydration guard: the resolved theme is only known client-side, so we render
  // inert until mounted to keep SSR and first paint in sync (next-themes docs).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), []);

  // Dismiss on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    function onDown(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label="Change theme"
        aria-expanded={open}
        title={mounted && theme ? `Theme: ${theme}` : "Theme"}
        onClick={() => setOpen((v) => !v)}
        className={cx(
          "inline-flex h-8 w-8 items-center justify-center rounded-full border transition-colors duration-150",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
          open
            ? "border-[var(--border-strong)] text-[var(--foreground)]"
            : "border-[var(--border)] text-[var(--foreground-muted)] hover:border-[var(--border-strong)] hover:text-[var(--foreground)]",
        )}
      >
        <ThemeIcon />
      </button>

      {open && (
        <div className="absolute bottom-full right-0 z-50 mb-2 w-44 overflow-hidden rounded-md border border-[var(--border)] bg-[var(--surface)] py-1 shadow-lg animate-scale-in">
          <p className="mono-label px-3 pb-1 pt-2 text-[10px] text-[var(--muted-foreground)]">
            Theme
          </p>
          {THEME_OPTIONS.map((opt) => {
            const active = mounted && theme === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => {
                  setTheme(opt.value);
                  setOpen(false);
                }}
                className={cx(
                  "flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[12px] transition-colors",
                  "focus:outline-none focus-visible:bg-[var(--accent-light)]",
                  active
                    ? "bg-[var(--primary-light)] font-medium text-[var(--primary)]"
                    : "text-[var(--foreground-muted)] hover:bg-[var(--accent-light)] hover:text-[var(--foreground)]",
                )}
              >
                <span
                  aria-hidden="true"
                  className="h-3.5 w-3.5 shrink-0 rounded-full border border-[var(--border-strong)]"
                  style={{ background: opt.swatch }}
                />
                <span className="flex-1">{opt.label}</span>
                {active && (
                  <svg
                    className="h-3 w-3"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    aria-hidden="true"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
