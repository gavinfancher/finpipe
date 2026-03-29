import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import type { Position, StockTick } from "../types";

interface Props {
  token: string;
  ticks: Record<string, StockTick>;
}

interface DropdownPos { top: number; right: number; }

type ColKey = "marketValue" | "dayPlPct" | "dayPl" | "shares" | "totalCost" | "totalPlPct" | "totalPl";

interface ColDef {
  key: ColKey;
  label: string;
  visible: boolean;
}

const DEFAULT_COLS: ColDef[] = [
  { key: "marketValue", label: "mkt value",    visible: true },
  { key: "dayPlPct",    label: "today p/l %",  visible: true },
  { key: "dayPl",       label: "today p/l",    visible: true },
  { key: "shares",      label: "shares",       visible: true },
  { key: "totalCost",   label: "cost",         visible: true },
  { key: "totalPlPct",  label: "total p/l %",  visible: true },
  { key: "totalPl",     label: "total p/l",    visible: true },
];

const LS_KEY = "positions-columns";

function loadCols(): ColDef[] {
  try {
    const saved = localStorage.getItem(LS_KEY);
    if (saved) {
      const parsed: ColDef[] = JSON.parse(saved);
      const keys = new Set(parsed.map((c) => c.key));
      return [...parsed, ...DEFAULT_COLS.filter((c) => !keys.has(c.key))];
    }
  } catch { /* empty */ }
  return DEFAULT_COLS;
}

import { API_BASE } from "../config";

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

type Row = {
  id: number; ticker: string; shares: number; cost_basis: number; opened_at: string;
  price: number | null; totalCost: number; marketValue: number | null;
  pl: number | null; plPct: number | null; dayPl: number | null; dayPlPct: number | null;
};

function cellContent(key: ColKey, r: Row) {
  const muted = "var(--text-muted)";
  if (key === "shares") return <>{fmt(r.shares, 4).replace(/\.?0+$/, "")}</>;
  if (key === "totalCost") return <>${fmt(r.totalCost)}</>;
  if (key === "marketValue") return <>{r.marketValue !== null ? `$${fmt(r.marketValue)}` : <span style={{ color: muted }}>—</span>}</>;
  if (key === "dayPl") {
    const color = r.dayPl !== null ? perfColor(r.dayPl) : muted;
    return <span style={{ color }}>{r.dayPl !== null ? `${sign(r.dayPl)}$${fmt(Math.abs(r.dayPl))}` : "—"}</span>;
  }
  if (key === "dayPlPct") {
    const color = r.dayPlPct !== null ? perfColor(r.dayPlPct) : muted;
    return <span style={{ color }}>{r.dayPlPct !== null ? `${fmtPct(r.dayPlPct)}%` : "—"}</span>;
  }
  if (key === "totalPl") {
    const color = r.pl !== null ? perfColor(r.pl) : muted;
    return <span style={{ color }}>{r.pl !== null ? `${sign(r.pl)}$${fmt(Math.abs(r.pl))}` : "—"}</span>;
  }
  if (key === "totalPlPct") {
    const color = r.plPct !== null ? perfColor(r.plPct) : muted;
    return <span style={{ color }}>{r.plPct !== null ? `${fmtPct(r.plPct)}%` : "—"}</span>;
  }
}

