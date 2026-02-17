# finpipe

End-to-end stock market data pipeline. Ingests minute-level aggregate data from Polygon.io, processes it through a medallion architecture on Apache Iceberg, and serves it via an MCP server for use in Claude Desktop.

```
Polygon.io S3 ──> Dagster ──> Spark ──> Iceberg (Bronze/Silver) ──> Trino ──> MCP Server ──> Claude Desktop
```

## Tech Stack

- **Orchestration:** Dagster
- **Compute:** Apache Spark (via Spark Connect)
- **Table Format:** Apache Iceberg (Nessie catalog)
- **Storage:** MinIO (S3-compatible)
- **Query Engine:** Trino
- **Serving:** MCP server (Python)

## Project Structure

```
dagster/     # Dagster assets, jobs, sensors, and transforms
lakehouse/   # Docker Compose stack (Spark, MinIO, Nessie, Trino)
mcp/         # MCP server for querying data from Claude Desktop
```

## Setup

### 1. Start the lakehouse

```bash
cd lakehouse
cp .env.example .env  # fill in credentials
docker compose up -d
```

### 2. Run Dagster

```bash
cd dagster
cp .env.example .env  # fill in credentials
uv sync
uv run dagster dev
```

### 3. Run the MCP server

See [mcp/README.md](mcp/README.md) for Claude Desktop configuration.