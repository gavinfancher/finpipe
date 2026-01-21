'''
Lakehouse and external resources for Dagster pipelines.
'''

import os
from typing import Any

import boto3
from botocore.config import Config
from dagster import ConfigurableResource
from pyspark.sql import SparkSession


class MinioResource(ConfigurableResource):
    '''
    MinIO resource for the remote data lakehouse.

    This is YOUR lakehouse storage where bronze/silver/gold tables live.
    Credentials come from your docker-compose lakehouse setup.
    '''

    endpoint_url: str = ''
    access_key: str = ''
    secret_key: str = ''
    region: str = 'us-east-1'

    def get_client(self) -> Any:
        '''Get a boto3 S3 client configured for MinIO.'''
        return boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )

    def list_objects(self, bucket: str, prefix: str = '') -> list[dict]:
        '''List objects in a bucket with optional prefix.'''
        client = self.get_client()
        response = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        return response.get('Contents', [])

    def upload_file(self, bucket: str, key: str, data: bytes) -> None:
        '''Upload data to a bucket.'''
        client = self.get_client()
        client.put_object(Bucket=bucket, Key=key, Body=data)


class MassiveS3Resource(ConfigurableResource):
    '''
    Massive (formerly Polygon) S3 flat files resource.

    Endpoint: https://files.massive.com
    Bucket: flatfiles
    Data: us_stocks_sip/minute_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz
    '''

    endpoint_url: str = 'https://files.massive.com'
    access_key: str = ''
    secret_key: str = ''
    bucket: str = 'flatfiles'

    def get_client(self) -> Any:
        '''Get a boto3 S3 client configured for Massive S3.'''
        session = boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )
        return session.client(
            's3',
            endpoint_url=self.endpoint_url,
            config=Config(signature_version='s3v4'),
        )

    def list_minute_aggs(self, year: int, month: int) -> list[dict]:
        '''List minute aggregate files for a given year/month.'''
        prefix = f'us_stocks_sip/minute_aggs_v1/{year}/{month:02d}/'
        client = self.get_client()
        response = client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return response.get('Contents', [])

    def list_objects(self, prefix: str = '') -> list[dict]:
        '''List objects with optional prefix.'''
        client = self.get_client()
        response = client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return response.get('Contents', [])

    def download_file(self, key: str, local_path: str) -> str:
        '''Download a file from Massive S3 to local path.'''
        client = self.get_client()
        client.download_file(self.bucket, key, local_path)
        return local_path

    def get_object(self, key: str) -> bytes:
        '''Get an object's contents from the bucket.'''
        client = self.get_client()
        response = client.get_object(Bucket=self.bucket, Key=key)
        return response['Body'].read()


class SparkConnectResource(ConfigurableResource):
    '''Spark Connect client resource for remote PySpark execution.'''

    host: str = ''
    port: int = None

    def get_session(self) -> SparkSession:
        '''Get a SparkSession connected to the remote Spark Connect server.'''
        return (
            SparkSession.builder.remote(f'sc://{self.host}:{self.port}')
            .appName('dagster-pipeline')
            .getOrCreate()
        )


def get_configured_resources() -> dict[str, Any]:

    minio_domain = os.getenv('MINIO_DOMAIN')
    minio_port = os.getenv('MINIO_PORT')
    minio_endpoint = f'http://{minio_domain}:{minio_port}'

    return {
        'minio': MinioResource(
            endpoint_url=minio_endpoint,
            access_key=os.getenv('MINIO_ACCESS_KEY'),
            secret_key=os.getenv('MINIO_SECRET_KEY'),
            region=os.getenv('AWS_REGION'),
        ),
        'massive_s3': MassiveS3Resource(
            endpoint_url='https://files.massive.com',
            access_key=os.getenv('MASSIVE_ACCESS_KEY'),
            secret_key=os.getenv('MASSIVE_SECRET_KEY'),
            bucket='flatfiles',
        ),
        'spark': SparkConnectResource(
            host=os.getenv('SPARK_HOST'),
            port=int(os.getenv('SPARK_PORT')),
        ),
    }
