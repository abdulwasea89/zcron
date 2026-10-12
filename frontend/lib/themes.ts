/** The same choices appear in the sidebar switcher and Settings. */
export const THEME_OPTIONS = [
  { value: "system", label: "System", swatch: "conic-gradient(from 90deg, #fafafa, #1a1a1a)" },
  { value: "notion", label: "Notion Light", swatch: "linear-gradient(135deg, #ffffff 40%, #2383e2)" },
  { value: "notion-dark", label: "Notion Dark", swatch: "linear-gradient(135deg, #191919 55%, #4d9cf7)" },
  { value: "chatgpt", label: "ChatGPT Dark", swatch: "linear-gradient(135deg, #0b0b0b 55%, #a376ed)" },
  { value: "helix", label: "Helix", swatch: "linear-gradient(135deg, #181411 55%, #ff6a00)" },
  { value: "light", label: "Light", swatch: "#faf7f2" },
  { value: "midnight", label: "Midnight", swatch: "oklch(0.16 0.012 165)" },
  { value: "dark", label: "Dark", swatch: "oklch(0.17 0.006 90)" },
  { value: "solarized", label: "Solarized", swatch: "#fdf6e3" },
  { value: "oled", label: "OLED", swatch: "#000000" },
] as const;

export const THEME_VALUES = THEME_OPTIONS.filter((option) => option.value !== "system").map((option) => option.value);
