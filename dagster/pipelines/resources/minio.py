import boto3
from dagster import ConfigurableResource


class MinioResource(ConfigurableResource):

    endpoint_domain: str = 'lakehouse.finpy.dev'
    endpoint_port: int = 9000
    access_key: str = ''
    secret_key: str = ''
    region: str = 'us-east-1'

    def get_client(self):

        endpoint_url = f'http://{self.endpoint_domain}:{self.endpoint_port}'
        
        client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
        )
        return client
