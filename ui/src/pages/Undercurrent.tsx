import { useState } from "react";
import NavBar from "../components/NavBar";

type Tab = "signals" | "backtest" | "models";

// Mock data for the UI shell
const MOCK_SIGNALS = [
  { id: 1, ticker: "SPY", direction: "long", confidence: 0.82, strategy: "momentum_15m", timestamp: "14:32:01 ET", status: "active" },
  { id: 2, ticker: "AAPL", direction: "short", confidence: 0.71, strategy: "mean_reversion", timestamp: "14:28:45 ET", status: "active" },
  { id: 3, ticker: "MSFT", direction: "long", confidence: 0.65, strategy: "momentum_15m", timestamp: "13:55:12 ET", status: "expired" },
  { id: 4, ticker: "NVDA", direction: "long", confidence: 0.88, strategy: "volume_breakout", timestamp: "13:41:30 ET", status: "active" },
  { id: 5, ticker: "TSLA", direction: "short", confidence: 0.59, strategy: "mean_reversion", timestamp: "12:15:08 ET", status: "expired" },
];

const MOCK_BACKTESTS = [
  { id: 1, name: "momentum_15m", tickers: "SPY, QQQ", period: "2025-01 → 2025-03", sharpe: 1.42, maxDd: -8.3, winRate: 58.2, trades: 247, status: "complete" },
  { id: 2, name: "mean_reversion", tickers: "AAPL, MSFT, GOOGL", period: "2025-01 → 2025-03", sharpe: 0.91, maxDd: -12.1, winRate: 52.7, trades: 184, status: "complete" },
  { id: 3, name: "volume_breakout", tickers: "NVDA, AMD", period: "2025-02 → 2025-03", sharpe: 1.87, maxDd: -5.6, winRate: 63.1, trades: 89, status: "running" },
];

const MOCK_MODELS = [
  { id: 1, name: "xgb_momentum_v3", type: "xgboost", features: 12, accuracy: 0.67, deployed: true, lastTrained: "2025-03-22" },
  { id: 2, name: "lstm_price_v1", type: "pytorch", features: 8, accuracy: 0.61, deployed: false, lastTrained: "2025-03-20" },
  { id: 3, name: "rf_session_v2", type: "sklearn", features: 15, accuracy: 0.72, deployed: true, lastTrained: "2025-03-23" },
];

export default function Undercurrent() {
  const [activeTab, setActiveTab] = useState<Tab>("signals");

  return (
    <div className="uc-page">
      <NavBar />

      <div className="uc-header">
        <div className="uc-header__left">
          <h1 className="uc-header__title">undercurrent</h1>
          <p className="uc-header__sub">signals, backtesting & models</p>
        </div>
      </div>

      <div className="tab-bar">
        <button className={`tab${activeTab === "signals" ? " tab--active uc-tab-active" : ""}`} onClick={() => setActiveTab("signals")}>live signals</button>
        <button className={`tab${activeTab === "backtest" ? " tab--active uc-tab-active" : ""}`} onClick={() => setActiveTab("backtest")}>backtests</button>
        <button className={`tab${activeTab === "models" ? " tab--active uc-tab-active" : ""}`} onClick={() => setActiveTab("models")}>models</button>
      </div>

      <main className="main-content">
        {activeTab === "signals" && <SignalsPanel />}
        {activeTab === "backtest" && <BacktestPanel />}
        {activeTab === "models" && <ModelsPanel />}
      </main>

      <footer className="statusbar">
        <span className="status-dot" style={{ background: "var(--undercurrent-accent)" }} />
        <span className="statusbar-label">undercurrent</span>
        <span className="statusbar-sep">·</span>
        <span className="statusbar-label">3 active signals · 2 models deployed</span>
      </footer>
    </div>
  );
}

