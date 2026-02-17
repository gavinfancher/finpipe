from datetime import datetime
from pathlib import Path

from dagster import AssetExecutionContext, Config, MaterializeResult, MetadataValue, asset

from ..resources import MassiveS3Resource, SparkConnectResource
from ..transforms.ingest_minute_aggs import ingest_minute_agg_file


class MinuteAggsConfig(Config):
    file_key: str = ''
    overwrite: bool = False


@asset(name='bronze_minute_aggs', group_name='bronze', compute_kind='spark')
def bronze_minute_aggs(
    context: AssetExecutionContext,
    config: MinuteAggsConfig,
    massive_s3: MassiveS3Resource,
    spark: SparkConnectResource,
) -> MaterializeResult:
    file_key = config.file_key
    if not file_key:
        now = datetime.now()
        prefix = f'us_stocks_sip/minute_aggs_v1/{now.year}/{now.month:02d}/'
        client = massive_s3.get_client()
        response = client.list_objects_v2(Bucket=massive_s3.bucket, Prefix=prefix)
        objects = response.get('Contents', [])
        if not objects:
            context.log.warning('No minute agg files found')
            return MaterializeResult(metadata={'status': MetadataValue.text('no_files')})
        file_key = sorted([o['Key'] for o in objects])[-1]

    context.log.info(f'Processing file: {file_key}')
    session = spark.get_session()

    row_count = ingest_minute_agg_file(
        session=session,
        file_key=file_key,
        log=context.log.info,
        overwrite=config.overwrite,
    )

    filename = Path(file_key).name
    date_str = filename.replace('.csv.gz', '')

    return MaterializeResult(
        metadata={
            'row_count': MetadataValue.int(int(row_count)),
            'date': MetadataValue.text(date_str),
            'source_file': MetadataValue.text(file_key),
            'table': MetadataValue.text('iceberg.bronze.minute_aggs'),
        }
    )
