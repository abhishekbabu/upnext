import { useCallback, useEffect, useState } from "react";

type Mode = "light" | "dark";

const MODE_STORAGE_KEY = "upnext:mode";

/** What the pre-paint script in index.html already put on <html>. */
function currentMode(): Mode {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/**
 * Storage throws rather than returning null in some contexts — a private
 * window, or a browser set to block site data. A theme preference is a
 * convenience, so failing to read or write one must never take the page down.
 */
function safeRead(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeWrite(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* preference simply will not persist */
  }
}

function apply(mode: Mode): void {
  document.documentElement.classList.toggle("dark", mode === "dark");
}

export function useTheme() {
  const [mode, setModeState] = useState<Mode>(currentMode);

  const setMode = useCallback((next: Mode) => {
    apply(next);
    setModeState(next);
    safeWrite(MODE_STORAGE_KEY, next);
  }, []);

  // Follow the OS only while the user has expressed no preference of their own,
  // which they can do at any point after the page loads.
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => {
      if (safeRead(MODE_STORAGE_KEY)) return;
      const next = e.matches ? "dark" : "light";
      apply(next);
      setModeState(next);
    };
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return { mode, setMode };
}
