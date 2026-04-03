"""
Redis key patterns and field constants shared across backend and dagster.
"""

# Tick data cache
PREV_CLOSE_KEY = "ticker:prev_close:{}"
PERF_KEY = "ticker:perf:{}"
PRICE_KEY = "ticker:prices:{}"

# Control plane
ASSIGNMENTS_KEY = "ticker:assignments"
NODE_COUNT_KEY = "control:node_count"
CHANNEL = "control:assignments"

# Perf field names (UI-facing) mapped to Redis hash fields (close reference labels)
PERF_FIELDS = ("perf5d", "perf1m", "perf3m", "perf6m", "perf1y", "perfYtd", "perf3y")
CLOSE_FIELDS = ("5d", "1m", "3m", "6m", "1y", "ytd", "3y")