export default function PositionsTab({ token, ticks }: Props) {
  const authHeader = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const [positions, setPositions] = useState<Position[]>([]);
  const [cols, setCols] = useState<ColDef[]>(loadCols);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ticker: "", shares: "", total_cost: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [editModal, setEditModal] = useState<{ id: number; ticker: string; shares: string; total_cost: string } | null>(null);
  const [editSaving, setEditSaving] = useState(false);

  const [dropdownId, setDropdownId] = useState<number | null>(null);
  const [dropdownPos, setDropdownPos] = useState<DropdownPos | null>(null);
  const triggerRefs = useRef<Map<number, HTMLButtonElement>>(new Map());

  const [sortKey, setSortKey] = useState("ticker");
  const [sortDir, setSortDir] = useState<1 | -1>(1);

  const [showColPanel, setShowColPanel] = useState(false);
  const [colPanelPos, setColPanelPos] = useState<DropdownPos | null>(null);
  const colBtnRef = useRef<HTMLButtonElement>(null);
  const [dragKey, setDragKey] = useState<ColKey | null>(null);
  const [dragOverKey, setDragOverKey] = useState<ColKey | null>(null);

  function toggleSort(key: string) {
    if (sortKey === key) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(key); setSortDir(key === "ticker" ? 1 : -1); }
  }

  const fetchPositions = useCallback(async () => {
    const res = await fetch(`${API_BASE}/external/positions`, { headers: authHeader });
    const data = await res.json();
    setPositions(Array.isArray(data) ? data : []);
  }, [token]);

  useEffect(() => { fetchPositions(); }, [fetchPositions]);

  useEffect(() => {
    if (!dropdownPos) return;
    function close() { setDropdownId(null); setDropdownPos(null); }
    document.addEventListener("pointerdown", close);
    document.addEventListener("scroll", close, true);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("scroll", close, true); };
  }, [dropdownPos]);

  useEffect(() => {
    if (!showColPanel) return;
    function close() { setShowColPanel(false); }
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [showColPanel]);

  function saveCols(next: ColDef[]) {
    localStorage.setItem(LS_KEY, JSON.stringify(next));
    setCols(next);
  }
  function toggleCol(key: ColKey) {
    saveCols(cols.map((c) => c.key === key ? { ...c, visible: !c.visible } : c));
  }
  function onDragStart(key: ColKey) { setDragKey(key); }
  function onDragOver(e: React.DragEvent, key: ColKey) { e.preventDefault(); setDragOverKey(key); }
  function onDrop(targetKey: ColKey) {
    if (!dragKey || dragKey === targetKey) { setDragKey(null); setDragOverKey(null); return; }
    const next = [...cols];
    const from = next.findIndex((c) => c.key === dragKey);
    const to = next.findIndex((c) => c.key === targetKey);
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    saveCols(next);
    setDragKey(null); setDragOverKey(null);
  }
  function openColPanel(e: React.MouseEvent) {
    e.stopPropagation();
    if (showColPanel) { setShowColPanel(false); return; }
    const rect = colBtnRef.current!.getBoundingClientRect();
    setColPanelPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
    setShowColPanel(true);
  }
  function openMenu(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    if (dropdownId === id) { setDropdownId(null); setDropdownPos(null); return; }
    const rect = triggerRefs.current.get(id)!.getBoundingClientRect();
    setDropdownId(id);
    setDropdownPos({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
  }
  function openEdit(p: Position) {
    setDropdownId(null); setDropdownPos(null);
    setEditModal({
      id: p.id, ticker: p.ticker,
      shares: String(p.shares),
      total_cost: String(+(p.shares * p.cost_basis).toFixed(4)),
    });
  }
  async function handleSaveEdit() {
    if (!editModal) return;
    const shares = parseFloat(editModal.shares);
    const total_cost = parseFloat(editModal.total_cost);
    if (isNaN(shares) || shares <= 0 || isNaN(total_cost) || total_cost <= 0) return;
    setEditSaving(true);
    try {
      await fetch(`${API_BASE}/external/positions/${editModal.id}`, {
        method: "PATCH", headers: authHeader,
        body: JSON.stringify({ shares, cost_basis: total_cost / shares }),
      });
    } finally { setEditSaving(false); }
    setEditModal(null);
    await fetchPositions();
  }
  async function handleAdd() {
    const ticker = form.ticker.trim().toUpperCase();
    const shares = parseFloat(form.shares);
    const total_cost = parseFloat(form.total_cost);
    if (!ticker || !/^[A-Z]{1,5}$/.test(ticker)) { setFormError("invalid ticker"); return; }
    if (isNaN(shares) || shares <= 0) { setFormError("shares must be > 0"); return; }
    if (isNaN(total_cost) || total_cost <= 0) { setFormError("total cost must be > 0"); return; }
    setSubmitting(true); setFormError(null);
    try {
      const res = await fetch(`${API_BASE}/external/positions`, {
        method: "POST", headers: authHeader,
        body: JSON.stringify({ ticker, shares, cost_basis: total_cost / shares }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); setFormError(e.detail ?? `error ${res.status}`); setSubmitting(false); return; }
    } catch { setFormError("network error"); setSubmitting(false); return; }
    setForm({ ticker: "", shares: "", total_cost: "" });
    setShowForm(false); setSubmitting(false);
    await fetchPositions();
  }
  async function handleRemove(id: number) {
    setDropdownId(null); setDropdownPos(null);
    await fetch(`${API_BASE}/external/positions/${id}`, { method: "DELETE", headers: authHeader });
    await fetchPositions();
  }

  const rows: Row[] = positions.map((p) => {
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

  const COL_SORT_FIELD: Record<ColKey, keyof Row> = {
    marketValue: "marketValue", dayPlPct: "dayPlPct", dayPl: "dayPl",
    shares: "shares", totalCost: "totalCost", totalPlPct: "plPct", totalPl: "pl",
  };

  const sortedRows = rows.slice().sort((a, b) => {
    if (sortKey === "ticker") return a.ticker.localeCompare(b.ticker) * sortDir;
    const field = COL_SORT_FIELD[sortKey as ColKey];
    const va = (a[field] as number | null) ?? -Infinity;
    const vb = (b[field] as number | null) ?? -Infinity;
    return (va - vb) * sortDir;
  });

  const totalValue = rows.reduce((s, r) => s + (r.marketValue ?? r.totalCost), 0);
  const totalPl = rows.reduce((s, r) => s + (r.pl ?? 0), 0);
  const grandCost = rows.reduce((s, r) => s + r.totalCost, 0);
  const totalPlPct = grandCost > 0 ? (totalPl / grandCost) * 100 : 0;
  const visibleCols = cols.filter((c) => c.visible);

  return (
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
          <button className="btn-primary btn-primary--sm" onClick={handleAdd} disabled={submitting}>{submitting ? "adding..." : "add"}</button>
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
              {visibleCols.map((c) => <col key={c.key} className="col--data col--data-wide" />)}
              <col className="col--action" />
            </colgroup>
            <thead>
              <tr>
                <th className={`th th--sortable${sortKey === "ticker" ? " th--active" : ""}`} onClick={() => toggleSort("ticker")}>
                  ticker {sortKey === "ticker" && sortDir === -1 ? "↓" : ""}
                </th>
                {visibleCols.map((c) => (
                  <th key={c.key} className={`th th--right th--sortable${sortKey === c.key ? " th--active" : ""}`} onClick={() => toggleSort(c.key)}>
                    {c.label} {sortKey === c.key ? (sortDir === 1 ? "↑" : "↓") : ""}
                  </th>
                ))}
                <th className="th th--action">
                  <button ref={colBtnRef} className="col-config-btn" onClick={openColPanel} title="configure columns">
                    <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168l10-10zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/></svg>
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((r) => (
                <tr key={r.id} className="ticker-row">
                  <td className="cell cell--ticker">{r.ticker}</td>
                  {visibleCols.map((c) => (
                    <td key={c.key} className="cell cell--num">{cellContent(c.key, r)}</td>
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

      {dropdownId !== null && dropdownPos && createPortal(
        <div className="row-menu-dropdown" style={{ position: "fixed", top: dropdownPos.top, right: dropdownPos.right }} onPointerDown={(e) => e.stopPropagation()}>
          <button className="row-menu-item" onClick={() => openEdit(positions.find((p) => p.id === dropdownId)!)}>edit position</button>
          <button className="row-menu-item row-menu-item--danger" onClick={() => handleRemove(dropdownId)}>remove position</button>
        </div>,
        document.body
      )}

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
              <button className="btn-primary btn-primary--sm" onClick={handleSaveEdit} disabled={editSaving}>{editSaving ? "saving..." : "save"}</button>
              <button className="btn-ghost btn-ghost--sm" onClick={() => setEditModal(null)}>cancel</button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {showColPanel && colPanelPos && createPortal(
        <div className="col-panel" style={{ position: "fixed", top: colPanelPos.top, right: colPanelPos.right }} onPointerDown={(e) => e.stopPropagation()}>
          <div className="col-panel__header">columns</div>
          {cols.map((c) => (
            <div key={c.key} className={`col-panel__row${dragOverKey === c.key ? " col-panel__row--over" : ""}`}
              onDragOver={(e) => onDragOver(e, c.key)} onDrop={() => onDrop(c.key)}>
              <span className="col-panel__drag" draggable onDragStart={() => onDragStart(c.key)} onDragEnd={() => { setDragKey(null); setDragOverKey(null); }}>⠿</span>
              <span className="col-panel__label">{c.label}</span>
              <input type="checkbox" className="col-panel__check" checked={c.visible} onChange={() => toggleCol(c.key)} />
            </div>
          ))}
          <button className="col-panel__revert" onClick={() => { saveCols(DEFAULT_COLS); setShowColPanel(false); }}>reset to default</button>
        </div>,
        document.body
      )}
    </div>
  );
}
