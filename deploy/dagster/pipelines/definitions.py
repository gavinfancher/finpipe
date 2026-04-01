from dagster import Definitions, asset, AssetExecutionContext
import datetime
import platform


@asset
def server_info(context: AssetExecutionContext):
    """Basic info about the running environment."""
    info = {
        "hostname": platform.node(),
        "python": platform.python_version(),
        "os": platform.platform(),
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    context.log.info(f"Server info: {info}")
    return info

@asset
def idk(context: AssetExecutionContext):
    """Basic info about the running environment."""

defs = Definitions(assets=[server_info, idk])
