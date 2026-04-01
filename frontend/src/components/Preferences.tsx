
interface Props {
  available: string[];
  watchlist: string[];
  onChange: (updated: string[]) => void;
  onClose: () => void;
}

export default function Preferences({ available, watchlist, onChange, onClose }: Props) {
  function remove(ticker: string) {
    onChange(watchlist.filter((t) => t !== ticker));
  }

  function toggle(ticker: string) {
    if (watchlist.includes(ticker)) {
      onChange(watchlist.filter((t) => t !== ticker));
    } else {
      onChange([...watchlist, ticker]);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <h2 className="modal-title">watchlist preferences</h2>
          <button className="btn-icon" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Current watchlist */}
        <div className="pref-section">
          <div className="pref-section-header">
            <p className="pref-section-label">your watchlist</p>
            <span className="pref-count">{watchlist.length} tickers</span>
          </div>
          {watchlist.length === 0 ? (
            <p className="no-results">no tickers added yet.</p>
          ) : (
            <div className="ticker-grid">
              {watchlist.map((ticker) => (
                <button
                  key={ticker}
                  className="ticker-chip ticker-chip--selected ticker-chip--removable"
                  onClick={() => remove(ticker)}
                  title="Remove"
                >
                  {ticker}
                  <span className="chip-remove">✕</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="pref-divider" />

        {/* All available tickers */}
        <div className="pref-section">
          <div className="pref-section-header">
            <p className="pref-section-label">all tickers</p>
            <div style={{ display: "flex", gap: "8px" }}>
              <button className="btn-ghost btn-ghost--sm" onClick={() => onChange([...available])}>
                select all
              </button>
              <button className="btn-ghost btn-ghost--sm" onClick={() => onChange([])}>
                clear all
              </button>
            </div>
          </div>
          <div className="ticker-grid">
            {available.map((ticker) => {
              const selected = watchlist.includes(ticker);
              return (
                <button
                  key={ticker}
                  className={`ticker-chip ${selected ? "ticker-chip--selected" : ""}`}
                  onClick={() => toggle(ticker)}
                >
                  {selected && <span className="chip-check">✓</span>}
                  {ticker}
                </button>
              );
            })}
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-primary" onClick={onClose}>done</button>
        </div>
      </div>
    </div>
  );
}
