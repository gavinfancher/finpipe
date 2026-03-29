import json
import logging
from datetime import datetime, timezone

import logging_loki


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


class _LevelLokiHandler(logging_loki.LokiHandler):
    def build_tags(self, record):
        return super().build_tags(record)


def configure_logging():
    loki_handler = _LevelLokiHandler(
        url="http://localhost:3100/loki/api/v1/push",
        tags={"service": "finpipe-api"},
        version="1",
    )
    loki_handler.setFormatter(_JsonFormatter())

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [loki_handler, stream_handler]

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = [loki_handler, stream_handler]
        uv_logger.propagate = False
