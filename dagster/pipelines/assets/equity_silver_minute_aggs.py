from dagster import AssetExecutionContext, MaterializeResult, MetadataValue, asset

from ..resources import SparkConnectResource
from ..transforms.enrich_minute_aggs import add_market_session, add_timestamp
from ..transforms.write import write_to_iceberg


SOURCE_TABLE = 'iceberg.equity_bronze.minute_aggs'
TARGET_TABLE = 'iceberg.equity_silver.minute_aggs'


@asset(
    name='equity_silver_minute_aggs',
    group_name='silver',
    compute_kind='spark',
    deps=['equity_bronze_minute_aggs']
)
def equity_silver_minute_aggs(
    context: AssetExecutionContext,
    spark: SparkConnectResource,
) -> MaterializeResult:
    spark_session = spark.get_session()
    df = spark_session.table(SOURCE_TABLE)

    df = add_timestamp(df)
    df = add_market_session(df)

    write_to_iceberg(spark_session, df, TARGET_TABLE)

    row_count = df.count()
    context.log.info(f'wrote {row_count:,} rows to {TARGET_TABLE}')

    return MaterializeResult(
        metadata={
            'row_count': MetadataValue.int(row_count),
            'table': MetadataValue.text(TARGET_TABLE),
        }
    )
