"""
Attach inline policies to the finpipe-github-actions IAM user.

GitHub Actions deploy uses access keys for this user (repo secrets). It needs
S3 write on ``scripts/`` for the EMR driver upload step in ``.github/workflows/deploy.yml``.

This is not the EC2 instance profile (``finpipe-ec2-role``); that role is for the server.

Usage (credentials must allow ``iam:PutUserPolicy`` on this user):

    uv run python infra/ci/github_actions_iam.py
"""

import json

from infra.config import iam

USER_NAME = "finpipe-github-actions"
BUCKET = "finpipe-lakehouse"


def apply_policies() -> None:
    # S3: upload Spark driver scripts from Actions runner → EMR entrypoints
    iam.put_user_policy(
        UserName=USER_NAME,
        PolicyName="finpipe-lakehouse-scripts",
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Sid": "ScriptsReadWrite",
                "Effect": "Allow",
                "Action": [
                    "s3:PutObject",
                    "s3:GetObject",
                    "s3:DeleteObject",
                ],
                "Resource": f"arn:aws:s3:::{BUCKET}/scripts/*",
            }],
        }),
    )
    print(f"put_user_policy: {USER_NAME} / finpipe-lakehouse-scripts (s3://{BUCKET}/scripts/*)")


if __name__ == "__main__":
    apply_policies()
