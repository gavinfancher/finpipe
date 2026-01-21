from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from ..resources import SparkConnectResource


# 15-minute rolling window within same day, ordered by time
def rolling_window(partition_cols, order_col, rows_back):
    return (
        Window.partitionBy(*partition_cols)
        .orderBy(order_col)
        .rowsBetween(-rows_back, 0)
    )


@asset(
    name='silver_minute_aggs',
    group_name='silver',
    compute_kind='spark',
    deps=['bronze_minute_aggs']
)
def silver_minute_aggs(
    context: AssetExecutionContext,
    spark: SparkConnectResource,
) -> MaterializeResult:
    session = spark.get_session()
    df = session.table('iceberg.bronze.minute_aggs')

    # Convert nanosecond timestamp to Eastern Time
    df = df.withColumn(
        'timestamp',
        F.from_utc_timestamp((F.col('window_start') / 1e9).cast('timestamp'), 'America/New_York')
    )

    # Market session enum: premarket, market, postmarket
    time_minutes = F.hour('timestamp') * 60 + F.minute('timestamp')
    df = df.withColumn(
        'session',
        F.when((time_minutes >= 4 * 60) & (time_minutes < 9 * 60 + 30), 'premarket')
        .when((time_minutes >= 9 * 60 + 30) & (time_minutes < 16 * 60), 'market')
        .when((time_minutes >= 16 * 60) & (time_minutes < 20 * 60), 'postmarket')
        .otherwise('closed')
    )

    # 15-minute rolling metrics (within same ticker + date)
    win_15 = rolling_window(['ticker', 'date'], 'timestamp', 14)  # current + 14 prior = 15 bars

    df = (
        df.withColumn('rolling_15m_avg_close', F.avg('close').over(win_15))
        .withColumn('rolling_15m_avg_volume', F.avg('volume').over(win_15))
        .withColumn('rolling_15m_high', F.max('high').over(win_15))
        .withColumn('rolling_15m_low', F.min('low').over(win_15))
        .withColumn('rolling_15m_total_volume', F.sum('volume').over(win_15))
    )

    # Write to silver table
    table_name = 'iceberg.silver.minute_aggs'
    table_exists = session.catalog.tableExists(table_name)

    if not table_exists:
        context.log.info('Creating silver.minute_aggs table...')
        (
            df.writeTo(table_name)
            .tableProperty('write.format.default', 'parquet')
            .tableProperty('write.parquet.compression-codec', 'zstd')
            .partitionedBy('date')
            .create()
        )
    else:
        context.log.info('Appending to silver.minute_aggs...')
        df.writeTo(table_name).append()

    row_count = df.count()
    context.log.info(f'Written {row_count:,} rows to silver.minute_aggs')

    return MaterializeResult(
        metadata={
            'row_count': MetadataValue.int(row_count),
            'table': MetadataValue.text(table_name),
        }
    )
