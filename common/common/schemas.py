"""
PyArrow schemas for the finpipe data lakehouse.
"""

import pyarrow as pa
import pyarrow.csv as pa_csv

BRONZE_SCHEMA = pa.schema([
    ("ticker", pa.string()),
    ("volume", pa.float64()),
    ("open", pa.float64()),
    ("close", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("window_start", pa.int64()),
    ("transactions", pa.int64()),
    ("otc", pa.string()),
    ("date", pa.string()),
])

MASSIVE_COLUMNS = [
    "ticker", "volume", "open", "close", "high", "low",
    "window_start", "transactions", "otc",
]

CSV_CONVERT_OPTS = pa_csv.ConvertOptions(
    column_types={
        "ticker": pa.string(),
        "volume": pa.float64(),
        "open": pa.float64(),
        "close": pa.float64(),
        "high": pa.float64(),
        "low": pa.float64(),
        "window_start": pa.int64(),
        "transactions": pa.int64(),
        "otc": pa.string(),
    },
)

CSV_READ_OPTS = pa_csv.ReadOptions(block_size=1 << 20)  # 1 MB read blocks
