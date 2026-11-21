
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import and_, or_, select

from app.core.database import SessionLocal
from app.models.entities import (
    Auction,
    AuctionEvent,
    AuctionEventType,
    AuctionStatus,
    RFQ,
    RFQStatus,
)
from app.tasks.celery_app import celery_app
from app.websocket.pubsub import publish_auction_event

logger = get_task_logger(__name__)


@celery_app.task(
    name="app.tasks.auction_lifecycle.process_auction_lifecycle"
)
def process_auction_lifecycle():
    db = SessionLocal()

    activated = 0
    closed = 0
    force_closed = 0

    # Events are published only after the database transaction commits.
    pending_events = []

    try:
        now = datetime.now(timezone.utc)

        due_auctions = db.scalars(
            select(Auction)
            .join(RFQ, RFQ.id == Auction.rfq_id)
            .where(
                RFQ.status == RFQStatus.PUBLISHED,
                Auction.status.in_([
                    AuctionStatus.SCHEDULED,
                    AuctionStatus.ACTIVE,
                ]),
                or_(
                    Auction.forced_close_time <= now,
                    Auction.close_time <= now,
                    and_(
                        Auction.status == AuctionStatus.SCHEDULED,
                        Auction.start_time <= now,
                    ),
                ),
            )
            .order_by(Auction.id.asc())
            .with_for_update(skip_locked=True)
        ).all()

        for auction in due_auctions:
            auction_id = auction.id
            old_close_time = auction.close_time

            # 1. Activate a scheduled auction.
            if (
                auction.status == AuctionStatus.SCHEDULED
                and now >= auction.start_time
            ):
                auction.status = AuctionStatus.ACTIVE

                reason = "Scheduled auction start time reached"

                db.add(
                    AuctionEvent(
                        auction_id=auction_id,
                        actor_id=None,
                        event_type=AuctionEventType.AUCTION_STARTED,
                        reason=reason,
                    )
                )

                pending_events.append({
                    "type": "AUCTION_STARTED",
                    "auction_id": auction_id,
                    "start_time": auction.start_time.isoformat(),
                    "close_time": auction.close_time.isoformat(),
                    "reason": reason,
                })

                activated += 1

            # 2. Forced close takes priority.
            if now >= auction.forced_close_time:
                auction.status = AuctionStatus.FORCE_CLOSED

                reason = "Auction reached its forced close time"

                db.add(
                    AuctionEvent(
                        auction_id=auction_id,
                        actor_id=None,
                        event_type=AuctionEventType.AUCTION_FORCE_CLOSED,
                        reason=reason,
                        old_close_time=old_close_time,
                        new_close_time=old_close_time,
                    )
                )

                pending_events.append({
                    "type": "AUCTION_FORCE_CLOSED",
                    "auction_id": auction_id,
                    "old_close_time": old_close_time.isoformat(),
                    "forced_close_time": auction.forced_close_time.isoformat(),
                    "reason": reason,
                })

                force_closed += 1

            # 3. Otherwise, perform normal closing.
            elif now >= auction.close_time:
                auction.status = AuctionStatus.CLOSED

                reason = "Auction reached its current close time"

                db.add(
                    AuctionEvent(
                        auction_id=auction_id,
                        actor_id=None,
                        event_type=AuctionEventType.AUCTION_CLOSED,
                        reason=reason,
                        old_close_time=old_close_time,
                        new_close_time=old_close_time,
                    )
                )

                pending_events.append({
                    "type": "AUCTION_CLOSED",
                    "auction_id": auction_id,
                    "old_close_time": old_close_time.isoformat(),
                    "closed_at": now.isoformat(),
                    "reason": reason,
                })

                closed += 1

        # Commit database changes before broadcasting.
        db.commit()

        result = {
            "checked_at": now.isoformat(),
            "activated": activated,
            "closed": closed,
            "force_closed": force_closed,
        }

        if activated or closed or force_closed:
            logger.info("Auction lifecycle changes: %s", result)

        # 4. Broadcast committed lifecycle events through Redis.
        for event in pending_events:
            try:
                publish_auction_event(
                    event["auction_id"],
                    event,
                )
                logger.info(
                    "Published auction lifecycle event: %s",
                    event,
                )
            except Exception:
                logger.exception(
                    "Failed to publish lifecycle event: %s",
                    event,
                )

        return result

    except Exception:
        db.rollback()
        logger.exception("Auction lifecycle processing failed")
        raise

    finally:
        db.close()
