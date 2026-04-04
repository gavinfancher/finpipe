import { useState, useEffect, useCallback } from "react";
import { API_BASE } from "../config";

export type MarketSession = "pre-market" | "open" | "post-market" | "closed";

export interface MarketStatus {
  session: MarketSession;
  isHoliday: boolean;
  holidayName: string | null;
  nextOpen: number;   // unix seconds
  nextClose: number;  // unix seconds
}

const DOT_CLASS: Record<MarketSession, string> = {
  "pre-market": "dot--yellow",
  "open": "dot--green",
  "post-market": "dot--purple",
  "closed": "dot--red",
};

const LABEL: Record<MarketSession, string> = {
  "pre-market": "pre-market",
  "open": "market open",
  "post-market": "post-market",
  "closed": "off hours",
};

export function useMarketStatus() {
  const [status, setStatus] = useState<MarketStatus | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/external/market/status`);
      if (!res.ok) return;
      const data = await res.json();
      setStatus({
        session: data.session,
        isHoliday: data.is_holiday,
        holidayName: data.holiday_name,
        nextOpen: data.next_open,
        nextClose: data.next_close,
      });
    } catch { /* ignore fetch errors */ }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 30_000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const session = status?.session ?? "closed";

  return {
    status,
    session,
    label: status?.isHoliday && status.holidayName
      ? status.holidayName.toLowerCase()
      : LABEL[session],
    dotClass: DOT_CLASS[session],
  };
}

export function useCountdown(targetUnix: number | null): number | null {
  const [seconds, setSeconds] = useState<number | null>(null);

  useEffect(() => {
    if (targetUnix === null) { setSeconds(null); return; }

    function tick() {
      const diff = targetUnix! - Math.floor(Date.now() / 1000);
      setSeconds(diff > 0 ? diff : 0);
    }
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [targetUnix]);

  return seconds;
}

export function formatCountdown(totalSecs: number): string {
  const h = Math.floor(totalSecs / 3600);
  const m = Math.floor((totalSecs % 3600) / 60);
  const s = totalSecs % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}
