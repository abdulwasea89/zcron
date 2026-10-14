"use client";

import type { KeyboardEventHandler, ReactNode, Ref } from "react";
import { CategoryTabs, Input, type CategoryTab } from "@/components/ui";
import { Glyph } from "@/components/Glyph";

/* ── ListToolbar ──────────────────────────────────────────────────────────
   The toolbar above a list page: quiet underline tabs on the left, search on
   the right — the same layout the plans page established. Pages pass their own
   tabs and search state; an optional `children` slot renders extra filters
   just left of the search field. The placement and styling live here so every
   list page matches. */

export function ListToolbar<T extends string>({
  tabs,
  value,
  onChange,
  search,
  onSearch,
  searchPlaceholder,
  searchRef,
  onSearchKeyDown,
  children,
  hideSearch = false,
}: {
  tabs: CategoryTab<T>[];
  value: T;
  onChange: (value: T) => void;
  search: string;
  onSearch: (value: string) => void;
  searchPlaceholder: string;
  searchRef?: Ref<HTMLInputElement>;
  onSearchKeyDown?: KeyboardEventHandler<HTMLInputElement>;
  /** Extra filters, placed left of the search field. */
  children?: ReactNode;
  hideSearch?: boolean;
}) {
  return (
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
      <CategoryTabs variant="underline" tabs={tabs} value={value} onChange={onChange} />
      {!hideSearch && <div className="flex flex-wrap items-center justify-end gap-2">
        {children}
        <Input
          ref={searchRef}
          onKeyDown={onSearchKeyDown}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          prefix={
            <Glyph className="h-3.5 w-3.5">
              <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
            </Glyph>
          }
          className="w-full sm:w-[280px]"
        />
      </div>}
    </div>
  );
}

