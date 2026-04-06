"""
Create Glue databases for the finpipe lakehouse.

Databases:
  finpipe_bronze — raw ingested data (minute aggs from Massive)
  finpipe_silver — enriched data (timestamps, sessions, rolling metrics)

Usage:
    uv run python infra/glue/database.py
"""

from infra.config import glue

DATABASES = ["finpipe_bronze", "finpipe_silver"]


def create() -> list[str]:
    """Create Glue databases. Returns list of database names."""
    for db_name in DATABASES:
        try:
            glue.create_database(
                DatabaseInput={
                    "Name": db_name,
                    "Description": f"finpipe lakehouse — {db_name.split('_')[1]} layer",
                },
            )
            print(f"created database: {db_name}")
        except glue.exceptions.AlreadyExistsException:
            print(f"already exists: {db_name}")

    return DATABASES


if __name__ == "__main__":
    create()
