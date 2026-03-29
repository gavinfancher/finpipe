import { Link, useNavigate } from "react-router-dom";
import NavBar from "../components/NavBar";
import { getCurrentUsername, getToken } from "../store/userStore";
import { useEffect } from "react";
import { featureEnabled } from "../config/gates";

export default function Dashboard() {
  const navigate = useNavigate();
  const user = getCurrentUsername();
  const token = getToken();

  useEffect(() => {
    if (!user || !token) navigate("/login");
  }, [user, token, navigate]);

  if (!user) return null;

  return (
    <div className="dash-page">
      <NavBar />
      <div className="dash-content">
        <div className="dash-header">
          <h1 className="dash-header__greeting">welcome back, <span className="dash-header__user">{user}</span></h1>
          <p className="dash-header__sub">your finpipe workspace</p>
        </div>

        <div className="dash-grid">
          {/* Faucet */}
          <Link to="/faucet" className="dash-card">
            <div className="dash-card__top">
              <span className="dash-card__icon">~</span>
              <span className="dash-card__name" style={{ color: "var(--faucet-accent)" }}>faucet</span>
            </div>
            <p className="dash-card__desc">
              real-time streaming dashboard. watchlists, positions, and live p/l.
            </p>
            <div className="dash-card__footer">
              <span className="dash-card__tag">live data</span>
              <span className="dash-card__tag">websocket</span>
            </div>
          </Link>

          {/* Icehouse */}
          <Link to="/icehouse" className="dash-card">
            <div className="dash-card__top">
              <span className="dash-card__icon">*</span>
              <span className="dash-card__name" style={{ color: "var(--ice-accent)" }}>icehouse</span>
            </div>
            <p className="dash-card__desc">
              historical data lakehouse. browse schemas, pipeline jobs, and table metadata.
            </p>
            <div className="dash-card__footer">
              <span className="dash-card__tag">iceberg</span>
              <span className="dash-card__tag">trino</span>
            </div>
          </Link>

          {/* Analyst */}
          <Link to="/analyst" className="dash-card">
            <div className="dash-card__top">
              <span className="dash-card__icon">&gt;_</span>
              <span className="dash-card__name" style={{ color: "var(--analyst-accent)" }}>analyst</span>
            </div>
            <p className="dash-card__desc">
              ai-powered data analyst. query your lakehouse with natural language.
            </p>
            <div className="dash-card__footer">
              <span className="dash-card__tag">claude</span>
              <span className="dash-card__tag">openai</span>
              <span className="dash-card__tag">gemini</span>
            </div>
          </Link>

          {/* Weather */}
          <Link to="/weather" className="dash-card">
            <div className="dash-card__top">
              <span className="dash-card__icon">~</span>
              <span className="dash-card__name" style={{ color: "var(--weather-accent)" }}>weather</span>
            </div>
            <p className="dash-card__desc">
              real-time US weather data. forecasts, alerts, and conditions via MCP tool calls.
            </p>
            <div className="dash-card__footer">
              <span className="dash-card__tag">mcp</span>
              <span className="dash-card__tag">nws api</span>
              <span className="dash-card__tag">claude</span>
            </div>
          </Link>

          {/* Undercurrent */}
          <Link to="/undercurrent" className="dash-card">
            <div className="dash-card__top">
              <span className="dash-card__icon">%</span>
              <span className="dash-card__name" style={{ color: "var(--undercurrent-accent)" }}>undercurrent</span>
            </div>
            <p className="dash-card__desc">
              ml signals and backtesting. build strategies, test against history, monitor live.
            </p>
            <div className="dash-card__footer">
              <span className="dash-card__tag">backtest</span>
              <span className="dash-card__tag">signals</span>
              <span className="dash-card__tag">models</span>
            </div>
          </Link>
        </div>

        <div className="dash-section">
          <h2 className="dash-section__title">quick actions</h2>
          <div className="dash-actions">
            <Link to="/faucet" className="dash-action">open watchlist</Link>
            <Link to="/analyst" className="dash-action">ask the analyst</Link>
            <Link to="/weather" className="dash-action">check weather</Link>
            <Link to="/undercurrent" className="dash-action">view signals</Link>
            <Link to="/icehouse" className="dash-action">browse schemas</Link>
            {featureEnabled("admin") && (
              <Link to="/admin" className="dash-action">admin console</Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
