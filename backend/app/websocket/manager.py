from collections import defaultdict

from fastapi import WebSocket


class AuctionConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, auction_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[auction_id].add(websocket)

    def disconnect(self, auction_id: int, websocket: WebSocket):
        connections = self.active_connections.get(auction_id)

        if connections:
            connections.discard(websocket)

            if not connections:
                self.active_connections.pop(auction_id, None)

    async def broadcast(self, auction_id: int, message: dict):
        connections = self.active_connections.get(auction_id, set()).copy()

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(auction_id, connection)


auction_manager = AuctionConnectionManager()
