import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { StockTick } from "../types";

export type WLColKey = "price" | "change" | "changePct" | "perf5d" | "perf1m" | "perf3m" | "perf6m" | "perfYtd" | "perf1y" | "perf3y" | "volume";

function formatVol(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toString();
}

function fmtPct(v: number): string {
  const abs = Math.abs(v);
  const sign = v >= 0 ? "+" : "\u2212";
  if (abs >= 1000) return sign + (abs / 1000).toFixed(2) + "k";
  const d = abs >= 100 ? 1 : abs >= 10 ? 2 : 3;
  return sign + abs.toFixed(d);
}

interface Props {
  ticker: string;
  tick?: StockTick;
  prevPrice?: number;
  visibleCols: WLColKey[];
  onRemove: () => void;
}

interface DropdownPos { top: number; right: number; }

export default function TickerRow({ ticker, tick, prevPrice, visibleCols, onRemove }: Props) {
  const up = (tick?.changePct ?? 0) >= 0;
  const priceFlashClass =
    tick && prevPrice !== undefined && prevPrice !== tick.price
      ? tick.price > prevPrice ? "price-flash-up" : "price-flash-down"
      : "";

  const [dropdownPos, setDropdownPos] = useState<DropdownPos | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!dropdownPos) return;
    function close() { setDropdownPos(null); }
    document.addEventListener("pointerdown", close);
    document.addEventListener("scroll", close, true);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("scroll", close, true);
    };
  }, [dropdownPos]);

  function openMenu(e: React.MouseEvent) {
    e.stopPropagation();
    if (dropdownPos) { setDropdownPos(null); return; }
    const rect = triggerRef.current!.getBoundingClientRect();
    setDropdownPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
  }

  function renderCell(key: WLColKey) {
    const green = "var(--green)", red = "var(--red)", muted = "var(--text-muted)";
    if (!tick) return <span style={{ color: muted }}>—</span>;
    switch (key) {
      case "price":
        return <span className={priceFlashClass}>${tick.price.toFixed(2)}</span>;
      case "change": {
        const c = up ? green : red;
        return <span style={{ color: c }}>{`${up ? "+" : ""}${tick.change.toFixed(2)}`}</span>;
      }
      case "changePct": {
        const c = up ? green : red;
        return <span style={{ color: c }}>{`${fmtPct(tick.changePct)}%`}</span>;
      }
      case "volume":
        return tick.volume != null ? <>{formatVol(tick.volume)}</> : <span style={{ color: muted }}>—</span>;
      default: {
        const val = (tick as unknown as Record<string, number | undefined>)[key];
        if (val == null) return <span style={{ color: muted }}>—</span>;
        const c = val >= 0 ? green : red;
        return <span style={{ color: c }}>{`${fmtPct(val)}%`}</span>;
      }
    }
  }

  return (
    <tr className="ticker-row">
      <td className="cell cell--ticker">{ticker}</td>
      {visibleCols.map((key) => (
        <td key={key} className="cell cell--num">{renderCell(key)}</td>
      ))}
      <td className="cell cell--action">
        <button ref={triggerRef} className="row-menu-trigger" onClick={openMenu} aria-label="row options">⋮</button>
        {dropdownPos && createPortal(
          <div className="row-menu-dropdown" style={{ position: "fixed", top: dropdownPos.top, right: dropdownPos.right }} onPointerDown={(e) => e.stopPropagation()}>
            <button className="row-menu-item row-menu-item--danger" onClick={() => { setDropdownPos(null); onRemove(); }}>
              remove from watchlist
            </button>
          </div>,
          document.body
        )}
      </td>
    </tr>
  );
}
