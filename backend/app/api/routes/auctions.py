
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.models.entities import (
    User,
    UserRole,
    RFQ,
    Auction,
    AuctionStatus,
    AuctionEvent,
    AuctionEventType,
)

router = APIRouter(prefix="/auctions", tags=["Auction Management"])


def get_buyer_auction(
    db: Session,
    auction_id: int,
    buyer: User,
) -> Auction:
    auction = db.scalar(
        select(Auction)
        .where(Auction.id == auction_id)
        .with_for_update()
    )

    if not auction:
        raise HTTPException(
            status_code=404,
            detail="Auction not found",
        )

    rfq = db.get(RFQ, auction.rfq_id)

    if not rfq or rfq.buyer_id != buyer.id:
        raise HTTPException(
            status_code=403,
            detail="You can only manage auctions belonging to your RFQs",
        )

    return auction


@router.post("/{auction_id}/close")
def close_auction(
    auction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.BUYER)),
):
    try:
        auction = get_buyer_auction(db, auction_id, current_user)

        if auction.status != AuctionStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail="Only active auctions can be manually closed",
            )

        now = datetime.now(timezone.utc)

        auction.status = AuctionStatus.CLOSED

        db.add(
            AuctionEvent(
                auction_id=auction.id,
                actor_id=current_user.id,
                event_type=AuctionEventType.AUCTION_CLOSED,
                reason="Auction manually closed by buyer",
                old_close_time=auction.close_time,
                new_close_time=auction.close_time,
            )
        )

        db.commit()

        return {
            "message": "Auction closed successfully",
            "auction_id": auction.id,
            "status": auction.status.value,
            "closed_at": now,
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to close auction",
        )


@router.post("/{auction_id}/force-close")
def force_close_auction(
    auction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.BUYER)),
):
    try:
        auction = get_buyer_auction(db, auction_id, current_user)

        if auction.status not in (
            AuctionStatus.SCHEDULED,
            AuctionStatus.ACTIVE,
        ):
            raise HTTPException(
                status_code=400,
                detail="Auction is already closed or cancelled",
            )

        now = datetime.now(timezone.utc)

        auction.status = AuctionStatus.FORCE_CLOSED

        db.add(
            AuctionEvent(
                auction_id=auction.id,
                actor_id=current_user.id,
                event_type=AuctionEventType.AUCTION_FORCE_CLOSED,
                reason="Auction force-closed manually by buyer",
                old_close_time=auction.close_time,
                new_close_time=auction.close_time,
            )
        )

        db.commit()

        return {
            "message": "Auction force-closed successfully",
            "auction_id": auction.id,
            "status": auction.status.value,
            "closed_at": now,
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to force-close auction",
        )
