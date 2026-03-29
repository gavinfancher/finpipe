import { Link } from "react-router-dom";
import NavBar from "../components/NavBar";
import { getCurrentUsername } from "../store/userStore";

export default function Home() {
  const user = getCurrentUsername();

  return (
    <div className="home-page">
      <NavBar />
      <div className="home-hero">
        <h1 className="home-hero__title">finpipe</h1>
        <p className="home-hero__sub">
          an end-to-end market data platform. ingest, process, and stream
          real-time and historical equity data through a modern lakehouse
          architecture.
        </p>

        <div className="home-hero__actions">
          {user ? (
            <Link to="/dashboard" className="btn-primary">open dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="btn-primary">sign in</Link>
              <Link to="/register" className="btn-ghost">request access</Link>
            </>
          )}
        </div>

        <div className="home-products">
          <Link to="/faucet" className="product-card">
            <span className="product-card__icon">~</span>
            <span className="product-card__name product-card__name--faucet">finpipe faucet</span>
            <span className="product-card__desc">
              real-time equity price streaming. watchlists, position tracking,
              and live p/l — powered by websocket feeds from the massive api.
            </span>
          </Link>
          <Link to="/icehouse" className="product-card">
            <span className="product-card__icon">*</span>
            <span className="product-card__name product-card__name--ice">finpipe icehouse</span>
            <span className="product-card__desc">
              historical market data lakehouse. minute-level aggregates ingested
              through dagster, processed via spark, stored in apache iceberg tables.
            </span>
          </Link>
          <Link to="/analyst" className="product-card">
            <span className="product-card__icon">&gt;_</span>
            <span className="product-card__name product-card__name--analyst">finpipe analyst</span>
            <span className="product-card__desc">
              ai analyst powered by claude, openai, or gemini. query your icehouse
              data with natural language — no sql required.
            </span>
          </Link>
          <Link to="/weather" className="product-card">
            <span className="product-card__icon">~</span>
            <span className="product-card__name product-card__name--weather">finpipe weather</span>
            <span className="product-card__desc">
              real-time US weather data powered by the national weather service.
              ask about forecasts, alerts, and conditions with structured MCP tool calls.
            </span>
          </Link>
          <Link to="/undercurrent" className="product-card">
            <span className="product-card__icon">%</span>
            <span className="product-card__name product-card__name--undercurrent">finpipe undercurrent</span>
            <span className="product-card__desc">
              ml signals and backtesting. build strategies, test against history,
              and monitor live signals in real-time.
            </span>
          </Link>
        </div>
      </div>
      <footer className="home-footer">finpipe &middot; built with dagster, spark, iceberg, and too much caffeine</footer>
    </div>
  );
}
