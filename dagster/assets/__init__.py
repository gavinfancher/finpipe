"""Asset definitions for finpipe-dagster."""

from .bronze_minute_aggs import bronze_minute_aggs
from .close_of_day import reference_closes, ticker_cache
from .silver_minute_aggs import silver_minute_aggs

all_assets = [
    bronze_minute_aggs,
    reference_closes,
    ticker_cache,
    silver_minute_aggs,
]
