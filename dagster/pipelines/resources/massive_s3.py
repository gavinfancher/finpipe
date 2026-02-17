import boto3
from botocore.config import Config
from dagster import ConfigurableResource


class MassiveS3Resource(ConfigurableResource):

    endpoint_url: str = 'https://files.massive.com'
    access_key: str = ''
    secret_key: str = ''
    bucket: str = 'flatfiles'

    def get_client(self):
        
        session = boto3.Session(
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )
        client = session.client(
            's3',
            endpoint_url=self.endpoint_url,
            config=Config(signature_version='s3v4'),
        )
        return client
