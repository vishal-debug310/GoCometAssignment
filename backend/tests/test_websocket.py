
import asyncio
import os
import websockets


async def test_connection():
    token = os.environ.get("GOCOMET_TEST_TOKEN")
    auction_id = os.environ.get("GOCOMET_AUCTION_ID", "11")

    if not token:
        raise RuntimeError(
            "Set GOCOMET_TEST_TOKEN before running this test"
        )

    uri = (
        f"ws://localhost:8000/ws/auctions/"
        f"{auction_id}?token={token}"
    )

    print(f"Connecting to Auction {auction_id}...")

    async with websockets.connect(uri) as websocket:
        response = await websocket.recv()
        print("Server response:", response)

        await websocket.send("ping")
        pong = await websocket.recv()
        print("Ping response:", pong)

        print("\nListening for live auction events...\n")

        async for message in websocket:
            print("LIVE EVENT:", message)


if __name__ == "__main__":
    try:
        asyncio.run(test_connection())
    except KeyboardInterrupt:
        print("\nWebSocket listener stopped.")
