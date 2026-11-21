from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import ALGORITHM
from app.models.entities import (
    User,
    UserRole,
    Auction,
    RFQ,
    AuctionParticipant,
    ParticipantStatus,
)
from app.websocket.manager import auction_manager


router = APIRouter(prefix="/ws", tags=["Auction WebSockets"])


@router.websocket("/auctions/{auction_id}")
async def auction_websocket(
    websocket: WebSocket,
    auction_id: int,
):
    token = websocket.query_params.get("token")

    if not token:
        await websocket.close(code=1008)
        return

    db = SessionLocal()

    try:
        # Validate JWT.
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[ALGORITHM],
            )

            subject = payload.get("sub")

            if not subject:
                await websocket.close(code=1008)
                return

            user_id = int(subject)

        except (JWTError, ValueError, TypeError):
            await websocket.close(code=1008)
            return

        # Verify the user.
        user = db.get(User, user_id)

        if not user or not user.is_active:
            await websocket.close(code=1008)
            return

        # Verify the auction.
        auction = db.scalar(
            select(Auction).where(Auction.id == auction_id)
        )

        if not auction:
            await websocket.close(code=1008)
            return

        # Check role-based access.
        if user.role == UserRole.BUYER:
            rfq = db.get(RFQ, auction.rfq_id)

            if not rfq or rfq.buyer_id != user.id:
                await websocket.close(code=1008)
                return

        elif user.role == UserRole.SUPPLIER:
            participant = db.scalar(
                select(AuctionParticipant).where(
                    AuctionParticipant.auction_id == auction_id,
                    AuctionParticipant.supplier_id == user.id,
                    AuctionParticipant.status == ParticipantStatus.ACCEPTED,
                )
            )

            if not participant:
                await websocket.close(code=1008)
                return

        elif user.role != UserRole.ADMIN:
            await websocket.close(code=1008)
            return

        # Accept the authorized connection.
        await auction_manager.connect(auction_id, websocket)

        await websocket.send_json({
            "type": "CONNECTED",
            "message": "Connected to auction updates",
            "auction_id": auction_id,
            "auction_status": auction.status.value,
            "close_time": auction.close_time.isoformat(),
        })

        # Keep the connection alive.
        while True:
            message = await websocket.receive_text()

            if message == "ping":
                await websocket.send_json({
                    "type": "PONG",
                })

    except WebSocketDisconnect:
        pass

    finally:
        auction_manager.disconnect(auction_id, websocket)
        db.close()
