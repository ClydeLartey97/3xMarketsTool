from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def market_stream_channel(market_code: str) -> str:
    return f"market-stream:{market_code.upper()}"


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def encode_market_message(message: dict[str, Any]) -> str:
    return json.dumps(message, default=_json_default, separators=(",", ":"))


def publish_market_message_sync(market_code: str, message: dict[str, Any]) -> bool:
    payload = encode_market_message({"market_code": market_code.upper(), **message})
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        client.publish(market_stream_channel(market_code), payload)
        return True
    except Exception as exc:
        logger.warning("Market stream publish failed for %s: %s", market_code, exc)
        return False
    finally:
        client.close()


def async_redis_client() -> AsyncRedis:
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)
