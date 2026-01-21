#!/usr/bin/env python3
'''
Setup script for Iceberg catalog namespaces.

Run this before starting Dagster to ensure all required namespaces exist.

Usage:
    uv run python setup.py
'''

import os
from pathlib import Path

from dotenv import load_dotenv
from pyspark.sql import SparkSession

# Load .env from current directory
load_dotenv(Path(__file__).parent / '.env')


def get_spark_session() -> SparkSession:
    '''Create a Spark Connect session.'''
    spark_host = os.environ.get('SPARK_HOST')
    spark_port = os.environ.get('SPARK_PORT')
    remote_url = f'sc://{spark_host}:{spark_port}'

    print(f'Connecting to Spark at {remote_url}...')
    return SparkSession.builder.remote(remote_url).getOrCreate()


def setup_namespaces(spark: SparkSession) -> None:
    '''Create required Iceberg namespaces if they don't exist.'''
    namespaces = ['bronze', 'silver', 'gold']

    for ns in namespaces:
        print(f'Creating namespace: {ns}')
        spark.sql(f'CREATE NAMESPACE IF NOT EXISTS {ns}')

    # List all namespaces to confirm
    print('\nExisting namespaces:')
    result = spark.sql('SHOW NAMESPACES').collect()
    for row in result:
        print(f'  - {row[0]}')


def main() -> None:
    print('=' * 50)
    print('Iceberg Catalog Setup')
    print('=' * 50)

    spark = get_spark_session()

    try:
        setup_namespaces(spark)
        print('\n✓ Setup complete!')
    finally:
        spark.stop()


if __name__ == '__main__':
    main()
