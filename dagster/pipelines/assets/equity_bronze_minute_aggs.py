from pathlib import Path

from dagster import AssetExecutionContext, Config, MaterializeResult, MetadataValue, asset

from ..resources import SparkConnectResource
from ..transforms.ingest_minute_aggs import ingest_minute_agg_file

TABLE = 'iceberg.equity.bronze.minute_aggs'


class MinuteAggsConfig(Config):
    file_key: str
    overwrite: bool = False


@asset(name='bronze_minute_aggs', group_name='bronze', compute_kind='spark')
def bronze_minute_aggs(
    context: AssetExecutionContext,
    config: MinuteAggsConfig,
    spark: SparkConnectResource,
) -> MaterializeResult:
    file_key = config.file_key
    context.log.info(f'Processing file: {file_key}')
    session = spark.get_session()

    row_count = ingest_minute_agg_file(
        spark_session=session,
        file_key=file_key,
        log=context.log.info,
        table=TABLE,
        overwrite=config.overwrite,
    )

    filename = Path(file_key).name
    date_str = filename.replace('.csv.gz', '')

    return MaterializeResult(
        metadata={
            'row_count': MetadataValue.int(int(row_count)),
            'date': MetadataValue.text(date_str),
            'source_file': MetadataValue.text(file_key),
            'table': MetadataValue.text(TABLE),
        }
    )
