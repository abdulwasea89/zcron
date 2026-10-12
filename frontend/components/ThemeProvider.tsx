"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";
import { THEME_VALUES } from "@/lib/themes";

// Thin wrapper so the root (server) layout can mount next-themes without itself
// becoming a client component. Toggles a `.notion` class on <html> by default
// (the shipped, Notion-like light theme); the rest of the set is available.
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="notion"
      enableSystem
      themes={THEME_VALUES}
      disableTransitionOnChange
      enableColorScheme={false}
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}
