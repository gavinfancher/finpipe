'''
iceberg table setup
    - creates namespaces and tables if they don't exist
    - run this before any ingestion jobs
'''

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

TABLES = {
    'iceberg.equity_bronze.minute_aggs': {
        'schema': StructType([
            StructField('ticker', StringType()),
            StructField('volume', DoubleType()),
            StructField('open', DoubleType()),
            StructField('close', DoubleType()),
            StructField('high', DoubleType()),
            StructField('low', DoubleType()),
            StructField('window_start', LongType()),
            StructField('transactions', LongType()),
            StructField('otc', StringType()),
            StructField('date', StringType()),
        ]),
        'partition_by': ['date', 'ticker'],
    },
    'iceberg.equity_silver.minute_aggs': {
        'schema': StructType([
            StructField('ticker', StringType()),
            StructField('volume', DoubleType()),
            StructField('open', DoubleType()),
            StructField('close', DoubleType()),
            StructField('high', DoubleType()),
            StructField('low', DoubleType()),
            StructField('window_start', LongType()),
            StructField('transactions', LongType()),
            StructField('otc', StringType()),
            StructField('date', StringType()),
            StructField('timestamp', StringType()),
            StructField('session', StringType()),
            StructField('rolling_15m_avg_close', DoubleType()),
            StructField('rolling_15m_avg_volume', DoubleType()),
            StructField('rolling_15m_high', DoubleType()),
            StructField('rolling_15m_low', DoubleType()),
            StructField('rolling_15m_total_volume', DoubleType()),
        ]),
        'partition_by': ['date', 'ticker'],
    },
}

NAMESPACES = ['iceberg.equity_bronze', 'iceberg.equity_silver']


def setup_namespaces(session: SparkSession) -> None:
    '''create iceberg namespaces if they don't exist.'''
    for ns in NAMESPACES:
        session.sql(f"create namespace if not exists {ns}")
        print(f'  namespace {ns} ready')


def setup_tables(session: SparkSession) -> None:
    '''create iceberg tables if they don't exist.'''
    for table, config in TABLES.items():
        if session.catalog.tableExists(table):
            print(f'  {table} already exists, skipping')
            continue

        schema = config['schema']
        partition_by = config['partition_by']

        df = session.createDataFrame([], schema)
        writer = (
            df.writeTo(table)
            .tableProperty('write.format.default', 'parquet')
            .tableProperty('write.parquet.compression-codec', 'zstd')
        )
        if partition_by:
            writer = writer.partitionedBy(*partition_by)
        writer.create()
        print(f'  {table} created')


def run_setup() -> None:
    '''connect to spark and set up the warehouse.'''
    from .resources.spark import SparkConnectResource

    spark = SparkConnectResource()
    session = spark.get_session()

    print('setting up namespaces...')
    setup_namespaces(session)

    print('setting up tables...')
    setup_tables(session)

    print('done')


if __name__ == '__main__':
    run_setup()
