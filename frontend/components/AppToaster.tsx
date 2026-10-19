"use client";

import { Toaster } from "sonner";
import { useTheme } from "next-themes";

const DARK_THEMES = new Set(["dark", "notion-dark", "chatgpt", "helix", "midnight", "oled"]);

export function AppToaster() {
  const { resolvedTheme } = useTheme();
  const theme = resolvedTheme && DARK_THEMES.has(resolvedTheme) ? "dark" : "light";

  return (
    <Toaster
      position="bottom-right"
      theme={theme}
      richColors
      closeButton
      visibleToasts={4}
      toastOptions={{
        classNames: {
          toast: "border border-[var(--border)] shadow-xl",
          title: "font-medium",
          description: "text-sm",
        },
      }}
    />
  );
}
