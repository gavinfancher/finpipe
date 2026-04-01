import { useState, useEffect, useRef } from "react";
import { API_BASE } from "../config";

export type BackendStatus = "checking" | "up" | "down";

export function useBackendStatus(interval = 30000) {
  const [status, setStatus] = useState<BackendStatus>("checking");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;

    async function check() {
      try {
        const res = await fetch(`${API_BASE}/external/health`, {
          signal: AbortSignal.timeout(5000),
        });
        if (!mounted.current) return;
        setStatus(res.ok ? "up" : "down");
      } catch {
        if (!mounted.current) return;
        setStatus("down");
      }
    }

    check();
    const id = setInterval(check, interval);
    return () => { mounted.current = false; clearInterval(id); };
  }, [interval]);

  return status;
}
