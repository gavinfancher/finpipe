"""
Redis key patterns and field constants shared across backend and dagster.
"""

# Single hash per ticker — 20 fields max
# ticker:{TICKER} = {price, change, changePct, volume, timestamp,
#                     prevClose,
#                     perf5d, perf1m, perf3m, perf6m, perf1y, perfYtd, perf3y,
#                     ref5d, ref1m, ref3m, ref6m, ref1y, refYtd, ref3y}
TICKER_KEY = "ticker:{}"

# UI-facing perf field names
PERF_FIELDS = ("perf5d", "perf1m", "perf3m", "perf6m", "perf1y", "perfYtd", "perf3y")

# Reference close field names (stored in same hash for live recomputation)
REF_FIELDS = ("ref5d", "ref1m", "ref3m", "ref6m", "ref1y", "refYtd", "ref3y")

# Close-of-day label → ref field mapping
LABEL_TO_REF = dict(zip(
    ("5d", "1m", "3m", "6m", "1y", "ytd", "3y"),
    REF_FIELDS,
))

# Control plane
ASSIGNMENTS_KEY = "ticker:assignments"
NODE_COUNT_KEY = "control:node_count"
CHANNEL = "control:assignments"
