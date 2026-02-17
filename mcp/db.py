'''Trino connection and query execution.'''

import os

import pyarrow as pa
import trino
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent / '.env')

TRINO_HOST = os.getenv('TRINO_HOST', 'localhost')
TRINO_PORT = int(os.getenv('TRINO_PORT', '8085'))
TRINO_USER = os.getenv('TRINO_USER', 'admin')
TRINO_CATALOG = os.getenv('TRINO_CATALOG', 'iceberg')
TRINO_SCHEMA = os.getenv('TRINO_SCHEMA', 'silver')


def run_query(sql: str) -> tuple[list, list]:
    '''Execute SQL against Trino. Returns (rows, description).'''
    conn = trino.dbapi.connect(
        host=TRINO_HOST, port=TRINO_PORT, user=TRINO_USER,
        catalog=TRINO_CATALOG, schema=TRINO_SCHEMA,
    )
    cursor = conn.cursor()
    cursor.execute(sql)
    return cursor.fetchall(), cursor.description


def query_to_arrow(sql: str) -> pa.Table:
    '''Execute SQL and return results as a PyArrow table.'''
    rows, desc = run_query(sql)
    columns = [d[0] for d in desc]
    return pa.table({col: [r[i] for r in rows] for i, col in enumerate(columns)})
