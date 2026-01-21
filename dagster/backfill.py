#!/usr/bin/env python3
'''
Backfill script to process all minute aggregate files.

Usage:
    python backfill.py              # Backfill with current prefix setting
    python backfill.py --list       # Just list available files
    python backfill.py --dry-run    # Show what would be processed
'''

import argparse
import os
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from pyspark.sql import SparkSession
from pyspark.sql.functions import lit

# Load environment from dagster/.env
load_dotenv(Path(__file__).parent / '.env')

# =============================================================================
# CONFIGURATION - Change this to backfill different months
# =============================================================================
BACKFILL_PREFIX = 'us_stocks_sip/minute_aggs_v1/2026/01/'  # January 2026
# =============================================================================


def get_massive_client():
    '''Get S3 client for Massive.'''
    session = boto3.Session(
        aws_access_key_id=os.getenv('MASSIVE_ACCESS_KEY'),
        aws_secret_access_key=os.getenv('MASSIVE_SECRET_KEY'),
    )
    return session.client(
        's3',
        endpoint_url='https://files.massive.com',
        config=Config(signature_version='s3v4'),
    )


def get_spark_session():
    '''Get Spark Connect session.'''
    host = os.getenv('SPARK_HOST', '')
    port = os.getenv('SPARK_PORT', '15002')
    return (
        SparkSession.builder
        .remote(f'sc://{host}:{port}')
        .appName('backfill')
        .getOrCreate()
    )


def list_files(prefix: str) -> list[str]:
    '''List all files under the given prefix.'''
    s3 = get_massive_client()
    paginator = s3.get_paginator('list_objects_v2')
    
    files = []
    for page in paginator.paginate(Bucket='flatfiles', Prefix=prefix):
        for obj in page.get('Contents', []):
            files.append(obj['Key'])
    
    return sorted(files)


def backfill(prefix: str, dry_run: bool = False):
    '''Backfill all files under the given prefix.'''
    file_keys = list_files(prefix)
    
    if not file_keys:
        print(f'No files found with prefix: {prefix}')
        return
    
    print(f'Found {len(file_keys)} files:')
    for f in file_keys:
        print(f'  {f}')
    
    if dry_run:
        print('\n[DRY RUN] Would process the above files.')
        return
    
    print(f'\nProcessing {len(file_keys)} files...\n')
    
    session = get_spark_session()
    
    try:
        for i, file_key in enumerate(file_keys, 1):
            # Extract date from filename: .../2026-01-14.csv.gz -> 2026-01-14
            filename = Path(file_key).name
            date_str = filename.replace('.csv.gz', '')
            
            print(f'[{i}/{len(file_keys)}] {date_str}')
            
            # Read from Massive S3
            s3_path = f's3a://flatfiles/{file_key}'
            df = (
                session.read
                .option('header', 'true')
                .option('inferSchema', 'true')
                .csv(s3_path)
            )
            
            row_count = df.count()
            print(f'  Read {row_count:,} rows')
            
            # Add date partition column
            df = df.withColumn('date', lit(date_str))
            
            # Write to Iceberg
            table_exists = session.catalog.tableExists('iceberg.bronze.minute_aggs')
            
            if not table_exists:
                print('  Creating table...')
                (
                    df.writeTo('iceberg.bronze.minute_aggs')
                    .tableProperty('write.format.default', 'parquet')
                    .tableProperty('write.parquet.compression-codec', 'zstd')
                    .partitionedBy('date')
                    .create()
                )
            else:
                (
                    df.writeTo('iceberg.bronze.minute_aggs')
                    .overwritePartitions()
                )
            
            print(f'  ✓ Written to bronze.minute_aggs')
        
        print(f'\n✓ Backfill complete! Processed {len(file_keys)} files.')
        
    finally:
        session.stop()


def main():
    parser = argparse.ArgumentParser(description='Backfill minute aggregates')
    parser.add_argument('--list', action='store_true', dest='list_only', help='Just list files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    parser.add_argument('--prefix', type=str, default=BACKFILL_PREFIX, help='Override prefix')
    
    args = parser.parse_args()
    
    prefix = args.prefix
    print(f'Using prefix: {prefix}\n')
    
    if args.list_only:
        files = list_files(prefix)
        for f in files:
            print(f)
        print(f'\nTotal: {len(files)} files')
    else:
        backfill(prefix, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
