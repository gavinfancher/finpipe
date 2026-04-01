import { useState, useEffect, useRef, useCallback } from "react";
import { API_BASE } from "../config";

/**
 * Syncs a preferences object to the server. Loads on mount, debounce-saves on change.
 * Falls back to localStorage if server is unavailable.
 */
export function usePreferences(token: string) {
  const [prefs, setPrefs] = useState<Record<string, unknown>>({});
  const [loaded, setLoaded] = useState(false);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestPrefs = useRef(prefs);
  latestPrefs.current = prefs;

  // Load from server on mount
  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/external/preferences`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          if (data && typeof data === "object") {
            setPrefs(data);
          }
        }
      } catch {
        // Server unavailable — try localStorage fallback
        try {
          const saved = localStorage.getItem("finpipe-prefs");
          if (saved) setPrefs(JSON.parse(saved));
        } catch { /* empty */ }
      }
      setLoaded(true);
    })();
  }, [token]);

  // Debounced save to server + localStorage
  const save = useCallback((next: Record<string, unknown>) => {
    setPrefs(next);
    localStorage.setItem("finpipe-prefs", JSON.stringify(next));

    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try {
        await fetch(`${API_BASE}/external/preferences`, {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(next),
        });
      } catch { /* silent */ }
    }, 1000);
  }, [token]);

  const update = useCallback((key: string, value: unknown) => {
    save({ ...latestPrefs.current, [key]: value });
  }, [save]);

  return { prefs, loaded, update };
}
