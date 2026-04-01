'''
Parallel vs sequential backfill — download from Massive S3 → write parquet to S3.

Usage:
    uv run python main.py --year 2026 --months 3 --mode concurrent --workers 16
    uv run python main.py --year 2026 --months 3 --mode sequential
    uv run python main.py --year 2026 --months 3 --dry-run

Uses streaming decompression — S3 response streams through gzip into PyArrow's
CSV reader. Never holds the full compressed or decompressed file in memory.
Only the final Arrow columnar table is materialized. Scales to multi-GB files.
'''

import argparse
import gzip
import io
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq
from botocore.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
log = logging.getLogger(__name__)

BRONZE_SCHEMA = pa.schema([
    ('ticker', pa.string()),
    ('volume', pa.float64()),
    ('open', pa.float64()),
    ('close', pa.float64()),
    ('high', pa.float64()),
    ('low', pa.float64()),
    ('window_start', pa.int64()),
    ('transactions', pa.int64()),
    ('otc', pa.string()),
    ('date', pa.string()),
])

MASSIVE_COLUMNS = [
    'ticker', 'volume', 'open', 'close', 'high', 'low',
    'window_start', 'transactions', 'otc',
]

# tell pyarrow the column types upfront — skips type inference on every file
CSV_CONVERT_OPTS = pa_csv.ConvertOptions(
    column_types={
        'ticker': pa.string(),
        'volume': pa.float64(),
        'open': pa.float64(),
        'close': pa.float64(),
        'high': pa.float64(),
        'low': pa.float64(),
        'window_start': pa.int64(),
        'transactions': pa.int64(),
        'otc': pa.string(),
    },
)

# only read the columns we need — skip any extras Massive includes
CSV_READ_OPTS = pa_csv.ReadOptions(block_size=1 << 20)  # 1 MB read blocks

PREFIX = 'us_stocks_sip/minute_aggs_v1'
MAX_RETRIES = 3


SECRET_NAME = 'finpipe/massive'


def load_credentials():
    """Load Massive API creds from Secrets Manager, fall back to .env for local dev."""
    try:
        sm = boto3.client('secretsmanager', region_name='us-east-1')
        resp = sm.get_secret_value(SecretId=SECRET_NAME)
        import json
        secret = json.loads(resp['SecretString'])
        os.environ.setdefault('MASSIVE_ACCESS_KEY', secret['access_key'])
        os.environ.setdefault('MASSIVE_SECRET_KEY', secret['secret_key'])
        log.info('loaded credentials from Secrets Manager')
        return
    except Exception:
        pass

    # fallback: .env file for local dev
    path = Path('.env')
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip())
    log.info('loaded credentials from .env')


def make_massive_client(session):
    return session.client(
        's3',
        endpoint_url='https://files.massive.com',
        config=Config(signature_version='s3v4'),
    )


def list_keys(client, bucket, prefix):
    keys = []
    paginator = client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(obj['Key'] for obj in page.get('Contents', []))
    return sorted(keys)


def build_manifest(massive_client, year, months):
    all_keys = []
    for month in months:
        prefix = f'{PREFIX}/{year}/{month:02d}/'
        keys = list_keys(massive_client, 'flatfiles', prefix)
        log.info(f'found {len(keys)} files for {year}/{month:02d}')
        all_keys.extend(keys)
    return all_keys


def cast_to_schema(table, date_str):
    columns = {}
    for col in MASSIVE_COLUMNS:
        if col in table.column_names:
            columns[col] = table.column(col)
        else:
            columns[col] = pa.nulls(len(table), type=BRONZE_SCHEMA.field(col).type)
    columns['date'] = pa.array([date_str] * len(table), type=pa.string())
    return pa.table(columns).cast(BRONZE_SCHEMA)


def stream_and_parse(file_key, massive_client):
    '''Stream S3 → gzip decompress → Arrow CSV parse. Never holds full file in memory.'''
    resp = massive_client.get_object(Bucket='flatfiles', Key=file_key)
    with gzip.GzipFile(fileobj=resp['Body']) as gz:
        table = pa_csv.read_csv(
            gz,
            convert_options=CSV_CONVERT_OPTS,
            read_options=CSV_READ_OPTS,
        )
    return table


def stream_and_parse_with_retry(file_key, massive_client):
    for attempt in range(MAX_RETRIES):
        try:
            return stream_and_parse(file_key, massive_client)
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)
            log.warning(f'retry {attempt + 1}/{MAX_RETRIES} for {file_key}: {e}')


def upload_parquet(table, s3_client, bucket, prefix, year, date_str):
    '''Write Arrow table to S3 as parquet.'''
    buf = io.BytesIO()
    pq.write_table(table, buf)
    s3_key = f'{prefix}/bronze/staged/{year}/{date_str}.parquet'
    s3_client.put_object(Bucket=bucket, Key=s3_key, Body=buf.getvalue())
    return s3_key


