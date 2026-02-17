from dagster import ConfigurableResource
from pyspark.sql import SparkSession


class SparkConnectResource(ConfigurableResource):
    host: str = 'lakehouse.finpy.dev'
    port: int = 15002

    def get_session(self) -> SparkSession:
        
        session = (
            SparkSession.builder.remote(f'sc://{self.host}:{self.port}')
            .appName('dagster-pipeline')
            .getOrCreate()
        )
        return session
