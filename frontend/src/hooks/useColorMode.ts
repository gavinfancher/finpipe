import { useState, useEffect } from "react";

type Mode = "dark" | "light";

const STORAGE_KEY = "finpipe-color-mode";

function getInitialMode(): Mode {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return "dark";
}

export function useColorMode() {
  const [mode, setMode] = useState<Mode>(getInitialMode);

  useEffect(() => {
    document.documentElement.setAttribute("data-mode", mode);
    localStorage.setItem(STORAGE_KEY, mode);
  }, [mode]);

  function toggle() {
    setMode((m) => (m === "dark" ? "light" : "dark"));
  }

  return { mode, toggle };
}
