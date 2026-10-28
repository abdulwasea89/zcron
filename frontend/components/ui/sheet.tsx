"use client"

import * as React from "react"
import * as SheetPrimitive from "@radix-ui/react-dialog"

function cn(...inputs: (string | false | null | undefined)[]) {
  return inputs.filter(Boolean).join(" ")
}

/* ── Sheet ────────────────────────────────────────────────────────────────
   An edge-anchored panel for tasks that belong *beside* the page rather than
   in front of it. The create/edit plan form is the case: it is long, it is
   about the table you are looking at, and a centred modal blanked the table
   out for no reason. A sheet keeps the workspace in view.

   Three regions, and the content is a flex column so they behave:
     header  fixed height, never scrolls
     body    `flex-1 min-h-0 overflow-y-auto` — the only scrolling region
     footer  fixed, always on screen

   The `min-h-0` on the body is load-bearing. A flex child defaults to
   `min-height: auto`, which refuses to shrink below its content, so without it
   the body grows past the sheet and pushes the footer off the bottom edge —
   exactly the failure the footer is meant to prevent.

   The scrim is deliberately lighter than Dialog's (which is black/40 + blur):
   the point of a sheet is that you can still see and read the page behind it. */

const Sheet = SheetPrimitive.Root
const SheetTrigger = SheetPrimitive.Trigger
const SheetClose = SheetPrimitive.Close
const SheetPortal = SheetPrimitive.Portal

const SheetOverlay = React.forwardRef<
  React.ComponentRef<typeof SheetPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof SheetPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <SheetPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/25 data-[state=closed]:pointer-events-none data-[state=closed]:invisible",
      "data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out",
      className,
    )}
    {...props}
  />
))
SheetOverlay.displayName = SheetPrimitive.Overlay.displayName

const SIDES = {
  right: {
    placement: "inset-y-0 right-0 h-full border-l",
    motion: "data-[state=open]:animate-sheet-in-right data-[state=closed]:animate-sheet-out-right",
  },
  left: {
    placement: "inset-y-0 left-0 h-full border-r",
    motion: "data-[state=open]:animate-sheet-in-left data-[state=closed]:animate-sheet-out-left",
  },
} as const

const SheetContent = React.forwardRef<
  React.ComponentRef<typeof SheetPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SheetPrimitive.Content> & {
    side?: keyof typeof SIDES
  }
>(({ className, children, side = "right", ...props }, ref) => {
  const { placement, motion } = SIDES[side]
  return (
    <SheetPortal forceMount>
      <SheetOverlay />
      <SheetPrimitive.Content
        ref={ref}
        forceMount
        className={cn(
          "fixed z-50 flex w-full flex-col border-[var(--border)] bg-card shadow-2xl shadow-black/25 data-[state=closed]:pointer-events-none data-[state=closed]:invisible",
          placement,
          motion,
          // Callers widen the panel by setting `--sheet-max-w` (e.g. the view
          // sheet's expand toggle); the 480px default is the create/edit width.
          "sm:max-w-[var(--sheet-max-w,480px)]",
          className,
        )}
        {...props}
      >
        {children}
      </SheetPrimitive.Content>
    </SheetPortal>
  )
})
SheetContent.displayName = SheetPrimitive.Content.displayName

const SheetHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("shrink-0 border-b border-[var(--border)] px-6 py-5", className)} {...props} />
))
SheetHeader.displayName = "SheetHeader"

/** The only scrolling region in a Sheet. */
const SheetBody = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("min-h-0 flex-1 overflow-y-auto px-6 py-5", className)} {...props} />
))
SheetBody.displayName = "SheetBody"

const SheetFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  // `mt-auto` keeps it pinned to the bottom when the body is shorter than the
  // sheet, so the buttons do not float mid-panel.
  <div
    ref={ref}
    className={cn("mt-auto flex shrink-0 items-center justify-end gap-2 border-t border-[var(--border)] px-6 py-4", className)}
    {...props}
  />
))
SheetFooter.displayName = "SheetFooter"

const SheetTitle = React.forwardRef<
  React.ComponentRef<typeof SheetPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof SheetPrimitive.Title>
>(({ className, ...props }, ref) => (
  <SheetPrimitive.Title
    ref={ref}
    className={cn("text-[14px] font-semibold leading-tight text-foreground", className)}
    {...props}
  />
))
SheetTitle.displayName = SheetPrimitive.Title.displayName

const SheetDescription = React.forwardRef<
  React.ComponentRef<typeof SheetPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof SheetPrimitive.Description>
>(({ className, ...props }, ref) => (
  <SheetPrimitive.Description
    ref={ref}
    className={cn("mt-1 text-[12px] text-muted-foreground", className)}
    {...props}
  />
))
SheetDescription.displayName = SheetPrimitive.Description.displayName

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetPortal,
  SheetOverlay,
  SheetContent,
  SheetHeader,
  SheetBody,
  SheetFooter,
  SheetTitle,
  SheetDescription,
}
