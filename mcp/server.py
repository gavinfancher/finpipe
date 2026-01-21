#!/usr/bin/env python3
"""
MCP Server for querying finpy silver tables.

Run on your Mac, connects to remote Trino instance.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import trino
import pyarrow as pa
import pyarrow.parquet as pq
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configuration - set these environment variables or edit defaults
TRINO_HOST = os.getenv("TRINO_HOST", "localhost")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8085"))
TRINO_USER = os.getenv("TRINO_USER", "admin")
OUTPUT_DIR = Path(os.getenv("MCP_OUTPUT_DIR", "/tmp/finpy_exports"))

server = Server("finpy-data")


def get_trino_connection():
    return trino.dbapi.connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        catalog="iceberg",
        schema="silver",
    )


def query_to_arrow(sql: str) -> pa.Table:
    """Execute SQL and return as PyArrow table."""
    conn = get_trino_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    # Convert to PyArrow
    data = {col: [row[i] for row in rows] for i, col in enumerate(columns)}
    return pa.table(data)


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="query_ticker",
            description="Query minute aggregates for a ticker and date range from the silver table. Returns summary stats.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., SPY, AAPL, MSFT)"
                    },
                    "days_back": {
                        "type": "integer",
                        "description": "Number of days back from today (default: 3)",
                        "default": 3
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date YYYY-MM-DD (optional, overrides days_back)"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date YYYY-MM-DD (optional, defaults to today)"
                    }
                },
                "required": ["ticker"]
            }
        ),
        Tool(
            name="export_parquet",
            description="Export ticker data to a .parquet file. Returns the file path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol"
                    },
                    "days_back": {
                        "type": "integer",
                        "description": "Number of days back from today (default: 3)",
                        "default": 3
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start date YYYY-MM-DD (optional)"
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End date YYYY-MM-DD (optional)"
                    },
                    "session_filter": {
                        "type": "string",
                        "description": "Filter by market session: premarket, market, postmarket (optional)"
                    }
                },
                "required": ["ticker"]
            }
        ),
        Tool(
            name="list_available_tickers",
            description="List all tickers available in the silver table with row counts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max tickers to return (default: 50)",
                        "default": 50
                    }
                }
            }
        ),
        Tool(
            name="get_date_range",
            description="Get the available date range in the silver table.",
            inputSchema={"type": "object", "properties": {}}
        ),
    ]


def resolve_dates(days_back: int = 3, start_date: str = None, end_date: str = None):
    """Resolve date range from parameters."""
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end = datetime.now().date()
    
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start = end - timedelta(days=days_back)
    
    return start, end


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    
    if name == "query_ticker":
        ticker = arguments["ticker"].upper()
        start, end = resolve_dates(
            arguments.get("days_back", 3),
            arguments.get("start_date"),
            arguments.get("end_date")
        )
        
        sql = f"""
            SELECT 
                COUNT(*) as row_count,
                MIN(timestamp) as first_timestamp,
                MAX(timestamp) as last_timestamp,
                MIN(low) as period_low,
                MAX(high) as period_high,
                AVG(close) as avg_close,
                SUM(volume) as total_volume
            FROM minute_aggs
            WHERE ticker = '{ticker}'
              AND date >= '{start}'
              AND date <= '{end}'
        """
        
        conn = get_trino_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        
        if not row or row[0] == 0:
            return [TextContent(type="text", text=f"No data found for {ticker} between {start} and {end}")]
        
        result = {
            "ticker": ticker,
            "date_range": f"{start} to {end}",
            "row_count": row[0],
            "first_timestamp": str(row[1]),
            "last_timestamp": str(row[2]),
            "period_low": float(row[3]) if row[3] else None,
            "period_high": float(row[4]) if row[4] else None,
            "avg_close": round(float(row[5]), 2) if row[5] else None,
            "total_volume": int(row[6]) if row[6] else None,
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "export_parquet":
        ticker = arguments["ticker"].upper()
        start, end = resolve_dates(
            arguments.get("days_back", 3),
            arguments.get("start_date"),
            arguments.get("end_date")
        )
        session_filter = arguments.get("session_filter")
        
        sql = f"""
            SELECT *
            FROM minute_aggs
            WHERE ticker = '{ticker}'
              AND date >= '{start}'
              AND date <= '{end}'
        """
        
        if session_filter:
            sql += f" AND session = '{session_filter}'"
        
        sql += " ORDER BY timestamp"
        
        table = query_to_arrow(sql)
        
        if table.num_rows == 0:
            return [TextContent(type="text", text=f"No data found for {ticker} between {start} and {end}")]
        
        # Create output directory
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        filename = f"{ticker.lower()}_{start}_to_{end}.parquet"
        filepath = OUTPUT_DIR / filename
        
        # Write parquet
        pq.write_table(table, filepath)
        
        result = {
            "status": "success",
            "ticker": ticker,
            "date_range": f"{start} to {end}",
            "rows_exported": table.num_rows,
            "file_path": str(filepath),
            "file_size_mb": round(filepath.stat().st_size / (1024 * 1024), 2)
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    elif name == "list_available_tickers":
        limit = arguments.get("limit", 50)
        
        sql = f"""
            SELECT ticker, COUNT(*) as row_count
            FROM minute_aggs
            GROUP BY ticker
            ORDER BY row_count DESC
            LIMIT {limit}
        """
        
        conn = get_trino_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        
        tickers = [{"ticker": row[0], "row_count": row[1]} for row in rows]
        
        return [TextContent(type="text", text=json.dumps({"tickers": tickers}, indent=2))]
    
    elif name == "get_date_range":
        sql = """
            SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(DISTINCT date) as days
            FROM minute_aggs
        """
        
        conn = get_trino_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        
        result = {
            "min_date": str(row[0]),
            "max_date": str(row[1]),
            "total_days": row[2]
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
