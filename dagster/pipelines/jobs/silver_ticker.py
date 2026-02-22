from dagster import Config, OpExecutionContext, job, op
from pyspark.sql import functions as F

from ..resources import SparkConnectResource
from ..transforms.enrich_minute_aggs import add_market_session, add_rolling_metrics, add_timestamp
from ..transforms.write import write_to_iceberg

TABLE = 'iceberg.equity_silver.minute_aggs'


class SilverConfig(Config):
    ticker: str = 'AAPL'
    date: str = '2026-01-14'  # YYYY-MM-DD


@op
def build_silver_for_ticker(
    context: OpExecutionContext,
    config: SilverConfig,
    spark: SparkConnectResource,
) -> None:
    session = spark.get_session()
    ticker = config.ticker.upper()
    date = config.date

    context.log.info(f'Building silver for {ticker} on {date}')

    df = (
        session.table('iceberg.equity_bronze.minute_aggs')
        .filter(F.col('ticker') == ticker)
        .filter(F.col('date') == date)
    )

    row_count = df.count()
    if row_count == 0:
        context.log.warning(f'No data found for {ticker} on {date}')
        return

    context.log.info(f'Found {row_count:,} rows')

    df = add_timestamp(df)
    df = add_market_session(df)
    df = add_rolling_metrics(df)

    write_to_iceberg(session, df, TABLE)
    context.log.info(f'Written {row_count:,} rows to {TABLE}')


@job
def silver_ticker_job():
    build_silver_for_ticker()
