import asyncio
import json
import os
import websockets


async def test_redis_event_delivery():
    token = os.environ.get("GOCOMET_TEST_TOKEN")

    if not token:
        raise RuntimeError("GOCOMET_TEST_TOKEN is not set")

    uri = (
        "ws://localhost:8000/ws/auctions/6"
        f"?token={token}"
    )

    async with websockets.connect(uri) as websocket:
        connected = await websocket.recv()
        print("Connection:", connected)

        print("Waiting for Redis test event...")

        event = await asyncio.wait_for(
            websocket.recv(),
            timeout=30,
        )

        print("Received event:", event)

        data = json.loads(event)
        assert data["type"] == "REDIS_TEST"
        assert data["auction_id"] == 6

        print("SUCCESS: Redis event reached WebSocket client")


if __name__ == "__main__":
    asyncio.run(test_redis_event_delivery())
