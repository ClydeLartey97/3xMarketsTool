from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.market_stream import async_redis_client, encode_market_message, market_stream_channel

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/markets/{market_code}")
async def market_websocket(websocket: WebSocket, market_code: str) -> None:
    await websocket.accept()
    redis = async_redis_client()
    pubsub = redis.pubsub()
    channel = market_stream_channel(market_code)
    await pubsub.subscribe(channel)
    await websocket.send_text(
        encode_market_message(
            {
                "type": "connected",
                "market_code": market_code.upper(),
                "channel": channel,
            }
        )
    )
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            await websocket.send_text(str(message.get("data", "")))
    except WebSocketDisconnect:
        logger.info("Market stream disconnected for %s", market_code)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.aclose()