function SignalsPanel() {
  return (
    <div>
      <div className="uc-summary">
        <div className="uc-summary__item">
          <span className="uc-summary__value" style={{ color: "var(--undercurrent-accent)" }}>3</span>
          <span className="uc-summary__label">active signals</span>
        </div>
        <div className="uc-summary__item">
          <span className="uc-summary__value">2</span>
          <span className="uc-summary__label">expired today</span>
        </div>
        <div className="uc-summary__item">
          <span className="uc-summary__value" style={{ color: "var(--green)" }}>73%</span>
          <span className="uc-summary__label">hit rate (7d)</span>
        </div>
      </div>

      <div className="table-wrapper">
        <table className="stock-table">
          <colgroup>
            <col style={{ width: 70 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 120 }} />
            <col style={{ width: 80 }} />
          </colgroup>
          <thead>
            <tr>
              <th className="th">ticker</th>
              <th className="th">direction</th>
              <th className="th th--right">confidence</th>
              <th className="th">strategy</th>
              <th className="th">time</th>
              <th className="th">status</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_SIGNALS.map((s) => (
              <tr key={s.id} className="ticker-row">
                <td className="cell cell--ticker" style={{ color: "var(--undercurrent-accent)" }}>{s.ticker}</td>
                <td className="cell">
                  <span style={{ color: s.direction === "long" ? "var(--green)" : "var(--red)" }}>
                    {s.direction}
                  </span>
                </td>
                <td className="cell cell--num">{(s.confidence * 100).toFixed(0)}%</td>
                <td className="cell" style={{ color: "var(--text-secondary)" }}>{s.strategy}</td>
                <td className="cell" style={{ color: "var(--text-muted)" }}>{s.timestamp}</td>
                <td className="cell">
                  <span className={`uc-status uc-status--${s.status}`}>{s.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BacktestPanel() {
  return (
    <div>
      <div className="uc-summary">
        <div className="uc-summary__item">
          <span className="uc-summary__value">2</span>
          <span className="uc-summary__label">complete</span>
        </div>
        <div className="uc-summary__item">
          <span className="uc-summary__value" style={{ color: "var(--yellow)" }}>1</span>
          <span className="uc-summary__label">running</span>
        </div>
        <div className="uc-actions">
          <button className="btn-primary btn-primary--sm" style={{ background: "var(--undercurrent-accent)" }}>+ new backtest</button>
        </div>
      </div>

      <div className="table-wrapper">
        <table className="stock-table">
          <colgroup>
            <col style={{ width: 140 }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 160 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 70 }} />
            <col style={{ width: 80 }} />
          </colgroup>
          <thead>
            <tr>
              <th className="th">strategy</th>
              <th className="th">tickers</th>
              <th className="th">period</th>
              <th className="th th--right">sharpe</th>
              <th className="th th--right">max dd</th>
              <th className="th th--right">win rate</th>
              <th className="th th--right">trades</th>
              <th className="th">status</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_BACKTESTS.map((b) => (
              <tr key={b.id} className="ticker-row" style={{ cursor: "pointer" }}>
                <td className="cell" style={{ color: "var(--undercurrent-accent)", fontWeight: 700 }}>{b.name}</td>
                <td className="cell" style={{ color: "var(--text-secondary)" }}>{b.tickers}</td>
                <td className="cell" style={{ color: "var(--text-muted)" }}>{b.period}</td>
                <td className="cell cell--num" style={{ color: b.sharpe >= 1 ? "var(--green)" : "var(--text-secondary)" }}>
                  {b.sharpe.toFixed(2)}
                </td>
                <td className="cell cell--num" style={{ color: "var(--red)" }}>{b.maxDd.toFixed(1)}%</td>
                <td className="cell cell--num">{b.winRate.toFixed(1)}%</td>
                <td className="cell cell--num">{b.trades}</td>
                <td className="cell">
                  <span className={`uc-status uc-status--${b.status === "complete" ? "active" : "running"}`}>
                    {b.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Placeholder for equity curve */}
      <div className="uc-chart-placeholder">
        <span className="uc-chart-placeholder__text">equity curve — select a backtest to view</span>
      </div>
    </div>
  );
}

function ModelsPanel() {
  return (
    <div>
      <div className="uc-summary">
        <div className="uc-summary__item">
          <span className="uc-summary__value">3</span>
          <span className="uc-summary__label">models</span>
        </div>
        <div className="uc-summary__item">
          <span className="uc-summary__value" style={{ color: "var(--green)" }}>2</span>
          <span className="uc-summary__label">deployed</span>
        </div>
        <div className="uc-actions">
          <button className="btn-primary btn-primary--sm" style={{ background: "var(--undercurrent-accent)" }}>+ register model</button>
        </div>
      </div>

      <div className="table-wrapper">
        <table className="stock-table">
          <colgroup>
            <col style={{ width: 160 }} />
            <col style={{ width: 90 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 80 }} />
            <col style={{ width: 120 }} />
          </colgroup>
          <thead>
            <tr>
              <th className="th">model</th>
              <th className="th">framework</th>
              <th className="th th--right">features</th>
              <th className="th th--right">accuracy</th>
              <th className="th">deployed</th>
              <th className="th">last trained</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_MODELS.map((m) => (
              <tr key={m.id} className="ticker-row">
                <td className="cell" style={{ color: "var(--undercurrent-accent)", fontWeight: 700 }}>{m.name}</td>
                <td className="cell" style={{ color: "var(--text-secondary)" }}>{m.type}</td>
                <td className="cell cell--num">{m.features}</td>
                <td className="cell cell--num" style={{ color: m.accuracy >= 0.7 ? "var(--green)" : "var(--text-secondary)" }}>
                  {(m.accuracy * 100).toFixed(1)}%
                </td>
                <td className="cell">
                  <span className={`uc-status uc-status--${m.deployed ? "active" : "expired"}`}>
                    {m.deployed ? "live" : "off"}
                  </span>
                </td>
                <td className="cell" style={{ color: "var(--text-muted)" }}>{m.lastTrained}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
