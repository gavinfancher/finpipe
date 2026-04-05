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
          an end-to-end financial data platform. ingest, process, and stream
          real-time and historical equity data through a modern lakehouse
          architecture.
        </p>

        <div className="home-sections">
          <div className="home-section">
            <h2 className="home-section__title">batch ingestion</h2>
            <p className="home-section__desc">
              historical equity and options data from the massive api. concurrent
              workers on ec2 spot instances stream through pyarrow, stage as
              parquet on s3, and commit to iceberg tables via emr serverless.
            </p>
          </div>
          <div className="home-section">
            <h2 className="home-section__title">real-time streaming</h2>
            <p className="home-section__desc">
              live tick data from massive websocket feeds. enriched with
              historical reference prices across multiple timeframes and
              broadcast to connected clients over websocket.
            </p>
          </div>
          <div className="home-section">
            <h2 className="home-section__title">orchestration</h2>
            <p className="home-section__desc">
              dagster manages pipeline execution — sensors watch for new data,
              jobs handle backfills, and the platform provisions and tears down
              cloud resources automatically.
            </p>
          </div>
        </div>

        <div className="home-demo-cta">
          <Link to="/demo" className="btn-primary btn-primary--lg">open demo</Link>
          <p className="home-demo-cta__sub">live market data — no account required</p>
        </div>

        <div className="home-links">
          <Link to="/learn" className="home-link-card">
            <h3 className="home-link-card__title">learn more</h3>
            <p className="home-link-card__desc">
              how the platform works — ingestion, lakehouse, streaming, and the full stack.
            </p>
          </Link>
          <Link to="/blog" className="home-link-card">
            <h3 className="home-link-card__title">blog</h3>
            <p className="home-link-card__desc">
              engineering decisions and architectural trade-offs behind finpipe.
            </p>
          </Link>
        </div>

        {user && (
          <div className="home-hero__actions">
            <Link to="/dashboard" className="btn-primary">open dashboard</Link>
          </div>
        )}
      </div>
      <footer className="home-footer">
        finpipe&trade; &middot; built by <a href="https://gavinfancher.com" target="_blank" rel="noopener noreferrer">gavin fancher</a> with too much caffeine
      </footer>
    </div>
  );
}
