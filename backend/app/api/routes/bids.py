
import logging

from datetime import datetime, timezone, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, delete
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db, require_roles
from app.models.entities import (
    User,
    UserRole,
    Auction,
    AuctionStatus,
    AuctionParticipant,
    ParticipantStatus,
    Bid,
    RFQ,
    AuctionRanking,
    AuctionEvent,
    AuctionEventType,
)
from app.schemas.bid import (
    BidCreate,
    BidResponse,
    RankingResponse,
    AuctionEventResponse,
    BidSubmissionResponse,
)
from app.websocket.pubsub import publish_auction_event


router = APIRouter(
    prefix="/bids",
    tags=["British Auction Bidding"],
)

logger = logging.getLogger(__name__)


def publish_event_safely(
    auction_id: int,
    event: dict,
) -> None:
    """
    Publish an auction event without affecting
    an already committed database transaction.
    """
    try:
        publish_auction_event(auction_id, event)
    except Exception:
        logger.exception(
            "Failed to publish auction event for auction %s",
            auction_id,
        )


def verify_auction_access(
    db: Session,
    auction_id: int,
    current_user: User,
) -> Auction:
    auction = db.get(Auction, auction_id)

    if not auction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auction not found",
        )

    # Admin can view every auction.
    if current_user.role == UserRole.ADMIN:
        return auction

    # Buyer can view auctions belonging to their own RFQs.
    if current_user.role == UserRole.BUYER:
        rfq = db.get(RFQ, auction.rfq_id)

        if not rfq or rfq.buyer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this auction",
            )

        return auction

    # Supplier can view only auctions they have accepted.
    if current_user.role == UserRole.SUPPLIER:
        participant = db.scalar(
            select(AuctionParticipant).where(
                AuctionParticipant.auction_id == auction_id,
                AuctionParticipant.supplier_id == current_user.id,
                AuctionParticipant.status == ParticipantStatus.ACCEPTED,
            )
        )

        if not participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not an accepted participant in this auction",
            )

        return auction

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to view this auction",
    )


