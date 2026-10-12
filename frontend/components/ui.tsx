"use client";

import { forwardRef, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Children, isValidElement } from "react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  KeyboardEvent as ReactKeyboardEvent,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
  ReactNode,
} from "react";

function cx(...parts: (string | false | undefined | null)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* Field-label voice: mono caps, letterspaced, muted (DESIGN §6.6). */
const LABEL = "mb-1.5 block font-mono text-[10px] uppercase tracking-widest text-muted-foreground";
/* Softer label voice for long, narrow forms (e.g. the plan sheet), where a
   column of shouty caps reads as noise. Same slot, sentence case. */
const LABEL_SENTENCE = "mb-1.5 block text-[13px] font-medium text-foreground";

/* Shared focus ring — brand hairline, no heavy box-shadow. */
const FOCUS =
  "focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand/60";

/* ── Button ───────────────────────────────────────────────────────────────
   Dashboard flavor (DESIGN §10.8): only CTAs/filters are pills; square marks
   data and destructive/neutral actions. Primary = the brand pill CTA.
   One height everywhere (h-8), taken from the create-slot sheet button. The
   old sm/md/lg ladder let a stray `size="lg"` make a page's primary action
   taller than the same action in a sheet, so the prop is gone — pass a
   className only when you mean a genuinely different shape, not a size. */
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "accent";
  loading?: boolean;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    loading,
    disabled,
    className,
    children,
    ...rest
  },
  ref,
) {
  const variants: Record<string, string> = {
    primary:
      "rounded-md bg-brand text-brand-foreground shadow-sm hover:bg-brand/90 active:brightness-95",
    secondary:
      "rounded-md border border-foreground/15 bg-card text-foreground hover:bg-foreground/[0.04] hover:border-foreground/25",
    danger:
      "rounded-md bg-danger text-white shadow-sm hover:bg-danger-hover active:brightness-95",
    ghost:
      "rounded-md text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground",
    accent:
      "rounded-md bg-accent text-accent-foreground hover:bg-accent-hover",
  };
  return (
    <button
      ref={ref}
      data-variant={variant}
      className={cx(
        "inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md px-3",
        "text-sm font-medium",
        "transition-colors duration-150",
        FOCUS,
        "disabled:opacity-40 disabled:cursor-not-allowed select-none",
        variants[variant],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && (
        <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </button>
  );
});

/* ── CategoryTabs ─────────────────────────────────────────────────────────
   The category switcher: a row of floating pills — no outer track. Active
   tab is the solid brand pill (§10.3), same language as the mobile top-nav
   chips. Counts ride along as sub-pills. Arrow keys move between tabs; the
   row scrolls horizontally on overflow instead of wrapping. */
export type CategoryTab<T extends string> = {
  value: T;
  label: string;
  count?: number;
};

type CategoryTabsProps<T extends string> = {
  tabs: CategoryTab<T>[];
  value: T;
  onChange: (value: T) => void;
  /** `pills` (default) is the floating chip switcher that sits above a table.
   *  `underline` is the quieter tab-bar form: no track and no full-width rule
   *  — only the active tab carries weight, and a brand underline marks it. */
  variant?: "pills" | "underline";
  className?: string;
};

export function CategoryTabs<T extends string>({
  tabs,
  value,
  onChange,
  variant = "pills",
  className,
}: CategoryTabsProps<T>) {
  const index = tabs.findIndex((t) => t.value === value);

  function move(next: number) {
    const t = tabs[Math.min(tabs.length - 1, Math.max(0, next))];
    if (t) onChange(t.value);
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      move(index + 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      move(index - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      move(0);
    } else if (e.key === "End") {
      e.preventDefault();
      move(tabs.length - 1);
    }
  }

  const underline = variant === "underline";

  return (
    <div
      role="tablist"
      onKeyDown={onKeyDown}
      className={cx(
        "no-scrollbar flex w-fit max-w-full items-center overflow-x-auto",
        underline ? "gap-1" : "gap-0.5 rounded-md p-0.5",
        className,
      )}
    >
      {tabs.map((t) => {
        const active = t.value === value;
        return (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active || index === -1 ? 0 : -1}
            onClick={() => onChange(t.value)}
            className={cx(
              "flex shrink-0 cursor-pointer items-center gap-1.5 whitespace-nowrap transition-colors duration-150",
              FOCUS,
              underline
                ? cx(
                    "h-8 border-b-2 px-3 text-[13px]",
                    active
                      ? "border-brand font-medium text-foreground"
                      : "border-transparent text-muted-foreground hover:border-foreground/20 hover:text-foreground",
                  )
                : cx(
                    "h-7 rounded-md px-2.5 text-[12px] font-medium",
                    active
                      ? "bg-foreground/[0.06] text-foreground"
                      : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
                  ),
            )}
          >
            {t.label}
            {t.count !== undefined && (
              <span
                className={cx(
                  "tabular-nums",
                  !underline &&
                    "inline-flex h-[17px] min-w-[17px] items-center justify-center rounded-full bg-foreground/10 px-1 text-[10px]",
                  active ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* ── Input ────────────────────────────────────────────────────────────────
   Hairline field: `border-foreground/20`, focus swaps to brand. Fills read
   flat (bg-card) so the hairline does the work. */
type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "size" | "prefix" | "suffix"> & {
  label?: string;
  /** `caps` (default) is the mono-caps field label. `sentence` swaps it for a
   *  calmer sentence-case label, for forms where caps would shout. */
  labelVariant?: "caps" | "sentence";
  hint?: string;
  error?: string;
  /** Leading adornment inside the field — a currency glyph, or a Search icon.
   *  `string` is the common case; ReactNode lets a call site drop in an icon
   *  without hand-rolling the positioning. */
  prefix?: ReactNode;
  suffix?: ReactNode;
  /** `sm` matches the CategoryTabs track height (38px) for filter rows. */
  size?: "md" | "sm";
  /** Interactive control inside the field, right-aligned (e.g. Show/Hide).
   *  Unlike `suffix` this stays clickable and is anchored to the input itself,
   *  so it never drifts when a hint or error appears below. */
  trailing?: ReactNode;
};

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, labelVariant = "caps", hint, error, className, id, prefix, suffix, trailing, size = "md", ...rest },
  ref,
) {
  return (
    <label className="block">
      {label && <span className={labelVariant === "sentence" ? LABEL_SENTENCE : LABEL}>{label}</span>}
      <div className="relative">
        {prefix && (
          <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{prefix}</span>
        )}
        <input
          ref={ref}
          id={id}
          className={cx(
            size === "sm"
              ? "h-8 w-full rounded-md border bg-transparent text-[12px] text-foreground"
              : "h-9 w-full rounded-md border bg-card text-sm text-foreground",
            "transition-colors duration-150",
            "placeholder:text-muted-foreground",
            !!prefix && "pl-8",
            !!suffix && "pr-9",
            !!trailing && "pr-14",
            !prefix && !suffix && !trailing && (size === "sm" ? "px-4" : "px-3.5"),
            // A trailing control reserves the right side; the free left side
            // keeps its default padding.
            !!trailing && !prefix && !suffix && (size === "sm" ? "pl-4" : "pl-3.5"),
            error
              ? "border-danger focus:border-danger focus:ring-2 focus:ring-danger/20"
              : "border-foreground/20 hover:border-foreground/35 focus:border-brand focus:ring-2 focus:ring-brand/20",
            "focus:outline-none",
            "disabled:opacity-40 disabled:cursor-not-allowed disabled:bg-foreground/[0.04]",
            className,
          )}
          {...rest}
        />
        {suffix && (
          <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">{suffix}</span>
        )}
        {trailing && (
          <span className="absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center">{trailing}</span>
        )}
      </div>
      {hint && !error && (
        <span className="mt-1.5 block truncate text-xs text-muted-foreground">{hint}</span>
      )}
      {error && (
        <span className="auth-field-error">
          <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
        </span>
      )}
    </label>
  );
});

/* ── Select ───────────────────────────────────────────────────────────────
   Custom listbox, not a native <select>: the OS menu can't be themed, so the
   open state looked generic HTML. Same props API as before (children are
   <option>s, onChange receives e.target.value) — call sites unchanged. The
   popup portals to <body> so scrolling dialogs and cards never clip it. */
type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "size" | "onChange"> & {
  label?: string;
  /** See `InputProps.labelVariant`. */
  labelVariant?: "caps" | "sentence";
  error?: string;
  /** `sm` matches the CategoryTabs track height (38px) for filter rows. */
  size?: "md" | "sm";
  onChange?: (e: { target: { value: string } }) => void;
};

type SelectOption = { value: string; label: string; disabled?: boolean };

export function Select({
  label,
  labelVariant = "caps",
  error,
  className,
  size = "md",
  children,
  value,
  onChange,
  disabled,
  id,
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<{ left: number; top?: number; bottom?: number; width: number } | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listboxId = useId();

  // Options arrive as <option> children — parse them once per render.
  const options: SelectOption[] = useMemo(() => {
    const out: SelectOption[] = [];
    Children.toArray(children).forEach((child) => {
      if (!isValidElement(child)) return;
      const p = child.props as { value?: string | number; children?: ReactNode; disabled?: boolean };
      const text = typeof p.children === "string" ? p.children : String(p.value ?? "");
      out.push({ value: String(p.value ?? ""), label: text, disabled: p.disabled });
    });
    return out;
  }, [children]);

  const selected = options.find((o) => o.value === String(value ?? ""));
  const selectedLabel = selected?.label ?? "Select…";

  // Keep the popup glued to the trigger through scrolls and resizes. When
  // there's no room below (select near the bottom of the viewport), flip it
  // open above the trigger instead.
  function syncRect() {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const POPUP_MAX = 288; // max-h-72
    const flip = r.bottom + POPUP_MAX > window.innerHeight && r.top > r.bottom;
    setRect(
      flip
        ? { left: r.left, bottom: window.innerHeight - r.top + 6, width: r.width }
        : { left: r.left, top: r.bottom + 6, width: r.width },
    );
  }

  useEffect(() => {
    if (!open) return;
    syncRect();
    const onDoc = (e: MouseEvent) => {
      const target = e.target as Node;
      // The popup portals to <body>, so it is NOT inside rootRef. Presses
      // inside it must be ignored: closing on mousedown would unmount the
      // option before mouseup/click could ever land on it, so choosing with
      // the mouse would silently do nothing.
      if (rootRef.current?.contains(target) || listRef.current?.contains(target)) return;
      setOpen(false);
    };
    window.addEventListener("resize", syncRect);
    window.addEventListener("scroll", syncRect, true);
    document.addEventListener("mousedown", onDoc);
    return () => {
      window.removeEventListener("resize", syncRect);
      window.removeEventListener("scroll", syncRect, true);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [open]);

  // Highlight the current selection when opening; scroll it into view.
  function openMenu() {
    setActive(Math.max(0, options.findIndex((o) => o.value === String(value ?? ""))));
    setOpen(true);
    requestAnimationFrame(() => {
      const i = Math.max(0, options.findIndex((o) => o.value === String(value ?? "")));
      listRef.current?.children[i]?.scrollIntoView({ block: "nearest" });
    });
  }

  function choose(o: SelectOption) {
    if (o.disabled) return;
    onChange?.({ target: { value: o.value } });
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>) {
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openMenu();
      }
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(options.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(options.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(options[active]);
    }
  }

  const triggerBase =
    size === "sm"
      ? "h-8 w-full rounded-md border border-foreground/20 bg-transparent pl-3 pr-8 text-[12px] text-foreground hover:border-foreground/35"
      : "h-9 w-full rounded-md border border-foreground/20 bg-card pl-3 pr-9 text-sm text-foreground hover:border-foreground/35";

  return (
    <label className="block" htmlFor={id}>
      {label && <span className={labelVariant === "sentence" ? LABEL_SENTENCE : LABEL}>{label}</span>}
      <div ref={rootRef} className="relative">
        <button
          ref={triggerRef}
          type="button"
          id={id}
          role="combobox"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listboxId}
          disabled={disabled}
          onClick={() => (open ? setOpen(false) : openMenu())}
          onKeyDown={onKeyDown}
          className={cx(
            "relative flex cursor-pointer items-center text-left",
            "transition duration-150",
            triggerBase,
            error
              ? "border-danger focus-visible:border-danger"
              : "focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/20",
            "focus-visible:outline-none",
            "disabled:opacity-40 disabled:cursor-not-allowed",
            className,
          )}
        >
          <span className="min-w-0 truncate">{selectedLabel}</span>
          <svg
            className={`pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground transition-transform duration-150 ${open ? "rotate-180" : ""}`}
            viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        {open &&
          rect &&
          createPortal(
            <ul
              ref={listRef}
              id={listboxId}
              role="listbox"
              aria-label={label}
              style={{ left: rect.left, top: rect.top, bottom: rect.bottom, width: rect.width }}
              className="fixed z-[100] max-h-72 animate-pop-in overflow-y-auto overscroll-contain rounded-lg border border-[var(--border)] bg-popover p-1 shadow-lg shadow-black/10"
            >
              {options.map((o, i) => {
                const isSelected = o.value === String(value ?? "");
                const isActive = i === active;
                return (
                  <li
                    key={o.value}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={o.disabled}
                    onClick={() => choose(o)}
                    onMouseEnter={() => setActive(i)}
                    className={cx(
                      "flex min-h-8 cursor-pointer items-center justify-between gap-2.5 rounded-md px-2.5 text-[12px] transition-colors",
                      o.disabled && "cursor-not-allowed opacity-40",
                      isSelected
                        ? "bg-foreground/[0.06] font-medium text-foreground"
                        : isActive
                          ? "bg-foreground/5 text-foreground"
                          : "text-foreground",
                    )}
                  >
                    <span className="min-w-0 truncate">{o.label}</span>
                    {isSelected && (
                      <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </li>
                );
              })}
            </ul>,
            document.body,
          )}
      </div>
      {error && (
        <span className="auth-field-error">
          <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
          {error}
        </span>
      )}
    </label>
  );
}

/* ── Textarea ───────────────────────────────────────────────────────────── */
type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label?: string;
  /** See `InputProps.labelVariant`. */
  labelVariant?: "caps" | "sentence";
  error?: string;
};

export function Textarea({ label, labelVariant = "caps", error, className, ...rest }: TextareaProps) {
  return (
    <label className="block">
      {label && <span className={labelVariant === "sentence" ? LABEL_SENTENCE : LABEL}>{label}</span>}
      <textarea
        className={cx(
          "w-full rounded-md border border-foreground/20 bg-card px-3 py-2 text-sm text-foreground hover:border-foreground/35",
          "transition-all duration-150",
          error
            ? "border-danger focus:border-danger focus:ring-2 focus:ring-danger/20"
            : "focus:border-brand focus:ring-2 focus:ring-brand/20",
          "placeholder:text-muted-foreground focus:outline-none",
          className,
        )}
        {...rest}
      />
      {error && (
        <span className="auth-field-error">
          <svg className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
          {error}
        </span>
      )}
    </label>
  );
}

/* ── Card (hairline panel, square-ish via the global radius scale) ─────── */
export function Card({ children, className, hover = false }: { children: ReactNode; className?: string; hover?: boolean }) {
  return (
    <div
      className={cx(
        "rounded-md border border-foreground/10 bg-card",
        hover && "transition-colors duration-150 hover:border-foreground/25",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 border-b border-foreground/10 px-5 py-3.5">
      <div className="min-w-0">
        <h3 className="text-[14px] font-semibold leading-tight text-foreground">{title}</h3>
        {subtitle && <p className="mt-0.5 text-[12px] text-muted-foreground">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/* ── TableToolbar (label row floating above a table card) ─────────────────
   Same title/subtitle/action shape as CardHeader, but rendered OUTSIDE the
   Card: no background, no border, no bottom hairline. The title and its
   filters stay on the page background so only the table carries the panel
   surface. Use this when the list below is the thing that should read as a
   discrete card; keep CardHeader when the header belongs to the panel. */
export function TableToolbar({
  title,
  subtitle,
  action,
  className,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("mb-3 flex flex-wrap items-center justify-between gap-4", className)}>
      <div className="min-w-0">
        <h3 className="text-[14px] font-semibold leading-tight text-foreground">{title}</h3>
        {subtitle && <p className="mt-0.5 text-[12px] text-muted-foreground">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

/* ── Badge (bordered mono capsule — DESIGN §6.4 cell status) ───────────── */
export function Badge({
  tone = "neutral",
  children,
  size = "md",
}: {
  tone?: "neutral" | "success" | "danger" | "warning" | "info";
  children: ReactNode;
  size?: "sm" | "md";
}) {
  const tones: Record<string, string> = {
    neutral: "bg-foreground/[0.06] text-muted-foreground",
    success: "bg-success-bg text-success",
    danger: "bg-danger-bg text-danger",
    warning: "bg-warning-bg text-warning",
    info: "bg-info-bg text-info",
  };
  const sizes: Record<string, string> = {
    sm: "px-1.5 py-0.5 text-[10px]",
    md: "px-2 py-0.5 text-[11px]",
  };
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-md font-medium leading-tight", sizes[size], tones[tone])}>
      {children}
    </span>
  );
}

/* ── Alert ──────────────────────────────────────────────────────────────── */
export function Alert({ tone = "danger", children, onDismiss }: { tone?: "danger" | "success" | "warning" | "info"; children: ReactNode; onDismiss?: () => void }) {
  if (!children) return null;
  const tones: Record<string, string> = {
    danger: "bg-danger-bg text-danger border-danger-border",
    success: "bg-success-bg text-success border-success-border",
    warning: "bg-warning-bg text-warning border-warning-border",
    info: "bg-info-bg text-info border-info-border",
  };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex items-start gap-3 rounded-md border px-4 py-3 text-sm", tones[tone])}>
      <span className="flex-1">{children}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="shrink-0 rounded p-0.5 opacity-60 hover:opacity-100 transition-opacity" aria-label="Dismiss">
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
        </button>
      )}
    </div>
  );
}

/* ── Spinner ────────────────────────────────────────────────────────────── */
export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <div className="h-8 w-8 rounded-full border-[3px] border-foreground/15 border-t-foreground animate-spin" />
      {label && <p className="text-sm text-muted-foreground">{label}</p>}
    </div>
  );
}

/* ── EmptyState (flat callout — sits inside the table surface, no outline) ── */
const EMPTY_ICON_PATHS = {
  search: "M21 21l-4.35-4.35m1.35-5.4a6.75 6.75 0 11-13.5 0 6.75 6.75 0 0113.5 0z",
  person: "M12 11.25a3.75 3.75 0 100-7.5 3.75 3.75 0 000 7.5zM4.5 20.25a7.5 7.5 0 0115 0",
  people: "M16.5 20.25a6 6 0 00-12 0m12-12a3 3 0 11-6 0 3 3 0 016 0zm2.25 5.25a4.5 4.5 0 014.5 4.5M18.75 5.5a2.75 2.75 0 010 5.5",
  plan: "M9 4.5H6.75A2.25 2.25 0 004.5 6.75v12a2.25 2.25 0 002.25 2.25h10.5a2.25 2.25 0 002.25-2.25v-12A2.25 2.25 0 0017.25 4.5H15M9 4.5a2.25 2.25 0 004.5 0M9 4.5a2.25 2.25 0 014.5 0M8.25 12h7.5m-7.5 3.75h5.25",
  money: "M3 7.5h18v9H3v-9zm9 7.5a3 3 0 100-6 3 3 0 000 6zM6 4.5h12M6 19.5h12",
  calendar: "M7.5 3v3m9-3v3M3.75 9h16.5M6 5.25h12a2.25 2.25 0 012.25 2.25v11.25A2.25 2.25 0 0118 21H6a2.25 2.25 0 01-2.25-2.25V7.5A2.25 2.25 0 016 5.25z",
  message: "M20.25 11.25a8.25 8.25 0 01-8.25 8.25 8.4 8.4 0 01-3.42-.72L3.75 20.25l1.47-4.83A8.25 8.25 0 1120.25 11.25z",
  check: "M9 12.75l2.25 2.25L15.75 9M12 21a9 9 0 110-18 9 9 0 010 18z",
  building: "M3.75 21h16.5M5.25 21V4.5h13.5V21M9 8.25h1.5m3 0H15M9 12h1.5m3 0H15M9 15.75h1.5m3 0H15",
  door: "M5.25 21V3.75h12V21M3.75 21h15m-4.5-9h.75",
  locker: "M5.25 3.75h13.5v16.5H5.25V3.75zm6.75 0v16.5m-3-9h.75m4.5 0H15",
} as const;

function EmptyStateGlyph({ title, hint = "" }: { title: string; hint?: string }) {
  const subject = title.toLowerCase();
  const kind = /match|search|filter/.test(subject) ? "search"
    : /lead|prospect/.test(subject) ? "person"
    : /referral|member|staff|seat-holder|student|people|client/.test(subject) ? "people"
    : /payment|cash|receipt|invoice|payroll|billing|transaction/.test(subject) ? "money"
    : /plan|offer|contract|subscription/.test(subject) ? "plan"
    : /locker/.test(subject) ? "locker"
    : /space|company|companies/.test(subject) ? "building"
    : /visitor|desk|walk-in/.test(subject) ? "door"
    : /class|booking|slot|attendance|check-in|tour|shift/.test(subject) ? "calendar"
    : /inbox|message|conversation/.test(subject) ? "message"
    : /approval|task|audit|queue|clear|entry|entries|event/.test(subject) ? "check"
    : /payment|receipt/.test(hint.toLowerCase()) ? "money"
    : "plan";
  return (
    <svg className="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={EMPTY_ICON_PATHS[kind]} />
    </svg>
  );
}

export function EmptyState({ title, hint, icon, action }: { title: string; hint?: string; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 flex h-8 w-8 items-center justify-center text-muted-foreground [&_svg]:h-7 [&_svg]:w-7" aria-hidden="true">
        {icon ?? <EmptyStateGlyph title={title} hint={hint} />}
      </div>
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {hint && <p className="mt-1 max-w-xs text-sm text-muted-foreground">{hint}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/* ── Separator ──────────────────────────────────────────────────────────── */
export function Separator({ className }: { className?: string }) {
  return <hr className={cx("border-0 border-t border-foreground/10", className)} />;
}

/* ── Avatar (neutral hairline tile — names stay in the sans column) ────── */
export function Avatar({ name, size = "md", className, photoUrl }: { name: string; size?: "sm" | "md" | "lg"; className?: string; photoUrl?: string | null }) {
  const initials = name.split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const sizes: Record<string, string> = {
    sm: "h-8 w-8 text-[10px]",
    md: "h-10 w-10 text-xs",
    lg: "h-12 w-12 text-sm",
  };
  return (
    <div
      className={cx(
        "inline-flex items-center justify-center overflow-hidden rounded-full border border-foreground/10 bg-foreground/[0.05] font-medium tracking-wide text-foreground",
        sizes[size],
        className,
      )}
      title={name}
    >
      {photoUrl ? <img src={photoUrl} alt={name} loading="lazy" referrerPolicy="no-referrer" className="h-full w-full object-cover" /> : initials}
    </div>
  );
}

/* ── StatCard (Notion-ish tile — sans label, semibold value) ───────────── */
export function StatCard({
  label,
  value,
  icon,
  trend,
  trendValue,
  accent = false,
  hint,
  joined = false,
  className,
}: {
  label: string;
  value: string;
  icon?: ReactNode;
  trend?: "up" | "down" | "neutral";
  trendValue?: string;
  accent?: boolean;
  hint?: string;
  /** Drop the card's own border/radius so it can sit inside a joined grid
   *  whose cells are separated by hairline gaps. */
  joined?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "p-4 sm:p-5",
        joined
          ? accent
            ? "bg-[color-mix(in_oklab,var(--brand)_6%,var(--card))]"
            : "bg-card"
          : accent
            ? "rounded-lg border border-brand/40 bg-brand/[0.04]"
            : "rounded-lg border border-foreground/10",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="mb-1.5 text-[12px] font-medium text-muted-foreground">{label}</p>
          <p className="text-[22px] font-semibold leading-none tracking-tight tabular-nums text-foreground">{value}</p>
          {hint && <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p>}
          {trendValue && (
            <div className="mt-2.5 flex items-center gap-1 text-xs">
              {trend === "up" && <span className="text-success">↑</span>}
              {trend === "down" && <span className="text-danger">↓</span>}
              <span className={cx(
                trend === "up" && "text-success",
                trend === "down" && "text-danger",
                trend === "neutral" && "text-muted-foreground",
              )}>{trendValue}</span>
            </div>
          )}
        </div>
        {icon && (
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-foreground/10 text-muted-foreground">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
