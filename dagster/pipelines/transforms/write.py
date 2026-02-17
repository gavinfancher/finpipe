"""Shared Iceberg write logic."""

from pyspark.sql import DataFrame, SparkSession


def write_to_iceberg(
    session: SparkSession,
    df: DataFrame,
    table: str,
    overwrite: bool = False,
    partition_col: str = 'date',
) -> None:
    """Write a DataFrame to an Iceberg table (create, append, or overwrite)."""
    if not session.catalog.tableExists(table):
        (
            df.writeTo(table)
            .tableProperty('write.format.default', 'parquet')
            .tableProperty('write.parquet.compression-codec', 'zstd')
            .partitionedBy(partition_col)
            .create()
        )
    elif overwrite:
        df.writeTo(table).overwritePartitions()
    else:
        df.writeTo(table).append()
