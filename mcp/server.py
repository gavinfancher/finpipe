#!/usr/bin/env python3
'''MCP Server for exporting finpy silver table data.'''

import json

import pendulum
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from db import query_to_arrow
from export import OUTPUT_DIR, to_parquet, to_csv

server = Server('finpy-data')


def text(obj) -> list[TextContent]:
    return [TextContent(type='text', text=json.dumps(obj, indent=2) if isinstance(obj, dict) else str(obj))]


TOOLS = [
    Tool(
        name='get_data',
        description='Export the last N days of minute-aggregate data for a ticker as parquet or csv.',
        inputSchema={
            'type': 'object',
            'properties': {
                'ticker': {
                    'type': 'string',
                    'description': 'Stock ticker symbol (e.g. SPY, AAPL)'
                },
                'days_back': {
                    'type': 'integer',
                    'description': 'Days back from today (default: 3)',
                    'default': 5
                },
                'format': {'type': 'string',
                'enum': ['parquet', 'csv'],
                'description': 'Output format (default: parquet)',
                'default': 'parquet'
                },
            },
            'required': ['ticker'],
        },
    ),
]


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name != 'get_data':
        return text(f'Unknown tool: {name}')

    ticker = arguments['ticker'].upper()
    days_back = arguments.get('days_back', 3)
    fmt = arguments.get('format', 'parquet')

    end = pendulum.today()
    start = end.subtract(days=days_back)
    start_str = start.format('YYYY-MM-DD')
    end_str = end.format('YYYY-MM-DD')

    sql = (
        f"select * from minute_aggs "
        f"where ticker = '{ticker}' and date >= '{start_str}' and date <= '{end_str}' "
        f"order by window_start"
    )
    table = query_to_arrow(sql)

    if table.num_rows == 0:
        return text(f'No data found for {ticker} in the last {days_back} days.')

    filename = f'{ticker.lower()}_{start_str}_to_{end_str}'
    if fmt == 'csv':
        filepath = to_csv(table, OUTPUT_DIR / f'{filename}.csv')
    else:
        filepath = to_parquet(table, OUTPUT_DIR / f'{filename}.parquet')

    return text({
        'status': 'success',
        'ticker': ticker,
        'date_range': f'{start_str} to {end_str}',
        'rows': table.num_rows,
        'format': fmt,
        'file_path': str(filepath),
        'file_size_mb': round(filepath.stat().st_size / (1024 * 1024), 2),
    })


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
