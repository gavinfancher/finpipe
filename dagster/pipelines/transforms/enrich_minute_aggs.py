"""Silver enrichment: timestamp conversion, session classification, rolling metrics."""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def rolling_window(partition_cols, order_col, rows_back):
    """Create a Spark window spec for rolling calculations."""
    return (
        Window.partitionBy(*partition_cols)
        .orderBy(order_col)
        .rowsBetween(-rows_back, 0)
    )


def add_timestamp(df: DataFrame) -> DataFrame:
    """Convert nanosecond window_start to Eastern Time timestamp."""
    return df.withColumn(
        'timestamp',
        F.from_utc_timestamp((F.col('window_start') / 1e9).cast('timestamp'), 'America/New_York')
    )


def add_market_session(df: DataFrame) -> DataFrame:
    """Classify each bar as premarket, market, postmarket, or closed."""
    time_minutes = F.hour('timestamp') * 60 + F.minute('timestamp')
    return df.withColumn(
        'session',
        F.when((time_minutes >= 4 * 60) & (time_minutes < 9 * 60 + 30), 'premarket')
        .when((time_minutes >= 9 * 60 + 30) & (time_minutes < 16 * 60), 'market')
        .when((time_minutes >= 16 * 60) & (time_minutes < 20 * 60), 'postmarket')
        .otherwise('closed')
    )


def add_rolling_metrics(df: DataFrame) -> DataFrame:
    """Add 15-minute rolling window metrics (within same ticker + date)."""
    win_15 = rolling_window(['ticker', 'date'], 'timestamp', 14)  # current + 14 prior = 15 bars

    return (
        df.withColumn('rolling_15m_avg_close', F.avg('close').over(win_15))
        .withColumn('rolling_15m_avg_volume', F.avg('volume').over(win_15))
        .withColumn('rolling_15m_high', F.max('high').over(win_15))
        .withColumn('rolling_15m_low', F.min('low').over(win_15))
        .withColumn('rolling_15m_total_volume', F.sum('volume').over(win_15))
    )
