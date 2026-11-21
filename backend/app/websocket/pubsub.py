import asyncio
import json
import logging

import redis
import redis.asyncio as async_redis

from app.core.config import settings
from app.websocket.manager import auction_manager

logger = logging.getLogger(__name__)


def publish_auction_event(auction_id: int, event: dict) -> None:
    """
    Publish an auction event to Redis.
    Used by FastAPI routes and Celery workers.
    """
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )

    try:
        channel = f"auction:{auction_id}:events"
        client.publish(channel, json.dumps(event, default=str))
    finally:
        client.close()


async def listen_for_auction_events() -> None:
    """
    Listen for auction events from Redis and forward them
    to WebSocket connections handled by this FastAPI process.
    """
    while True:
        client = async_redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )

        try:
            async with client.pubsub() as pubsub:
                await pubsub.psubscribe("auction:*:events")
                logger.info("Subscribed to Redis auction events")

                async for message in pubsub.listen():
                    if message["type"] != "pmessage":
                        continue

                    try:
                        channel = message["channel"]
                        auction_id = int(channel.split(":")[1])
                        event = json.loads(message["data"])

                        await auction_manager.broadcast(
                            auction_id,
                            event,
                        )

                    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                        logger.exception("Invalid Redis auction event")

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Redis auction event listener failed; reconnecting"
            )
            await asyncio.sleep(2)

        finally:
            await client.aclose()
