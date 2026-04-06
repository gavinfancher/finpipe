# common — Shared Python Library

Shared constants, schemas, and helpers used by both `backend/` and `dagster/`.
Installed as a uv workspace dependency (`finpipe-common`).

## Modules

- **market.py** — NYSE trading calendar, market status, reference date calculations, Massive API helpers
- **postgres.py** — shared database queries (e.g. `get_all_tickers`)
- **redis_keys.py** — Redis key templates and field name constants
- **schemas.py** — PyArrow schemas and CSV parsing options for bronze data

## Usage

Referenced as a workspace dependency in `backend/pyproject.toml` and `dagster/pyproject.toml`:

```toml
[tool.uv.sources]
finpipe-common = { workspace = true }
```

Then import directly:

```python
from common.market import trading_dates, get_market_status
from common.redis_keys import TICKER_KEY
```
