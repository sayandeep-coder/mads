"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "mads_theme";

export type Theme = "dark" | "light";

/** Dark is the default look (see globals.css's :root); "light" opts into
 * the data-theme="light" override. Persisted per-browser. */
export function useTheme(): [Theme, (theme: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "light" || saved === "dark") {
        setThemeState(saved);
        document.documentElement.setAttribute("data-theme", saved);
      }
    } catch {
      // Private/locked-down context — default dark theme is a fine fallback.
    }
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not worth surfacing — the toggle still works for this tab.
    }
  }, []);

  return [theme, setTheme];
}
