import { useState, useEffect, useRef, useCallback, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useStockWebSocket } from "../hooks/useStockWebSocket";
import { useMarketStatus, useCountdown, formatCountdown } from "../hooks/useMarketStatus";
import { usePreferences } from "../hooks/usePreferences";
import { getToken } from "../store/userStore";
import TickerRow, { type WLColKey } from "../components/TickerRow";
import PositionsTab from "../components/PositionsTab";
import NavBar from "../components/NavBar";
import { API_BASE, WS_BASE } from "../config";

interface WLCol { key: WLColKey; label: string; visible: boolean; sortable: boolean; }

const DEFAULT_WL_COLS: WLCol[] = [
  { key: "price",     label: "price",   visible: true, sortable: false },
  { key: "change",    label: "change",  visible: true, sortable: false },
  { key: "changePct", label: "chg %",   visible: true, sortable: true  },
  { key: "prevClose", label: "prev close", visible: false, sortable: true },
  { key: "perf5d",    label: "5d %",    visible: true, sortable: true  },
  { key: "perf1m",    label: "1m %",    visible: true, sortable: true  },
  { key: "perf3m",    label: "3m %",    visible: true, sortable: true  },
  { key: "perf6m",    label: "6m %",    visible: true, sortable: true  },
  { key: "perfYtd",   label: "ytd %",   visible: true, sortable: true  },
  { key: "perf1y",    label: "1y %",    visible: true, sortable: true  },
  { key: "perf3y",    label: "3y %",    visible: true, sortable: true  },
  { key: "volume",    label: "volume",  visible: true, sortable: false },
];

function parseWLCols(saved: unknown): WLCol[] {
  if (!Array.isArray(saved)) return DEFAULT_WL_COLS;
  try {
    const parsed = saved as WLCol[];
    const keys = new Set(parsed.map((c) => c.key));
    return [...parsed, ...DEFAULT_WL_COLS.filter((c) => !keys.has(c.key))];
  } catch { /* empty */ }
  return DEFAULT_WL_COLS;
}

const STATUS_LABEL: Record<string, string> = {
  connecting: "Connecting...",
  connected: "Live",
  disconnected: "Reconnecting...",
};

const STATUS_DOT: Record<string, string> = {
  connecting: "dot--yellow",
  connected: "dot--green",
  disconnected: "dot--red",
};


