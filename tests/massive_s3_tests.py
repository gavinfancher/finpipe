import boto3
from botocore.config import Config

session = boto3.Session(
    aws_access_key_id='5bb2fa0f-f604-402e-a6f4-3133541e6d53',
    aws_secret_access_key='S7cWSJxAiX664uiLjIVyhSyDsJRxUKJu',
)

s3 = session.client(
    "s3",
    endpoint_url="https://files.massive.com",
    config=Config(signature_version="s3v4"),
)

bucket = "flatfiles"
base_prefix = "us_stocks_sip/minute_aggs_v1/"
jan_26_prefix = "2026/01/"

full_prefix = base_prefix + jan_26_prefix

paginator = s3.get_paginator("list_objects_v2")

files = []

for page in paginator.paginate(
    Bucket=bucket,
    Prefix=full_prefix,
):
    for obj in page.get("Contents", []):
        key = obj["Key"]
        filename = key.removeprefix(full_prefix)
        files.append(filename)

for f in files:
    print(f)

full_keys = [
    full_prefix + filename
    for filename in files
]

print('--------')
print(full_keys)
