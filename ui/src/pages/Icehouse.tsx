import NavBar from "../components/NavBar";

export default function Icehouse() {
  return (
    <div className="icehouse-page icehouse-scope">
      <NavBar />
      <div className="icehouse-content">
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: "var(--ice-accent)", letterSpacing: "-0.5px", marginBottom: 4 }}>
            finpipe icehouse
          </h1>
          <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
            historical market data lakehouse — minute-level equity aggregates
          </p>
        </div>

        <div className="icehouse-grid">
          {/* Architecture overview */}
          <div className="icehouse-card">
            <div className="icehouse-card__header">
              <span className="icehouse-card__icon">~</span>
              <span className="icehouse-card__title">architecture</span>
            </div>
            <div className="icehouse-card__body">
              <table className="icehouse-table">
                <tbody>
                  <tr><td>ingestion</td><td>polygon.io via massive s3</td></tr>
                  <tr><td>orchestration</td><td>dagster</td></tr>
                  <tr><td>compute</td><td>apache spark 3.5</td></tr>
                  <tr><td>table format</td><td>apache iceberg</td></tr>
                  <tr><td>catalog</td><td>nessie (git-like)</td></tr>
                  <tr><td>storage</td><td>minio (s3-compatible)</td></tr>
                  <tr><td>query engine</td><td>trino</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Data layers */}
          <div className="icehouse-card">
            <div className="icehouse-card__header">
              <span className="icehouse-card__icon">*</span>
              <span className="icehouse-card__title">data layers</span>
            </div>
            <div className="icehouse-card__body">
              <table className="icehouse-table">
                <thead>
                  <tr><th>layer</th><th>table</th><th>description</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td><span className="layer-badge layer-badge--bronze">bronze</span></td>
                    <td>equity_bronze.minute_aggs</td>
                    <td>raw ohlcv minute bars ingested from massive s3</td>
                  </tr>
                  <tr>
                    <td><span className="layer-badge layer-badge--silver">silver</span></td>
                    <td>equity_silver.minute_aggs</td>
                    <td>enriched with timestamps, session tags, rolling metrics</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Pipeline jobs */}
          <div className="icehouse-card">
            <div className="icehouse-card__header">
              <span className="icehouse-card__icon">|</span>
              <span className="icehouse-card__title">pipeline jobs</span>
            </div>
            <div className="icehouse-card__body">
              <table className="icehouse-table">
                <thead>
                  <tr><th>job</th><th>description</th></tr>
                </thead>
                <tbody>
                  <tr><td>daily_elt_job</td><td>daily ingestion + enrichment</td></tr>
                  <tr><td>backfill_sequential</td><td>historical load, one file at a time</td></tr>
                  <tr><td>backfill_parallel</td><td>historical load, batched</td></tr>
                  <tr><td>silver_ticker_job</td><td>rebuild silver for a specific ticker/date</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Schema: Bronze */}
          <div className="icehouse-card">
            <div className="icehouse-card__header">
              <span className="layer-badge layer-badge--bronze">bronze</span>
              <span className="icehouse-card__title">schema</span>
            </div>
            <div className="icehouse-card__body">
              <table className="icehouse-table">
                <thead>
                  <tr><th>column</th><th>type</th></tr>
                </thead>
                <tbody>
                  <tr><td>ticker</td><td>string</td></tr>
                  <tr><td>open / high / low / close</td><td>double</td></tr>
                  <tr><td>volume</td><td>double</td></tr>
                  <tr><td>window_start</td><td>long (ns)</td></tr>
                  <tr><td>transactions</td><td>long</td></tr>
                  <tr><td>date</td><td>string (partition)</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Schema: Silver */}
          <div className="icehouse-card">
            <div className="icehouse-card__header">
              <span className="layer-badge layer-badge--silver">silver</span>
              <span className="icehouse-card__title">schema (enriched)</span>
            </div>
            <div className="icehouse-card__body">
              <table className="icehouse-table">
                <thead>
                  <tr><th>column</th><th>type</th></tr>
                </thead>
                <tbody>
                  <tr><td>+ timestamp</td><td>string (ET datetime)</td></tr>
                  <tr><td>+ session</td><td>premarket / market / postmarket</td></tr>
                  <tr><td>+ rolling_15m_avg_close</td><td>double</td></tr>
                  <tr><td>+ rolling_15m_avg_volume</td><td>double</td></tr>
                  <tr><td>+ rolling_15m_high</td><td>double</td></tr>
                  <tr><td>+ rolling_15m_low</td><td>double</td></tr>
                  <tr><td>+ rolling_15m_total_volume</td><td>double</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Sensors */}
          <div className="icehouse-card">
            <div className="icehouse-card__header">
              <span className="icehouse-card__icon">@</span>
              <span className="icehouse-card__title">sensors</span>
            </div>
            <div className="icehouse-card__body">
              <table className="icehouse-table">
                <thead>
                  <tr><th>sensor</th><th>interval</th><th>action</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td>daily_massive_s3_sensor</td>
                    <td>5 min</td>
                    <td>watches massive s3 for new files, triggers daily_elt_job</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* MCP */}
          <div className="icehouse-card">
            <div className="icehouse-card__header">
              <span className="icehouse-card__icon">&gt;</span>
              <span className="icehouse-card__title">mcp server</span>
            </div>
            <div className="icehouse-card__body">
              <p style={{ marginBottom: 8 }}>query icehouse data directly from claude desktop via mcp tools.</p>
              <table className="icehouse-table">
                <thead>
                  <tr><th>tool</th><th>params</th><th>output</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td>get_data</td>
                    <td>ticker, days_back, session, format</td>
                    <td>parquet or csv export</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <footer className="statusbar">
        <span className="status-dot dot--blue" />
        <span className="statusbar-label">icehouse</span>
        <span className="statusbar-sep">·</span>
        <span className="statusbar-label">iceberg + nessie + trino</span>
      </footer>
    </div>
  );
}
