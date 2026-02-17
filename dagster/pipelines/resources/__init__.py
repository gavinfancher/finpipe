from pathlib import Path
import os

from dotenv import load_dotenv

from .minio import MinioResource
from .massive_s3 import MassiveS3Resource
from .spark import SparkConnectResource

# Load .env from dagster/ directory
load_dotenv(Path(__file__).parent.parent.parent / '.env')


def get_configured_resources() -> dict:
    return {
        'minio': MinioResource(
            access_key=os.getenv('MINIO_ACCESS_KEY', ''),
            secret_key=os.getenv('MINIO_SECRET_KEY', ''),
        ),
        'massive_s3': MassiveS3Resource(
            access_key=os.getenv('MASSIVE_ACCESS_KEY', ''),
            secret_key=os.getenv('MASSIVE_SECRET_KEY', ''),
        ),
        'spark': SparkConnectResource(),
    }
