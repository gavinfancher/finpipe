"""
Create the finpipe Athena workgroup.

Query results go to s3://finpipe-lakehouse/athena-results/.

Usage:
    uv run python infra/athena/workgroup.py
"""

from infra.config import athena

WORKGROUP = "finpipe"
BUCKET = "finpipe-lakehouse"


def create() -> str:
    """Create the Athena workgroup. Returns the workgroup name."""
    try:
        athena.create_work_group(
            Name=WORKGROUP,
            Configuration={
                "ResultConfiguration": {
                    "OutputLocation": f"s3://{BUCKET}/athena-results/",
                },
                "EnforceWorkGroupConfiguration": True,
                "EngineVersion": {"SelectedEngineVersion": "Athena engine version 3"},
            },
            Description="finpipe lakehouse queries",
            Tags=[{"Key": "project", "Value": "finpipe"}],
        )
        print(f"created workgroup: {WORKGROUP}")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"already exists: {WORKGROUP}")
        else:
            raise

    return WORKGROUP


if __name__ == "__main__":
    create()
