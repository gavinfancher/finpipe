import json
import logging
import os
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_tags = getattr(record, "tags", {})
        if extra_tags:
            payload.update(extra_tags)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging():
    handlers: list[logging.Handler] = []

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(_JsonFormatter())
    handlers.append(stream_handler)

    # Only add Loki handler if LOKI_URL is set
    loki_url = os.getenv("LOKI_URL")
    if loki_url:
        import logging_loki
        loki_handler = logging_loki.LokiHandler(
            url=f"{loki_url}/loki/api/v1/push",
            tags={"service": "finpipe-api"},
            version="1",
        )
        loki_handler.setFormatter(_JsonFormatter())
        handlers.append(loki_handler)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = handlers

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = handlers
        uv_logger.propagate = False
