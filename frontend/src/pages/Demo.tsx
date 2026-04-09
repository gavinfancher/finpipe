import { useState, useEffect, useRef, useCallback, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import NavBar from "../components/NavBar";
import { useMarketStatus, useCountdown, formatCountdown } from "../hooks/useMarketStatus";
import TickerRow, { type WLColKey } from "../components/TickerRow";
import type { StockTick, ServerMessage, Position } from "../types";
import { WS_BASE } from "../config";

/* ── allowed tickers ── */

const DEMO_TICKERS = new Set([
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
  "TSLA", "META", "JPM", "V", "UNH",
]);

/* ── static fallback data (used when WS has no data) ── */

const STATIC_TICKS: Record<string, StockTick> = {
  AAPL:  { ticker: "AAPL",  price: 224.37, open: 222.80, change: 1.57,  changePct: 0.70,  prevClose: 222.80, perf5d: 2.86,  perf1m: -3.32, perf3m: -8.14, perf6m: 5.21,  perfYtd: -4.59, perf1y: 14.31, perf3y: 28.42, timestamp: 0, volume: 48_320_000 },
  MSFT:  { ticker: "MSFT",  price: 418.92, open: 416.10, change: 2.82,  changePct: 0.68,  prevClose: 416.10, perf5d: 1.94,  perf1m: -2.18, perf3m: -5.62, perf6m: 1.83,  perfYtd: -3.41, perf1y: 8.57,  perf3y: 42.16, timestamp: 0, volume: 22_150_000 },
  GOOGL: { ticker: "GOOGL", price: 161.24, open: 159.90, change: 1.34,  changePct: 0.84,  prevClose: 159.90, perf5d: 3.12,  perf1m: -1.45, perf3m: -3.89, perf6m: 8.72,  perfYtd: -2.10, perf1y: 19.65, perf3y: 55.33, timestamp: 0, volume: 31_400_000 },
  AMZN:  { ticker: "AMZN",  price: 186.53, open: 185.20, change: 1.33,  changePct: 0.72,  prevClose: 185.20, perf5d: 2.41,  perf1m: -4.15, perf3m: -7.22, perf6m: 3.18,  perfYtd: -5.73, perf1y: 12.84, perf3y: 38.91, timestamp: 0, volume: 54_800_000 },
  NVDA:  { ticker: "NVDA",  price: 114.22, open: 112.50, change: 1.72,  changePct: 1.53,  prevClose: 112.50, perf5d: 5.64,  perf1m: -8.91, perf3m: -15.30, perf6m: -12.44, perfYtd: -14.82, perf1y: 42.17, perf3y: 412.50, timestamp: 0, volume: 312_000_000 },
  TSLA:  { ticker: "TSLA",  price: 272.18, open: 268.40, change: 3.78,  changePct: 1.41,  prevClose: 268.40, perf5d: 4.22,  perf1m: -12.56, perf3m: -18.44, perf6m: -22.17, perfYtd: -31.60, perf1y: -3.28, perf3y: -8.14, timestamp: 0, volume: 98_600_000 },
  META:  { ticker: "META",  price: 562.41, open: 558.70, change: 3.71,  changePct: 0.66,  prevClose: 558.70, perf5d: 1.88,  perf1m: -5.72, perf3m: -9.31, perf6m: -1.22, perfYtd: -6.15, perf1y: 21.43, perf3y: 185.20, timestamp: 0, volume: 18_900_000 },
  JPM:   { ticker: "JPM",   price: 243.15, open: 241.80, change: 1.35,  changePct: 0.56,  prevClose: 241.80, perf5d: 0.92,  perf1m: 2.14,  perf3m: 5.87,  perf6m: 12.63, perfYtd: 8.41,  perf1y: 32.50, perf3y: 68.74, timestamp: 0, volume: 9_200_000 },
  V:     { ticker: "V",     price: 332.08, open: 330.50, change: 1.58,  changePct: 0.48,  prevClose: 330.50, perf5d: 1.15,  perf1m: 0.82,  perf3m: 3.44,  perf6m: 7.92,  perfYtd: 5.18,  perf1y: 18.66, perf3y: 44.33, timestamp: 0, volume: 6_800_000 },
  UNH:   { ticker: "UNH",   price: 498.62, open: 501.30, change: -2.68, changePct: -0.53, prevClose: 501.30, perf5d: -1.84, perf1m: -8.42, perf3m: -14.18, perf6m: -18.30, perfYtd: -13.52, perf1y: -7.91, perf3y: 2.15, timestamp: 0, volume: 4_100_000 },
};

/* ── localStorage helpers ── */

const WL_LS = "demo-watchlist";
const POS_LS = "demo-positions";
const COL_LS = "demo-wl-cols";
const PCOL_LS = "demo-pos-cols";

function lsLoad<T>(key: string, fallback: T): T {
  try { const s = localStorage.getItem(key); if (s) return JSON.parse(s); } catch { /* empty */ }
  return fallback;
}
function lsSave(key: string, val: unknown) { localStorage.setItem(key, JSON.stringify(val)); }

/* ── column defs (same as Stream) ── */

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

/* ── positions column defs (same as PositionsTab) ── */

type PosColKey = "marketValue" | "dayPlPct" | "dayPl" | "shares" | "totalCost" | "totalPlPct" | "totalPl";

interface PosCol { key: PosColKey; label: string; visible: boolean; }

const DEFAULT_POS_COLS: PosCol[] = [
  { key: "marketValue", label: "mkt value",    visible: true },
  { key: "dayPlPct",    label: "today p/l %",  visible: true },
  { key: "dayPl",       label: "today p/l",    visible: true },
  { key: "shares",      label: "shares",       visible: true },
  { key: "totalCost",   label: "cost",         visible: true },
  { key: "totalPlPct",  label: "total p/l %",  visible: true },
  { key: "totalPl",     label: "total p/l",    visible: true },
];

function parsePCols(saved: unknown): PosCol[] {
  if (!Array.isArray(saved)) return DEFAULT_POS_COLS;
  try {
    const parsed = saved as PosCol[];
    const keys = new Set(parsed.map((c) => c.key));
    return [...parsed, ...DEFAULT_POS_COLS.filter((c) => !keys.has(c.key))];
  } catch { /* empty */ }
  return DEFAULT_POS_COLS;
}

/* ── default demo positions ── */

const DEFAULT_POSITIONS: Position[] = [
  { id: 1, ticker: "AAPL",  shares: 50,  cost_basis: 178.25, opened_at: "2024-01-15" },
  { id: 2, ticker: "NVDA",  shares: 100, cost_basis: 48.12,  opened_at: "2023-06-20" },
  { id: 3, ticker: "MSFT",  shares: 25,  cost_basis: 340.50, opened_at: "2023-11-08" },
  { id: 4, ticker: "GOOGL", shares: 75,  cost_basis: 125.80, opened_at: "2024-03-12" },
  { id: 5, ticker: "TSLA",  shares: 30,  cost_basis: 245.60, opened_at: "2024-07-01" },
];

/* ── helpers ── */

const fmt = (n: number, decimals = 2) =>
  n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

function fmtPct(v: number): string {
  const abs = Math.abs(v);
  const sign = v >= 0 ? "+" : "\u2212";
  if (abs >= 1000) return sign + (abs / 1000).toFixed(2) + "k";
  const d = abs >= 100 ? 1 : abs >= 10 ? 2 : 3;
  return sign + abs.toFixed(d);
}

const perfColor = (n: number) => (n >= 0 ? "var(--green)" : "var(--red)");
const sign = (n: number) => (n >= 0 ? "+" : "");

type PosRow = {
  id: number; ticker: string; shares: number; cost_basis: number; opened_at: string;
  price: number | null; totalCost: number; marketValue: number | null;
  pl: number | null; plPct: number | null; dayPl: number | null; dayPlPct: number | null;
};

function posCell(key: PosColKey, r: PosRow) {
  const muted = "var(--text-muted)";
  if (key === "shares") return <>{fmt(r.shares, 4).replace(/\.?0+$/, "")}</>;
  if (key === "totalCost") return <>${fmt(r.totalCost)}</>;
  if (key === "marketValue") return r.marketValue !== null ? <>${fmt(r.marketValue)}</> : <span style={{ color: muted }}>—</span>;
  if (key === "dayPl") {
    const c = r.dayPl !== null ? perfColor(r.dayPl) : muted;
    return <span style={{ color: c }}>{r.dayPl !== null ? `${sign(r.dayPl)}$${fmt(Math.abs(r.dayPl))}` : "—"}</span>;
  }
  if (key === "dayPlPct") {
    const c = r.dayPlPct !== null ? perfColor(r.dayPlPct) : muted;
    return <span style={{ color: c }}>{r.dayPlPct !== null ? `${fmtPct(r.dayPlPct)}%` : "—"}</span>;
  }
  if (key === "totalPl") {
    const c = r.pl !== null ? perfColor(r.pl) : muted;
    return <span style={{ color: c }}>{r.pl !== null ? `${sign(r.pl)}$${fmt(Math.abs(r.pl))}` : "—"}</span>;
  }
  if (key === "totalPlPct") {
    const c = r.plPct !== null ? perfColor(r.plPct) : muted;
    return <span style={{ color: c }}>{r.plPct !== null ? `${fmtPct(r.plPct)}%` : "—"}</span>;
  }
}

/* ── demo WebSocket hook ── */

function useDemoWebSocket() {
  const [ticks, setTicks] = useState<Record<string, StockTick>>(STATIC_TICKS);
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmounted = useRef(false);

  const connect = useCallback(() => {
    if (unmounted.current) return;
    setWsStatus("connecting");
    const ws = new WebSocket(`${WS_BASE}/ws/demo`);
    wsRef.current = ws;
    ws.onopen = () => { if (!unmounted.current) setWsStatus("connected"); };
    ws.onmessage = (event: MessageEvent<string>) => {
      if (unmounted.current) return;
      setWsStatus("connected");
      try {
        const msg: ServerMessage = JSON.parse(event.data);
        if (msg.type === "snapshot") setTicks((prev) => ({ ...prev, ...msg.ticks }));
        else if (msg.type === "tick") setTicks((prev) => ({ ...prev, [msg.tick.ticker]: msg.tick }));
      } catch { /* ignore */ }
    };
    ws.onclose = () => {
      if (!unmounted.current) { setWsStatus("disconnected"); reconnectTimer.current = setTimeout(connect, 3000); }
    };
    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    unmounted.current = false;
    connect();
    return () => { unmounted.current = true; wsRef.current?.close(); if (reconnectTimer.current) clearTimeout(reconnectTimer.current); };
  }, [connect]);

  return { ticks, wsStatus };
}

/* ── component ── */

const STATUS_LABEL: Record<string, string> = { connecting: "Connecting...", connected: "Live", disconnected: "Reconnecting..." };
const STATUS_DOT: Record<string, string> = { connecting: "dot--yellow", connected: "dot--green", disconnected: "dot--red" };

interface DropdownPos { top: number; right: number; }

export default function Demo() {
  const { ticks, wsStatus } = useDemoWebSocket();
  const market = useMarketStatus();
  const isActive = market.session === "pre-market" || market.session === "open" || market.session === "post-market";
  const countdownTarget = isActive ? market.status?.nextClose ?? null : market.status?.nextOpen ?? null;
  const countdown = useCountdown(countdownTarget);

  const prevPrices = useRef<Record<string, number>>({});
  const [, forceUpdate] = useState(0);

  // ── tabs ──
  const [activeTab, setActiveTab] = useState<"watchlist" | "positions">("watchlist");

  // ── watchlist state (localStorage) ──
  const [userTickers, setUserTickers] = useState<string[]>(() => lsLoad<string[]>(WL_LS, [...DEMO_TICKERS]));
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFeedback, setSearchFeedback] = useState<{ msg: string; ok: boolean } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [sortKey, setSortKey] = useState("ticker");
  const [sortDir, setSortDir] = useState<1 | -1>(1);

  // ── watchlist column config ──
  const [wlCols, setWLCols] = useState<WLCol[]>(() => parseWLCols(lsLoad(COL_LS, null)));
  const [showWLPanel, setShowWLPanel] = useState(false);
  const [wlPanelPos, setWLPanelPos] = useState<DropdownPos | null>(null);
  const wlColBtnRef = useRef<HTMLButtonElement>(null);
  const [wlDragKey, setWLDragKey] = useState<WLColKey | null>(null);
  const [wlDragOverKey, setWLDragOverKey] = useState<WLColKey | null>(null);

  // ── positions state (localStorage) ──
  const [positions, setPositions] = useState<Position[]>(() => lsLoad<Position[]>(POS_LS, DEFAULT_POSITIONS));
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ticker: "", shares: "", total_cost: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const [editModal, setEditModal] = useState<{ id: number; ticker: string; shares: string; total_cost: string } | null>(null);

  // ── positions column config ──
  const [pCols, setPCols] = useState<PosCol[]>(() => parsePCols(lsLoad(PCOL_LS, null)));
  const [showPColPanel, setShowPColPanel] = useState(false);
  const [pColPanelPos, setPColPanelPos] = useState<DropdownPos | null>(null);
  const pColBtnRef = useRef<HTMLButtonElement>(null);
  const [pDragKey, setPDragKey] = useState<PosColKey | null>(null);
  const [pDragOverKey, setPDragOverKey] = useState<PosColKey | null>(null);

  // ── positions row menu ──
  const [dropdownId, setDropdownId] = useState<number | null>(null);
  const [dropdownPos, setDropdownPos] = useState<DropdownPos | null>(null);
  const triggerRefs = useRef<Map<number, HTMLButtonElement>>(new Map());

  const [posSortKey, setPosSortKey] = useState("ticker");
  const [posSortDir, setPosSortDir] = useState<1 | -1>(1);

  // ── persist helpers ──
  function saveUserTickers(next: string[]) { setUserTickers(next); lsSave(WL_LS, next); }
  function savePositions(next: Position[]) { setPositions(next); lsSave(POS_LS, next); }
  function saveWLCols(next: WLCol[]) { setWLCols(next); lsSave(COL_LS, next); }
  function savePCols(next: PosCol[]) { setPCols(next); lsSave(PCOL_LS, next); }

  // ── price flash ──
  useEffect(() => {
    forceUpdate((n) => n + 1);
    const t = setTimeout(() => { for (const [k, v] of Object.entries(ticks)) prevPrices.current[k] = v.price; forceUpdate((n) => n + 1); }, 300);
    return () => clearTimeout(t);
  }, [ticks]);

  // ── keyboard shortcut ──
  useEffect(() => {
    function onKeyDown(e: globalThis.KeyboardEvent) {
      if (e.key !== "/") return;
      const active = document.activeElement;
      if (active === searchRef.current || active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) return;
      e.preventDefault();
      searchRef.current?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // ── close panels on outside click ──
  useEffect(() => { if (!showWLPanel) return; const close = () => setShowWLPanel(false); document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, [showWLPanel]);
  useEffect(() => { if (!showPColPanel) return; const close = () => setShowPColPanel(false); document.addEventListener("pointerdown", close); return () => document.removeEventListener("pointerdown", close); }, [showPColPanel]);
  useEffect(() => { if (!dropdownPos) return; const close = () => { setDropdownId(null); setDropdownPos(null); }; document.addEventListener("pointerdown", close); document.addEventListener("scroll", close, true); return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("scroll", close, true); }; }, [dropdownPos]);

  // ── search ──
  function showFeedbackMsg(msg: string, ok: boolean) {
    setSearchFeedback({ msg, ok });
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current);
    if (ok) feedbackTimer.current = setTimeout(() => setSearchFeedback(null), 2000);
  }

  function submitTicker() {
    const ticker = searchQuery.trim().toUpperCase();
    if (!ticker) return;
    if (!/^[A-Z]{1,5}$/.test(ticker)) { showFeedbackMsg(`"${ticker}" invalid ticker`, false); return; }
    if (!DEMO_TICKERS.has(ticker)) { showFeedbackMsg(`demo tickers: ${[...DEMO_TICKERS].join(", ")}`, false); return; }
    if (userTickers.includes(ticker)) { showFeedbackMsg(`${ticker} already subscribed`, false); setSearchQuery(""); return; }
    saveUserTickers([...userTickers, ticker]);
    showFeedbackMsg(`${ticker} added`, true);
    setSearchQuery("");
  }

  function handleSearchKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") { setSearchQuery(""); searchRef.current?.blur(); return; }
    if (e.key === "Enter") submitTicker();
  }

  // ── watchlist sorting ──
  function toggleSort(key: string) {
    if (key === "ticker") { setSortKey("ticker"); setSortDir(1); return; }
    if (sortKey === key) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(-1); }
  }

  // ── watchlist column panel ──
  function toggleWLCol(key: WLColKey) { saveWLCols(wlCols.map((c) => c.key === key ? { ...c, visible: !c.visible } : c)); }
  function onWLDragStart(key: WLColKey) { setWLDragKey(key); }
  function onWLDragOver(e: React.DragEvent, key: WLColKey) { e.preventDefault(); setWLDragOverKey(key); }
  function onWLDrop(targetKey: WLColKey) {
    if (!wlDragKey || wlDragKey === targetKey) { setWLDragKey(null); setWLDragOverKey(null); return; }
    const next = [...wlCols]; const from = next.findIndex((c) => c.key === wlDragKey); const to = next.findIndex((c) => c.key === targetKey);
    const [item] = next.splice(from, 1); next.splice(to, 0, item); saveWLCols(next); setWLDragKey(null); setWLDragOverKey(null);
  }
  function openWLPanel(e: React.MouseEvent) {
    e.stopPropagation();
    if (showWLPanel) { setShowWLPanel(false); return; }
    const rect = wlColBtnRef.current!.getBoundingClientRect();
    setWLPanelPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right }); setShowWLPanel(true);
  }

  // ── positions column panel ──
  function togglePCol(key: PosColKey) { savePCols(pCols.map((c) => c.key === key ? { ...c, visible: !c.visible } : c)); }
  function onPDragStart(key: PosColKey) { setPDragKey(key); }
  function onPDragOver(e: React.DragEvent, key: PosColKey) { e.preventDefault(); setPDragOverKey(key); }
  function onPDrop(targetKey: PosColKey) {
    if (!pDragKey || pDragKey === targetKey) { setPDragKey(null); setPDragOverKey(null); return; }
    const next = [...pCols]; const from = next.findIndex((c) => c.key === pDragKey); const to = next.findIndex((c) => c.key === targetKey);
    const [item] = next.splice(from, 1); next.splice(to, 0, item); savePCols(next); setPDragKey(null); setPDragOverKey(null);
  }
  function openPColPanel(e: React.MouseEvent) {
    e.stopPropagation();
    if (showPColPanel) { setShowPColPanel(false); return; }
    const rect = pColBtnRef.current!.getBoundingClientRect();
    setPColPanelPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right }); setShowPColPanel(true);
  }

  // ── positions row menu ──
  function openMenu(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    if (dropdownId === id) { setDropdownId(null); setDropdownPos(null); return; }
    const rect = triggerRefs.current.get(id)!.getBoundingClientRect();
    setDropdownId(id); setDropdownPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
  }
  function openEdit(p: Position) {
    setDropdownId(null); setDropdownPos(null);
    setEditModal({ id: p.id, ticker: p.ticker, shares: String(p.shares), total_cost: String(+(p.shares * p.cost_basis).toFixed(4)) });
  }
  function handleSaveEdit() {
    if (!editModal) return;
    const shares = parseFloat(editModal.shares);
    const total_cost = parseFloat(editModal.total_cost);
    if (isNaN(shares) || shares <= 0 || isNaN(total_cost) || total_cost <= 0) return;
    savePositions(positions.map((p) => p.id === editModal.id ? { ...p, shares, cost_basis: total_cost / shares } : p));
    setEditModal(null);
  }
  function handleAddPosition() {
    const ticker = form.ticker.trim().toUpperCase();
    const shares = parseFloat(form.shares);
    const total_cost = parseFloat(form.total_cost);
    if (!ticker || !DEMO_TICKERS.has(ticker)) { setFormError(`pick from: ${[...DEMO_TICKERS].join(", ")}`); return; }
    if (isNaN(shares) || shares <= 0) { setFormError("shares must be > 0"); return; }
    if (isNaN(total_cost) || total_cost <= 0) { setFormError("total cost must be > 0"); return; }
    const nextId = positions.length > 0 ? Math.max(...positions.map((p) => p.id)) + 1 : 1;
    savePositions([...positions, { id: nextId, ticker, shares, cost_basis: total_cost / shares, opened_at: new Date().toISOString().slice(0, 10) }]);
    setForm({ ticker: "", shares: "", total_cost: "" }); setShowForm(false); setFormError(null);
  }
  function handleRemovePosition(id: number) { setDropdownId(null); setDropdownPos(null); savePositions(positions.filter((p) => p.id !== id)); }

  function togglePosSort(key: string) {
    if (posSortKey === key) setPosSortDir((d) => (d === 1 ? -1 : 1));
    else { setPosSortKey(key); setPosSortDir(key === "ticker" ? 1 : -1); }
  }

  // ── derived data ──
  const displayList = userTickers.slice().sort((a, b) => {
    if (sortKey === "ticker") return a.localeCompare(b);
    const va = (ticks[a] as unknown as Record<string, number | undefined>)?.[sortKey] ?? -Infinity;
    const vb = (ticks[b] as unknown as Record<string, number | undefined>)?.[sortKey] ?? -Infinity;
    return (va - vb) * sortDir;
  });

  const visibleWLCols = wlCols.filter((c) => c.visible);
  const visiblePCols = pCols.filter((c) => c.visible);

  const POS_SORT_FIELD: Record<PosColKey, keyof PosRow> = {
    marketValue: "marketValue", dayPlPct: "dayPlPct", dayPl: "dayPl",
    shares: "shares", totalCost: "totalCost", totalPlPct: "plPct", totalPl: "pl",
  };

  const rows: PosRow[] = positions.map((p) => {
    const tick = ticks[p.ticker];
    const price = tick?.price ?? null;
    const totalCost = p.shares * p.cost_basis;
    const marketValue = price !== null ? p.shares * price : null;
    const pl = marketValue !== null ? marketValue - totalCost : null;
    const plPct = pl !== null ? (pl / totalCost) * 100 : null;
    const dayPl = tick?.change != null ? p.shares * tick.change : null;
    const dayPlPct = tick?.changePct ?? null;
    return { ...p, price, totalCost, marketValue, pl, plPct, dayPl, dayPlPct };
  });

  const sortedRows = rows.slice().sort((a, b) => {
    if (posSortKey === "ticker") return a.ticker.localeCompare(b.ticker) * posSortDir;
    const field = POS_SORT_FIELD[posSortKey as PosColKey];
    const va = (a[field] as number | null) ?? -Infinity;
    const vb = (b[field] as number | null) ?? -Infinity;
    return (va - vb) * posSortDir;
  });

  const totalValue = rows.reduce((s, r) => s + (r.marketValue ?? r.totalCost), 0);
  const totalPl = rows.reduce((s, r) => s + (r.pl ?? 0), 0);
  const grandCost = rows.reduce((s, r) => s + r.totalCost, 0);
  const totalPlPct = grandCost > 0 ? (totalPl / grandCost) * 100 : 0;
  const noData = displayList.length === 0;

  return (
    <div className="dashboard stream-scope">
      <NavBar />

      <div className="stream-toolbar">
        <span className="stream-label">demo</span>
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
            <button className="search-add-btn" onClick={submitTicker} title="add ticker">+</button>
            {searchFeedback && (
              <span className={`search-feedback ${searchFeedback.ok ? "search-feedback--ok" : "search-feedback--err"}`}>
                {searchFeedback.msg}
                <button className="search-feedback__dismiss" onClick={() => setSearchFeedback(null)}>×</button>
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
          <div className="positions-tab">
            <div className="positions-summary">
              <div className="positions-summary__item">
                <span className="positions-summary__label">positions value</span>
                <span className="positions-summary__value">${fmt(totalValue)}</span>
              </div>
              <div className="positions-summary__item">
                <span className="positions-summary__label">live p/l</span>
                <span className="positions-summary__value" style={{ color: perfColor(totalPl) }}>
                  {sign(totalPl)}${fmt(Math.abs(totalPl))} ({sign(totalPlPct)}{fmt(totalPlPct)}%)
                </span>
              </div>
              <div className="positions-summary__actions">
                <button className="btn-primary btn-primary--sm" onClick={() => { setShowForm(true); setFormError(null); }}>+ add</button>
              </div>
            </div>

            {showForm && (
              <div className="position-form">
                <input className="position-form__input" placeholder="ticker" value={form.ticker} onChange={(e) => setForm((f) => ({ ...f, ticker: e.target.value }))} autoFocus />
                <input className="position-form__input" placeholder="shares" type="number" min="0" step="any" value={form.shares} onChange={(e) => setForm((f) => ({ ...f, shares: e.target.value }))} />
                <input className="position-form__input" placeholder="total cost" type="number" min="0" step="any" value={form.total_cost} onChange={(e) => setForm((f) => ({ ...f, total_cost: e.target.value }))} />
                {formError && <span className="position-form__error">{formError}</span>}
                <button className="btn-primary btn-primary--sm" onClick={handleAddPosition}>add</button>
                <button className="btn-ghost btn-ghost--sm" onClick={() => setShowForm(false)}>cancel</button>
              </div>
            )}

            {rows.length === 0 ? (
              <div className="empty-state">
                <p className="empty-state__icon">📭</p>
                <p className="empty-state__title">no positions yet</p>
              </div>
            ) : (
              <div className="table-wrapper">
                <table className="stock-table">
                  <colgroup>
                    <col className="col--ticker" />
                    {visiblePCols.map((c) => <col key={c.key} className="col--data col--data-wide" />)}
                    <col className="col--action" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th className={`th th--sortable${posSortKey === "ticker" ? " th--active" : ""}`} onClick={() => togglePosSort("ticker")}>
                        ticker {posSortKey === "ticker" && posSortDir === -1 ? "↓" : ""}
                      </th>
                      {visiblePCols.map((c) => (
                        <th key={c.key} className={`th th--right th--sortable${posSortKey === c.key ? " th--active" : ""}`} onClick={() => togglePosSort(c.key)}>
                          {c.label} {posSortKey === c.key ? (posSortDir === 1 ? "↑" : "↓") : ""}
                        </th>
                      ))}
                      <th className="th th--action">
                        <button ref={pColBtnRef} className="col-config-btn" onClick={openPColPanel} title="configure columns">
                          <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168l10-10zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/></svg>
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRows.map((r) => (
                      <tr key={r.id} className="ticker-row">
                        <td className="cell cell--ticker">{r.ticker}</td>
                        {visiblePCols.map((c) => (
                          <td key={c.key} className="cell cell--num">{posCell(c.key, r)}</td>
                        ))}
                        <td className="cell cell--action">
                          <button ref={(el) => { if (el) triggerRefs.current.set(r.id, el); }} className="row-menu-trigger" onClick={(e) => openMenu(r.id, e)} aria-label="row options">⋮</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : noData ? (
          <div className="empty-state">
            <p className="empty-state__icon">⏳</p>
            <p className="empty-state__title">watchlist empty — type / to add a ticker</p>
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
                    onRemove={() => saveUserTickers(userTickers.filter((t) => t !== ticker))}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      {/* ── watchlist column config panel ── */}
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

      {/* ── positions column config panel ── */}
      {showPColPanel && pColPanelPos && createPortal(
        <div className="col-panel" style={{ position: "fixed", top: pColPanelPos.top, right: pColPanelPos.right }} onPointerDown={(e) => e.stopPropagation()}>
          <div className="col-panel__header">columns</div>
          {pCols.map((c) => (
            <div key={c.key} className={`col-panel__row${pDragOverKey === c.key ? " col-panel__row--over" : ""}`}
              onDragOver={(e) => onPDragOver(e, c.key)} onDrop={() => onPDrop(c.key)}>
              <span className="col-panel__drag" draggable onDragStart={() => onPDragStart(c.key)} onDragEnd={() => { setPDragKey(null); setPDragOverKey(null); }}>⠿</span>
              <span className="col-panel__label">{c.label}</span>
              <input type="checkbox" className="col-panel__check" checked={c.visible} onChange={() => togglePCol(c.key)} />
            </div>
          ))}
          <button className="col-panel__revert" onClick={() => { savePCols(DEFAULT_POS_COLS); setShowPColPanel(false); }}>reset to default</button>
        </div>,
        document.body
      )}

      {/* ── positions row dropdown ── */}
      {dropdownId !== null && dropdownPos && createPortal(
        <div className="row-menu-dropdown" style={{ position: "fixed", top: dropdownPos.top, right: dropdownPos.right }} onPointerDown={(e) => e.stopPropagation()}>
          <button className="row-menu-item" onClick={() => openEdit(positions.find((p) => p.id === dropdownId)!)}>edit position</button>
          <button className="row-menu-item row-menu-item--danger" onClick={() => handleRemovePosition(dropdownId)}>remove position</button>
        </div>,
        document.body
      )}

      {/* ── edit modal ── */}
      {editModal && createPortal(
        <div className="edit-modal-overlay" onPointerDown={() => setEditModal(null)}>
          <div className="edit-modal" onPointerDown={(e) => e.stopPropagation()}>
            <div className="edit-modal__title">{editModal.ticker}</div>
            <div className="edit-modal__fields">
              <label className="edit-modal__label">
                shares
                <input className="position-form__input" type="number" min="0" step="any"
                  value={editModal.shares}
                  onChange={(e) => setEditModal((m) => m && ({ ...m, shares: e.target.value }))}
                  onKeyDown={(e) => { if (e.key === "Enter") handleSaveEdit(); if (e.key === "Escape") setEditModal(null); }}
                  autoFocus
                />
              </label>
              <label className="edit-modal__label">
                total cost
                <div className="edit-modal__input-wrap">
                  <span className="edit-modal__prefix">$</span>
                  <input className="position-form__input" type="number" min="0" step="0.01"
                    value={editModal.total_cost}
                    onChange={(e) => setEditModal((m) => m && ({ ...m, total_cost: e.target.value }))}
                    onBlur={(e) => { const v = parseFloat(e.target.value); if (!isNaN(v)) setEditModal((m) => m && ({ ...m, total_cost: v.toFixed(2) })); }}
                    onKeyDown={(e) => { if (e.key === "Enter") handleSaveEdit(); if (e.key === "Escape") setEditModal(null); }}
                  />
                </div>
              </label>
            </div>
            <div className="edit-modal__actions">
              <button className="btn-primary btn-primary--sm" onClick={handleSaveEdit}>save</button>
              <button className="btn-ghost btn-ghost--sm" onClick={() => setEditModal(null)}>cancel</button>
            </div>
          </div>
        </div>,
        document.body
      )}

      <footer className="statusbar">
        <span className={`status-dot ${STATUS_DOT[wsStatus]}`} />
        <span className="statusbar-label">{STATUS_LABEL[wsStatus].toLowerCase()}</span>
        <span className="statusbar-sep">·</span>
        <span className="statusbar-label">demo</span>
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
