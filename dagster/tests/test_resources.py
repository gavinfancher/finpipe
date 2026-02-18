'''Tests for resource connectivity and env var loading.'''

import os

import pytest

from pipelines.resources import get_configured_resources
from pipelines.resources.minio import MinioResource
from pipelines.resources.massive_s3 import MassiveS3Resource
from pipelines.resources.spark import SparkConnectResource


# ── helpers ───────────────────────────────────────────────────────────────────

def _has_env(*keys):
    return all(os.getenv(k) for k in keys)


needs_massive = pytest.mark.skipif(
    not _has_env('MASSIVE_ACCESS_KEY', 'MASSIVE_SECRET_KEY'),
    reason='MASSIVE_ACCESS_KEY / MASSIVE_SECRET_KEY not set',
)
needs_minio = pytest.mark.skipif(
    not _has_env('MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY'),
    reason='MINIO_ACCESS_KEY / MINIO_SECRET_KEY not set',
)


# ── resource instantiation ────────────────────────────────────────────────────

def test_get_configured_resources_returns_all_keys():
    resources = get_configured_resources()
    assert 'minio' in resources
    assert 'massive_s3' in resources
    assert 'spark' in resources


def test_minio_resource_defaults():
    r = MinioResource()
    assert r.endpoint_domain == 'lakehouse.finpy.dev'
    assert r.endpoint_port == 9000
    assert r.region == 'us-east-1'


def test_massive_s3_resource_defaults():
    r = MassiveS3Resource()
    assert r.endpoint_url == 'https://files.massive.com'
    assert r.bucket == 'flatfiles'


def test_spark_resource_defaults():
    r = SparkConnectResource()
    assert r.host == 'lakehouse.finpy.dev'
    assert r.port == 15002


# ── env vars ──────────────────────────────────────────────────────────────────

@needs_massive
def test_massive_env_vars_loaded():
    assert os.getenv('MASSIVE_ACCESS_KEY')
    assert os.getenv('MASSIVE_SECRET_KEY')


@needs_minio
def test_minio_env_vars_loaded():
    assert os.getenv('MINIO_ACCESS_KEY')
    assert os.getenv('MINIO_SECRET_KEY')


# ── connectivity ──────────────────────────────────────────────────────────────

@needs_massive
def test_massive_s3_connects():
    '''Verify we can reach Massive S3 and list a known prefix.'''
    resources = get_configured_resources()
    massive = resources['massive_s3']
    client = massive.get_client()

    response = client.list_objects_v2(
        Bucket=massive.bucket,
        Prefix='us_stocks_sip/minute_aggs_v1/',
        MaxKeys=1,
    )
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200


@needs_minio
def test_minio_connects():
    '''Verify we can reach MinIO.'''
    resources = get_configured_resources()
    minio = resources['minio']
    client = minio.get_client()

    response = client.list_buckets()
    assert response['ResponseMetadata']['HTTPStatusCode'] == 200


def test_spark_connects():
    '''Verify we can reach Spark Connect.'''
    resources = get_configured_resources()
    spark = resources['spark']
    session = spark.get_session()

    result = session.sql('select 1 as test').collect()
    assert result[0]['test'] == 1
