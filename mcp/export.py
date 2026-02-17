'''Parquet and CSV export logic.'''

import os
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pcsv
import pyarrow.parquet as pq
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

OUTPUT_DIR = Path(os.getenv('MCP_OUTPUT_DIR', '/tmp/finpy_exports'))


def to_parquet(table: pa.Table, path: Path) -> Path:
    '''Write a PyArrow table to parquet. Returns the file path.'''
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)
    return path


def to_csv(table: pa.Table, path: Path) -> Path:
    '''Write a PyArrow table to CSV. Returns the file path.'''
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pcsv.write_csv(table, path)
    return path
