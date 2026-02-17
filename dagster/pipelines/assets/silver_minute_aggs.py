from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from ..resources import SparkConnectResource
from ..transforms.enrich_minute_aggs import add_market_session, add_rolling_metrics, add_timestamp
from ..transforms.write import write_to_iceberg

TABLE = 'iceberg.silver.minute_aggs'


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

    df = add_timestamp(df)
    df = add_market_session(df)
    df = add_rolling_metrics(df)

    write_to_iceberg(session, df, TABLE)

    row_count = df.count()
    context.log.info(f'Written {row_count:,} rows to {TABLE}')

    return MaterializeResult(
        metadata={
            'row_count': MetadataValue.int(row_count),
            'table': MetadataValue.text(TABLE),
        }
    )
