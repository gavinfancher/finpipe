import { useState, useEffect } from "react";

/**
 * Returns seconds until next market open (09:30 ET), or null if market is open.
 * Handles weekends: Saturday → Monday, Sunday → Monday.
 */
export function useMarketCountdown(): number | null {
  const [seconds, setSeconds] = useState<number | null>(getSecondsUntilOpen);

  useEffect(() => {
    const id = setInterval(() => setSeconds(getSecondsUntilOpen()), 1000);
    return () => clearInterval(id);
  }, []);

  return seconds;
}

function getSecondsUntilOpen(): number | null {
  const now = new Date();

  // Get current ET components
  const etParts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(now);

  const get = (type: string) => Number(etParts.find((p) => p.type === type)!.value);
  const etH = get("hour");
  const etM = get("minute");
  const etS = get("second");
  const etMins = etH * 60 + etM;

  // Trading hours: 04:00 - 20:00 ET (pre-market through post-market)
  const etDow = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
  }).format(now);

  if (etMins >= 4 * 60 && etMins < 20 * 60 && !["Sat", "Sun"].includes(etDow)) {
    return null;
  }

  // Calculate seconds until next 04:00 ET (pre-market open)
  const openMins = 4 * 60;

  let daysToAdd = 0;

  if (etDow === "Sat") {
    daysToAdd = 2;
  } else if (etDow === "Sun") {
    daysToAdd = 1;
  } else if (etDow === "Fri" && etMins >= 20 * 60) {
    daysToAdd = 3;
  } else if (etMins >= 20 * 60) {
    daysToAdd = 1;
  }
  // else: today before 04:00, daysToAdd = 0

  const secsLeftToday = (openMins - etMins) * 60 - etS;

  if (daysToAdd === 0) {
    return Math.max(0, secsLeftToday);
  }

  const secsToMidnight = (24 * 60 - etMins) * 60 - etS;
  const secsFromMidnightToOpen = openMins * 60;
  return secsToMidnight + (daysToAdd - 1) * 86400 + secsFromMidnightToOpen;
}

export function formatCountdown(totalSecs: number): string {
  const h = Math.floor(totalSecs / 3600);
  const m = Math.floor((totalSecs % 3600) / 60);
  const s = totalSecs % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}
