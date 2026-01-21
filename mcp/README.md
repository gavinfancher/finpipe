# finpy MCP Server

MCP server for querying finpy silver tables from Claude Desktop.

## Setup (on your Mac)

### 1. Clone and install

```bash
# Clone the repo (or copy this mcp/ directory)
cd ~/projects/finpy/mcp

# Install with uv
uv sync
```

### 2. Configure environment

The server connects to your remote Trino instance. Set environment variables:

```bash
export TRINO_HOST="your-server-ip"  # e.g., 192.168.1.100
export TRINO_PORT="8085"
export MCP_OUTPUT_DIR="/tmp/finpy_exports"  # where parquet files are saved
```

### 3. Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "finpy-data": {
      "command": "uv",
      "args": ["--directory", "/path/to/finpy/mcp", "run", "python", "server.py"],
      "env": {
        "TRINO_HOST": "your-server-ip",
        "TRINO_PORT": "8085",
        "MCP_OUTPUT_DIR": "/tmp/finpy_exports"
      }
    }
  }
}
```

### 4. Restart Claude Desktop

Quit and reopen Claude Desktop. You should see the finpy-data tools available.

## Available Tools

| Tool | Description |
|------|-------------|
| `query_ticker` | Query summary stats for a ticker and date range |
| `export_parquet` | Export data to .parquet file, returns file path |
| `list_available_tickers` | List all tickers with row counts |
| `get_date_range` | Show available date range in the data |

## Example Prompts

```
"Get me SPY data for the last 3 days as a parquet file"

"What tickers do you have available?"

"Export AAPL market hours only for January 15-17 2026"

"Show me the date range available in the data"
```

## Network Setup

Make sure your Mac can reach the Trino port on your server:

```bash
# Test connection
nc -zv your-server-ip 8085

# If using SSH tunnel
ssh -L 8085:localhost:8085 user@your-server
```

If tunneling, set `TRINO_HOST=localhost` in the config.

## Troubleshooting

### "Connection refused"

- Check Trino is running: `docker compose ps` on the server
- Check firewall allows port 8085
- Try SSH tunnel if direct connection fails

### "Table not found"

- Make sure silver table exists: run silver_ticker_job in Dagster first
- Check catalog/schema: should be `iceberg.silver.minute_aggs`

### Test the server manually

```bash
cd /path/to/finpy/mcp
uv run python -c "
from server import get_trino_connection
conn = get_trino_connection()
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM minute_aggs')
print(cursor.fetchone())
"
```
