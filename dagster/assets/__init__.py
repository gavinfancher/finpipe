"""Asset definitions for finpipe-dagster."""

from .bronze_minute_aggs import bronze_minute_aggs
from .silver_minute_aggs import silver_minute_aggs

all_assets = [bronze_minute_aggs, silver_minute_aggs]