def process_file(file_key, massive_client, s3_client, bucket, prefix, year):
    date_str = Path(file_key).name.replace('.csv.gz', '')
    t0 = time.monotonic()

    table = stream_and_parse(file_key, massive_client)
    table = cast_to_schema(table, date_str)
    stream_time = time.monotonic() - t0

    t1 = time.monotonic()
    s3_key = upload_parquet(table, s3_client, bucket, prefix, year, date_str)
    upload_time = time.monotonic() - t1

    return {
        'date': date_str, 'rows': len(table), 's3_key': s3_key,
        'download_s': 0.0, 'parse_s': stream_time,
        'upload_s': upload_time, 'total_s': time.monotonic() - t0,
    }


def process_file_with_retry(file_key, massive_client, s3_client, bucket, prefix, year):
    for attempt in range(MAX_RETRIES):
        try:
            return process_file(file_key, massive_client, s3_client, bucket, prefix, year)
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** attempt
            log.warning(f'retry {attempt + 1}/{MAX_RETRIES} for {file_key}: {e} (waiting {wait}s)')
            time.sleep(wait)


# ---------- sequential ----------

def run_sequential(file_keys, massive_session, bucket, prefix, year):
    massive_client = make_massive_client(massive_session)
    s3_client = boto3.client('s3', region_name='us-east-1')
    results, errors = [], []

    for key in file_keys:
        try:
            result = process_file_with_retry(key, massive_client, s3_client, bucket, prefix, year)
            results.append(result)
            log.info(
                f'[{len(results)}/{len(file_keys)}] {result["date"]}: '
                f'{result["rows"]:,} rows | '
                f'stream+parse={result["parse_s"]:.1f}s upload={result["upload_s"]:.1f}s '
                f'total={result["total_s"]:.1f}s'
            )
        except Exception as e:
            log.error(f'failed: {key}: {e}')
            errors.append(f'{key}: {e}')

    return results, errors


# ---------- concurrent (original) ----------

def run_concurrent(file_keys, massive_session, bucket, prefix, workers, year):
    results, errors = [], []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for key in file_keys:
            future = executor.submit(
                process_file_with_retry, key,
                make_massive_client(massive_session),
                boto3.client('s3', region_name='us-east-1'),
                bucket, prefix, year,
            )
            futures[future] = key

        for future in as_completed(futures):
            key = futures[future]
            try:
                result = future.result()
                results.append(result)
                log.info(
                    f'[{len(results)}/{len(file_keys)}] {result["date"]}: '
                    f'{result["rows"]:,} rows | '
                    f'stream+parse={result["parse_s"]:.1f}s upload={result["upload_s"]:.1f}s '
                    f'total={result["total_s"]:.1f}s'
                )
            except Exception as e:
                log.error(f'failed: {key}: {e}')
                errors.append(f'{key}: {e}')

    return results, errors


# ---------- main ----------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--months', type=int, nargs='+', required=True)
    parser.add_argument('--mode', choices=['concurrent', 'sequential'], default='concurrent')
    parser.add_argument('--workers', type=int, default=16)
    parser.add_argument('--bucket', default='finpipe-root')
    parser.add_argument('--prefix', default='dev/lakehouse')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    load_credentials()

    massive_session = boto3.Session(
        aws_access_key_id=os.environ['MASSIVE_ACCESS_KEY'],
        aws_secret_access_key=os.environ['MASSIVE_SECRET_KEY'],
    )

    file_keys = build_manifest(make_massive_client(massive_session), args.year, args.months)
    log.info(f'total files: {len(file_keys)}')

    if not file_keys:
        log.warning('no files found')
        return

    if args.dry_run:
        for key in file_keys:
            print(key)
        return

    log.info(f'mode={args.mode} workers={args.workers if args.mode == "concurrent" else 1} → s3://{args.bucket}/{args.prefix}/bronze/staged/{args.year}/')

    t0 = time.monotonic()

    if args.mode == 'sequential':
        results, errors = run_sequential(file_keys, massive_session, args.bucket, args.prefix, args.year)
    else:
        results, errors = run_concurrent(file_keys, massive_session, args.bucket, args.prefix, args.workers, args.year)

    elapsed = time.monotonic() - t0
    total_rows = sum(r['rows'] for r in results)
    avg_stream = sum(r['parse_s'] for r in results) / len(results) if results else 0
    avg_upload = sum(r['upload_s'] for r in results) / len(results) if results else 0

    log.info('=' * 60)
    log.info(f'MODE: {args.mode} (workers={args.workers if args.mode == "concurrent" else 1})')
    log.info(f'FILES: {len(results)} ok, {len(errors)} failed')
    log.info(f'ROWS: {total_rows:,}')
    log.info(f'WALL TIME: {elapsed:.1f}s')
    log.info(f'AVG PER FILE: stream+parse={avg_stream:.1f}s upload={avg_upload:.1f}s')
    log.info(f'THROUGHPUT: {total_rows / elapsed:,.0f} rows/s')
    log.info('=' * 60)


if __name__ == '__main__':
    main()