export default function Stream() {
  const navigate = useNavigate();
  const token = getToken() ?? "";

  useEffect(() => {
    if (!token) navigate("/login");
  }, [token, navigate]);

  const { ticks, status } = useStockWebSocket(token);
  const authHeader = { Authorization: `Bearer ${token}` };
  const market = useMarketStatus();
  const isActive = market.session === "pre-market" || market.session === "open" || market.session === "post-market";
  const countdownTarget = isActive ? market.status?.nextClose ?? null : market.status?.nextOpen ?? null;
  const countdown = useCountdown(countdownTarget);
  const { prefs, loaded: prefsLoaded, update: updatePref } = usePreferences(token);
  const prevPrices = useRef<Record<string, number>>({});
  const [, forceUpdate] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFeedback, setSearchFeedback] = useState<{ msg: string; ok: boolean } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [userTickers, setUserTickers] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"watchlist" | "positions">("watchlist");
  const [sortKey, setSortKey] = useState("ticker");
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [wlCols, setWLCols] = useState<WLCol[]>(DEFAULT_WL_COLS);
  const [showWLPanel, setShowWLPanel] = useState(false);
  const [wlPanelPos, setWLPanelPos] = useState<{ top: number; right: number } | null>(null);
  const wlColBtnRef = useRef<HTMLButtonElement>(null);
  const [wlDragKey, setWLDragKey] = useState<WLColKey | null>(null);
  const [wlDragOverKey, setWLDragOverKey] = useState<WLColKey | null>(null);

  // Load column prefs from server
  useEffect(() => {
    if (prefsLoaded && prefs.wlCols) {
      setWLCols(parseWLCols(prefs.wlCols));
    }
  }, [prefsLoaded]);

  const fetchUserTickers = useCallback(async () => {
    const res = await fetch(`${API_BASE}/external/tickers/list`, { headers: authHeader });
    const data = await res.json();
    setUserTickers(data.tickers ?? []);
  }, [token]);

  useEffect(() => {
    fetchUserTickers();
    const id = setInterval(fetchUserTickers, 5000);
    return () => clearInterval(id);
  }, [fetchUserTickers]);


  useEffect(() => {
    function onKeyDown(e: globalThis.KeyboardEvent) {
      if (e.key !== "/") return;
      const active = document.activeElement;
      if (active === searchRef.current) return;
      if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) return;
      e.preventDefault();
      searchRef.current?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function showFeedbackMsg(msg: string, ok: boolean) {
    setSearchFeedback({ msg, ok });
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    feedbackTimer.current = setTimeout(() => setSearchFeedback(null), 2000);
  }

  async function handleSearchKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") { setSearchQuery(""); searchRef.current?.blur(); return; }
    if (e.key !== "Enter") return;
    const ticker = searchQuery.trim().toUpperCase();
    if (!ticker) return;
    if (!/^[A-Z]{1,5}$/.test(ticker)) { showFeedbackMsg(`"${ticker}" invalid ticker`, false); return; }
    if (userTickers.includes(ticker)) { showFeedbackMsg(`${ticker} already subscribed`, false); setSearchQuery(""); return; }
    await fetch(`${API_BASE}/external/tickers/${ticker}`, { method: "POST", headers: authHeader });
    await fetchUserTickers();
    showFeedbackMsg(`${ticker} added`, true);
    setSearchQuery("");
  }

  useEffect(() => {
    forceUpdate((n) => n + 1);
    const t = setTimeout(() => {
      for (const [k, v] of Object.entries(ticks)) { prevPrices.current[k] = v.price; }
      forceUpdate((n) => n + 1);
    }, 300);
    return () => clearTimeout(t);
  }, [ticks]);

  useEffect(() => {
    if (!showWLPanel) return;
    function close() { setShowWLPanel(false); }
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [showWLPanel]);

  function saveWLCols(next: WLCol[]) { setWLCols(next); updatePref("wlCols", next); }
  function toggleWLCol(key: WLColKey) { saveWLCols(wlCols.map((c) => c.key === key ? { ...c, visible: !c.visible } : c)); }
  function onWLDragStart(key: WLColKey) { setWLDragKey(key); }
  function onWLDragOver(e: React.DragEvent, key: WLColKey) { e.preventDefault(); setWLDragOverKey(key); }
  function onWLDrop(targetKey: WLColKey) {
    if (!wlDragKey || wlDragKey === targetKey) { setWLDragKey(null); setWLDragOverKey(null); return; }
    const next = [...wlCols];
    const from = next.findIndex((c) => c.key === wlDragKey);
    const to = next.findIndex((c) => c.key === targetKey);
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    saveWLCols(next);
    setWLDragKey(null); setWLDragOverKey(null);
  }
  function openWLPanel(e: React.MouseEvent) {
    e.stopPropagation();
    if (showWLPanel) { setShowWLPanel(false); return; }
    const rect = wlColBtnRef.current!.getBoundingClientRect();
    setWLPanelPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
    setShowWLPanel(true);
  }

  function toggleSort(key: string) {
    if (key === "ticker") { setSortKey("ticker"); setSortDir(1); return; }
    if (sortKey === key) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(-1); }
  }

  const displayList = userTickers.slice().sort((a, b) => {
    if (sortKey === "ticker") return a.localeCompare(b);
    const va = (ticks[a] as unknown as Record<string, number | undefined>)?.[sortKey] ?? -Infinity;
    const vb = (ticks[b] as unknown as Record<string, number | undefined>)?.[sortKey] ?? -Infinity;
    return (va - vb) * sortDir;
  });

  const visibleWLCols = wlCols.filter((c) => c.visible);
  const noData = displayList.length === 0;

  if (!token) return null;

  return (
    <div className="dashboard stream-scope">
      <NavBar />

      <div className="stream-toolbar">
        <span className="stream-label">stream</span>
        <div className="stream-toolbar__search">
          <div className="search-wrap">
            <span className="search-slash">/</span>
            <input
              ref={searchRef}
              className="search-input"
              type="text"
              placeholder="add ticker..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value.replace(/^\//, ""))}
              onKeyDown={handleSearchKeyDown}
              autoComplete="off"
              spellCheck={false}
            />
            {searchFeedback && (
              <span className={`search-feedback ${searchFeedback.ok ? "search-feedback--ok" : "search-feedback--err"}`}>
                {searchFeedback.msg}
              </span>
            )}
          </div>
        </div>
        <div className="stream-toolbar__right">
          <span className={`status-dot ${market.dotClass}`} />
          <span className="status-label">{market.label}</span>
        </div>
      </div>

      <div className="tab-bar">
        <button className={`tab${activeTab === "watchlist" ? " tab--active" : ""}`} onClick={() => setActiveTab("watchlist")}>watchlist</button>
        <button className={`tab${activeTab === "positions" ? " tab--active" : ""}`} onClick={() => setActiveTab("positions")}>positions</button>
      </div>

      <main className="main-content">
        {activeTab === "positions" ? (
          <PositionsTab token={token} ticks={ticks} />
        ) : noData ? (
          <div className="empty-state">
            <p className="empty-state__icon">⏳</p>
            <p className="empty-state__title">waiting for data...</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="stock-table">
              <colgroup>
                <col className="col--ticker" />
                {visibleWLCols.map((c) => <col key={c.key} className="col--data" />)}
                <col className="col--action" />
              </colgroup>
              <thead>
                <tr>
                  <th className={`th th--sortable${sortKey === "ticker" ? " th--active" : ""}`} onClick={() => toggleSort("ticker")}>
                    ticker {sortKey === "ticker" && sortDir === -1 ? "↓" : ""}
                  </th>
                  {visibleWLCols.map((c) => (
                    <th key={c.key} className={`th th--right${c.sortable ? " th--sortable" : ""}${sortKey === c.key ? " th--active" : ""}`} onClick={c.sortable ? () => toggleSort(c.key) : undefined}>
                      {c.label} {c.sortable && sortKey === c.key ? (sortDir === 1 ? "↑" : "↓") : ""}
                    </th>
                  ))}
                  <th className="th th--action">
                    <button ref={wlColBtnRef} className="col-config-btn" onClick={openWLPanel} title="configure columns">
                      <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168l10-10zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/></svg>
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {displayList.map((ticker) => (
                  <TickerRow
                    key={ticker}
                    ticker={ticker}
                    tick={ticks[ticker]}
                    prevPrice={prevPrices.current[ticker]}
                    visibleCols={visibleWLCols.map((c) => c.key)}
                    onRemove={async () => {
                      await fetch(`${API_BASE}/external/tickers/${ticker}`, { method: "DELETE", headers: authHeader });
                      await fetchUserTickers();
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {showWLPanel && wlPanelPos && createPortal(
        <div className="col-panel" style={{ position: "fixed", top: wlPanelPos.top, right: wlPanelPos.right }} onPointerDown={(e) => e.stopPropagation()}>
          <div className="col-panel__header">columns</div>
          {wlCols.map((c) => (
            <div key={c.key} className={`col-panel__row${wlDragOverKey === c.key ? " col-panel__row--over" : ""}`}
              onDragOver={(e) => onWLDragOver(e, c.key)} onDrop={() => onWLDrop(c.key)}>
              <span className="col-panel__drag" draggable onDragStart={() => onWLDragStart(c.key)} onDragEnd={() => { setWLDragKey(null); setWLDragOverKey(null); }}>⠿</span>
              <span className="col-panel__label">{c.label}</span>
              <input type="checkbox" className="col-panel__check" checked={c.visible} onChange={() => toggleWLCol(c.key)} />
            </div>
          ))}
          <button className="col-panel__revert" onClick={() => { saveWLCols(DEFAULT_WL_COLS); setShowWLPanel(false); }}>reset to default</button>
        </div>,
        document.body
      )}

      <footer className="statusbar">
        <span className={`status-dot ${STATUS_DOT[status]}`} />
        <span className="statusbar-label">{STATUS_LABEL[status].toLowerCase()}</span>
        <span className="statusbar-sep">·</span>
        <span className="statusbar-label">{WS_BASE}</span>
        {countdown !== null && countdown > 0 && (
          <>
            <span className="statusbar-sep">·</span>
            <span className="statusbar-label">
              {isActive ? `trading stops in ${formatCountdown(countdown)}` : `trading in ${formatCountdown(countdown)}`}
            </span>
          </>
        )}
      </footer>
    </div>
  );
}