@router.post(
    "/auctions/{auction_id}",
    response_model=BidSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_bid(
    auction_id: int,
    payload: BidCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.SUPPLIER)
    ),
):
    now = datetime.now(timezone.utc)

    # Lock auction row to serialize concurrent bids.
    auction = db.scalar(
        select(Auction)
        .where(Auction.id == auction_id)
        .options(selectinload(Auction.config))
        .with_for_update()
    )

    if not auction:
        raise HTTPException(
            status_code=404,
            detail="Auction not found",
        )

    # Check supplier participation.
    participant = db.scalar(
        select(AuctionParticipant).where(
            AuctionParticipant.auction_id == auction_id,
            AuctionParticipant.supplier_id == current_user.id,
        )
    )

    if (
        not participant
        or participant.status != ParticipantStatus.ACCEPTED
    ):
        raise HTTPException(
            status_code=403,
            detail="You must accept the auction invitation before bidding",
        )

    if auction.status in (
        AuctionStatus.CLOSED,
        AuctionStatus.FORCE_CLOSED,
        AuctionStatus.CANCELLED,
    ):
        raise HTTPException(
            status_code=400,
            detail="Auction is not open",
        )

    if now < auction.start_time:
        raise HTTPException(
            status_code=400,
            detail="Auction has not started",
        )

    if (
        now >= auction.close_time
        or now >= auction.forced_close_time
    ):
        raise HTTPException(
            status_code=400,
            detail="Auction bidding has ended",
        )

    if payload.quote_valid_until <= now:
        raise HTTPException(
            status_code=422,
            detail="Quote validity must be in the future",
        )

    # Track automatic auction activation.
    auction_started = (
        auction.status == AuctionStatus.SCHEDULED
    )

    if auction_started:
        auction.status = AuctionStatus.ACTIVE

        db.add(
            AuctionEvent(
                auction_id=auction.id,
                actor_id=None,
                event_type=AuctionEventType.AUCTION_STARTED,
                reason=(
                    "Auction automatically activated "
                    "when the first bid was submitted"
                ),
            )
        )

    if not auction.config:
        raise HTTPException(
            status_code=500,
            detail="Auction configuration missing",
        )

    # Calculate total price on the server.
    total_price = (
        payload.freight_charges
        + payload.origin_charges
        + payload.destination_charges
    ).quantize(Decimal("0.01"))

    if total_price <= 0:
        raise HTTPException(
            status_code=422,
            detail="Total bid price must be greater than zero",
        )

    # Get supplier's previous bid.
    previous_bid = db.scalar(
        select(Bid)
        .where(
            Bid.auction_id == auction_id,
            Bid.supplier_id == current_user.id,
        )
        .order_by(
            Bid.submitted_at.desc(),
            Bid.id.desc(),
        )
        .limit(1)
    )

    # British auction: supplier must improve their own previous price.
    if previous_bid and total_price >= previous_bid.total_price:
        raise HTTPException(
            status_code=400,
            detail=(
                "Your new bid must be lower than your "
                f"previous bid of {previous_bid.total_price}"
            ),
        )

    # Save immutable bid history.
    bid = Bid(
        auction_id=auction_id,
        supplier_id=current_user.id,
        freight_charges=payload.freight_charges,
        origin_charges=payload.origin_charges,
        destination_charges=payload.destination_charges,
        total_price=total_price,
        transit_time_days=payload.transit_time_days,
        quote_valid_until=payload.quote_valid_until,
    )

    try:
        db.add(bid)
        db.flush()

        db.add(
            AuctionEvent(
                auction_id=auction_id,
                actor_id=current_user.id,
                event_type=AuctionEventType.BID_SUBMITTED,
                reason=f"Supplier submitted a bid of {total_price}",
                bid_id=bid.id,
            )
        )

        # Read previous ranking snapshot.
        old_rankings = db.scalars(
            select(AuctionRanking).where(
                AuctionRanking.auction_id == auction_id
            )
        ).all()

        old_rank_map = {
            row.supplier_id: row.rank
            for row in old_rankings
        }

        old_leader = next(
            (
                row.supplier_id
                for row in old_rankings
                if row.rank == 1
            ),
            None,
        )

        # Get the latest bid from every supplier.
        all_bids = db.scalars(
            select(Bid)
            .where(Bid.auction_id == auction_id)
            .order_by(
                Bid.supplier_id,
                Bid.submitted_at.desc(),
                Bid.id.desc(),
            )
        ).all()

        latest_bids = {}

        for item in all_bids:
            if item.supplier_id not in latest_bids:
                latest_bids[item.supplier_id] = item

        sorted_bids = sorted(
            latest_bids.values(),
            key=lambda item: (
                item.total_price,
                item.submitted_at,
                item.supplier_id,
            ),
        )

        new_rank_map = {
            item.supplier_id: index
            for index, item in enumerate(
                sorted_bids,
                start=1,
            )
        }

        new_leader = (
            sorted_bids[0].supplier_id
            if sorted_bids
            else None
        )

        ranking_changed = (
            old_rank_map != new_rank_map
        )

        l1_changed = (
            old_leader != new_leader
        )

        # Replace ranking snapshot inside the same transaction.
        db.execute(
            delete(AuctionRanking).where(
                AuctionRanking.auction_id == auction_id
            )
        )

        db.flush()

        new_ranking_rows = []

        for index, item in enumerate(
            sorted_bids,
            start=1,
        ):
            ranking = AuctionRanking(
                auction_id=auction_id,
                supplier_id=item.supplier_id,
                rank=index,
                total_price=item.total_price,
                latest_bid_id=item.id,
            )

            db.add(ranking)
            new_ranking_rows.append(ranking)

        db.flush()

        if ranking_changed:
            db.add(
                AuctionEvent(
                    auction_id=auction_id,
                    actor_id=current_user.id,
                    event_type=AuctionEventType.RANKING_CHANGED,
                    reason=(
                        "Supplier rankings changed "
                        "after bid submission"
                    ),
                    bid_id=bid.id,
                )
            )

        # Evaluate auction extension.
        old_close_time = auction.close_time

        trigger_window_start = (
            old_close_time
            - timedelta(
                minutes=auction.config.trigger_window_minutes
            )
        )

        within_trigger_window = (
            trigger_window_start <= now < old_close_time
        )

        trigger_type = auction.config.trigger_type

        should_extend = False
        extension_reason = None

        if within_trigger_window:
            if trigger_type.value == "ANY_BID":
                should_extend = True
                extension_reason = (
                    "Valid bid received within trigger window"
                )

            elif (
                trigger_type.value == "ANY_RANK_CHANGE"
                and ranking_changed
            ):
                should_extend = True
                extension_reason = (
                    "Supplier rankings changed within trigger window"
                )

            elif (
                trigger_type.value == "L1_RANK_CHANGE"
                and l1_changed
            ):
                should_extend = True
                extension_reason = (
                    "Lowest-price supplier changed within trigger window"
                )

        extension_applied = False

        if should_extend:
            proposed_close = (
                old_close_time
                + timedelta(
                    minutes=auction.config.extension_minutes
                )
            )

            # Never extend beyond forced close time.
            new_close_time = min(
                proposed_close,
                auction.forced_close_time,
            )

            if new_close_time > old_close_time:
                auction.close_time = new_close_time
                extension_applied = True

                db.add(
                    AuctionEvent(
                        auction_id=auction_id,
                        actor_id=current_user.id,
                        event_type=AuctionEventType.AUCTION_EXTENDED,
                        reason=extension_reason,
                        old_close_time=old_close_time,
                        new_close_time=new_close_time,
                        bid_id=bid.id,
                    )
                )

        # Commit bid, rankings, auction changes and audit events together.
        db.commit()

        db.refresh(bid)
        db.refresh(auction)

        # All notifications happen after a successful commit.

        if auction_started:
            publish_event_safely(
                auction_id,
                {
                    "type": "AUCTION_STARTED",
                    "auction_id": auction_id,
                    "message": "Auction is now active",
                },
            )

        publish_event_safely(
            auction_id,
            {
                "type": "BID_SUBMITTED",
                "auction_id": auction_id,
                "bid": {
                    "bid_id": bid.id,
                    "supplier_id": bid.supplier_id,
                    "total_price": str(bid.total_price),
                    "submitted_at": bid.submitted_at.isoformat(),
                },
            },
        )

        if ranking_changed:
            publish_event_safely(
                auction_id,
                {
                    "type": "RANKING_CHANGED",
                    "auction_id": auction_id,
                    "rankings": [
                        {
                            "supplier_id": row.supplier_id,
                            "rank": row.rank,
                            "total_price": str(row.total_price),
                            "latest_bid_id": row.latest_bid_id,
                        }
                        for row in new_ranking_rows
                    ],
                },
            )

        if extension_applied:
            publish_event_safely(
                auction_id,
                {
                    "type": "AUCTION_EXTENDED",
                    "auction_id": auction_id,
                    "old_close_time": old_close_time.isoformat(),
                    "new_close_time": auction.close_time.isoformat(),
                    "reason": extension_reason,
                },
            )

        return BidSubmissionResponse(
            message="Bid submitted successfully",
            bid=bid,
            rankings=new_ranking_rows,
            current_close_time=auction.close_time,
            extension_applied=extension_applied,
            extension_reason=(
                extension_reason
                if extension_applied
                else None
            ),
        )

    except Exception:
        db.rollback()

        logger.exception(
            "Bid processing failed for auction %s",
            auction_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Bid processing failed. Please try again.",
        )


