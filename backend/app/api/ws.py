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
    subscribed = False
    try:
        try:
            await pubsub.subscribe(channel)
            subscribed = True
            await websocket.send_text(
                encode_market_message(
                    {
                        "type": "connected",
                        "market_code": market_code.upper(),
                        "channel": channel,
                        "stream_status": "live",
                    }
                )
            )
        except Exception as exc:  # noqa: BLE001 - local demo can run without Redis
            logger.warning("Market stream unavailable for %s: %s", market_code, exc)
            await websocket.send_text(
                encode_market_message(
                    {
                        "type": "connected",
                        "market_code": market_code.upper(),
                        "channel": channel,
                        "stream_status": "redis_unavailable",
                    }
                )
            )
            while True:
                await websocket.receive_text()

        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            await websocket.send_text(str(message.get("data", "")))
    except WebSocketDisconnect:
        logger.info("Market stream disconnected for %s", market_code)
    finally:
        if subscribed:
            await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.aclose()
