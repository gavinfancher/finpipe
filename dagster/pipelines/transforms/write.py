'''Shared Iceberg write logic.'''

from pyspark.sql import DataFrame, SparkSession


def write_to_iceberg(
    spark_session: SparkSession,
    df: DataFrame,
    table: str,
    overwrite: bool = False,
) -> None:
    '''
    write dataframe to iceberg table -- append or overwrite
    '''
    if not spark_session.catalog.tableExists(table):
        raise RuntimeError(
            f"table '{table}' does not exist — run the warehouse setup before ingesting data"
        )

    if overwrite:
        df.writeTo(table).overwritePartitions()
    else:
        df.writeTo(table).append()
