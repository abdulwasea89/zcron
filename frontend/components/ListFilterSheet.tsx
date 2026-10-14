"use client";

import type { ReactNode } from "react";
import { Button } from "@/components/ui";
import {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

export function ListFilterSheet({
  title,
  description,
  activeCount,
  resultCount,
  onClear,
  children,
}: {
  title: string;
  description: string;
  activeCount: number;
  resultCount: number;
  onClear: () => void;
  children: ReactNode;
}) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button type="button" variant={activeCount ? "secondary" : "ghost"}>
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 7h9m4 0h3M4 17h3m4 0h9" /><circle cx="15" cy="7" r="2" /><circle cx="9" cy="17" r="2" />
          </svg>
          Filters{activeCount ? ` · ${activeCount}` : ""}
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="sm:max-w-[420px]">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        <SheetBody className="space-y-5">
          <div className="flex items-center justify-between rounded-md border border-[var(--border)] bg-background/40 px-3 py-2.5">
            <span className="text-sm text-foreground">Matching records</span>
            <span className="text-sm font-semibold tabular-nums text-[var(--primary)]">{resultCount}</span>
          </div>
          {children}
        </SheetBody>
        <SheetFooter className="justify-between">
          <span className="text-xs text-muted-foreground">{activeCount ? `${activeCount} active` : "No filters applied"}</span>
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" onClick={onClear} disabled={!activeCount}>Clear all</Button>
            <SheetClose asChild><Button type="button">Done</Button></SheetClose>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
