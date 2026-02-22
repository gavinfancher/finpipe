'''
silver data enrichment
    - timestamp conversion
    - session classification
'''

from pyspark.sql import DataFrame
from pyspark.sql import functions as sf



def add_timestamp(df: DataFrame) -> DataFrame:
    '''
    convert nanosecond int to eastern datetime
    '''
    return df.withColumn(
        'timestamp',
        sf.from_utc_timestamp((sf.col('window_start') / 1e9).cast('timestamp'), 'America/New_York')
    )


def add_market_session(df: DataFrame) -> DataFrame:
    '''
    classify each bar as pre_market, market, post_market, or closed (just incase)
    '''
    time_minutes = sf.hour('timestamp') * 60 + sf.minute('timestamp')
    return df.withColumn(
        'session',
        sf.when((time_minutes >= 4 * 60) & (time_minutes < 9 * 60 + 30), 'pre_market')
        .when((time_minutes >= 9 * 60 + 30) & (time_minutes < 16 * 60), 'market')
        .when((time_minutes >= 16 * 60) & (time_minutes < 20 * 60), 'post_market')
        .otherwise('closed')
    )