@router.get(
    "/auctions/{auction_id}",
    response_model=list[BidResponse],
)
def get_auction_bids(
    auction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.BUYER,
            UserRole.SUPPLIER,
            UserRole.ADMIN,
        )
    ),
):
    verify_auction_access(
        db,
        auction_id,
        current_user,
    )

    bids = db.scalars(
        select(Bid)
        .where(Bid.auction_id == auction_id)
        .order_by(
            Bid.total_price.asc(),
            Bid.submitted_at.asc(),
            Bid.id.asc(),
        )
    ).all()

    return bids


@router.get(
    "/auctions/{auction_id}/rankings",
    response_model=list[RankingResponse],
)
def get_auction_rankings(
    auction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.BUYER,
            UserRole.SUPPLIER,
            UserRole.ADMIN,
        )
    ),
):
    verify_auction_access(
        db,
        auction_id,
        current_user,
    )

    rankings = db.scalars(
        select(AuctionRanking)
        .where(AuctionRanking.auction_id == auction_id)
        .order_by(AuctionRanking.rank.asc())
    ).all()

    return rankings


@router.get(
    "/auctions/{auction_id}/events",
    response_model=list[AuctionEventResponse],
)
def get_auction_events(
    auction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            UserRole.BUYER,
            UserRole.SUPPLIER,
            UserRole.ADMIN,
        )
    ),
):
    verify_auction_access(
        db,
        auction_id,
        current_user,
    )

    events = db.scalars(
        select(AuctionEvent)
        .where(AuctionEvent.auction_id == auction_id)
        .order_by(
            AuctionEvent.created_at.asc(),
            AuctionEvent.id.asc(),
        )
    ).all()

    return events
