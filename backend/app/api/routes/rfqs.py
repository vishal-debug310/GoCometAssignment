
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, aliased

# from app.api.deps import get_db, require_roles
from app.api.deps import get_db, require_roles
from app.models.entities import (
    User,
    UserRole,
    RFQ,
    RFQStatus,
    Auction,
    AuctionStatus,
    AuctionConfig,
    AuctionEvent,
    AuctionEventType,
    AuctionParticipant,
    ParticipantStatus,
)
from app.schemas.rfq import (
    RFQCreate,
    RFQResponse,
    SupplierRFQResponse,
)


router = APIRouter(prefix="/rfqs", tags=["RFQ Management"])


@router.post(
    "/",
    response_model=RFQResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rfq(
    payload: RFQCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.BUYER)),
):
    rfq = RFQ(
        reference_id=f"RFQ-{uuid4().hex[:10].upper()}",
        name=payload.name,
        description=payload.description,
        buyer_id=current_user.id,
        pickup_date=payload.pickup_date,
        service_date=payload.service_date,
        status=RFQStatus.DRAFT,
    )

    auction = Auction(
        start_time=payload.auction.start_time,
        close_time=payload.auction.close_time,
        forced_close_time=payload.auction.forced_close_time,
        status=AuctionStatus.SCHEDULED,
    )

    auction_config = AuctionConfig(
        trigger_type=payload.auction.config.trigger_type,
        trigger_window_minutes=payload.auction.config.trigger_window_minutes,
        extension_minutes=payload.auction.config.extension_minutes,
    )

    auction.config = auction_config
    rfq.auction = auction

    try:
        db.add(rfq)
        db.commit()
        db.refresh(rfq)
        return rfq
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create RFQ. Please try again.",
        )


@router.get("/", response_model=list[RFQResponse])
def list_my_rfqs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.BUYER)),
):
    statement = (
        select(RFQ)
        .where(RFQ.buyer_id == current_user.id)
        .options(
            selectinload(RFQ.auction).selectinload(Auction.config)
        )
        .order_by(RFQ.created_at.desc())
    )

    return db.scalars(statement).all()

# ---------------------------------------------------------
# SUPPLIER: VIEW PUBLISHED RFQS THEY ARE INVITED TO
# ---------------------------------------------------------

@router.get(
    "/available",
    response_model=list[SupplierRFQResponse],
)
def get_available_rfqs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPPLIER)),
):
    Buyer = aliased(User)

    statement = (
        select(RFQ, AuctionParticipant, Buyer)
        .join(Auction, Auction.rfq_id == RFQ.id)
        .join(
            AuctionParticipant,
            AuctionParticipant.auction_id == Auction.id,
        )
        .join(Buyer, Buyer.id == RFQ.buyer_id)
        .where(
            AuctionParticipant.supplier_id == current_user.id,
            AuctionParticipant.status.in_([
                ParticipantStatus.INVITED,
                ParticipantStatus.ACCEPTED,
            ]),
            RFQ.status == RFQStatus.PUBLISHED,
        )
        .options(
            selectinload(RFQ.auction).selectinload(Auction.config)
        )
        .order_by(AuctionParticipant.invited_at.desc())
    )

    results = db.execute(statement).all()

    return [
        {
            "participant_id": participant.id,
            "invitation_status": participant.status,
            "invited_at": participant.invited_at,
            "rfq_id": rfq.id,
            "reference_id": rfq.reference_id,
            "name": rfq.name,
            "description": rfq.description,
            "pickup_date": rfq.pickup_date,
            "service_date": rfq.service_date,
            "buyer_name": buyer.name,
            "buyer_company_name": buyer.company_name,
            "auction": rfq.auction,
        }
        for rfq, participant, buyer in results
    ]


@router.post(
    "/{rfq_id}/publish",
    response_model=RFQResponse,
)
def publish_rfq(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.BUYER)),
):
    try:
        # Lock the RFQ row to prevent concurrent publishing.
        rfq = db.scalar(
            select(RFQ)
            .where(RFQ.id == rfq_id)
            .options(
                selectinload(RFQ.auction).selectinload(Auction.config)
            )
            .with_for_update()
        )

        if not rfq:
            raise HTTPException(
                status_code=404,
                detail="RFQ not found",
            )

        if rfq.buyer_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You can only publish your own RFQs",
            )

        if rfq.status != RFQStatus.DRAFT:
            raise HTTPException(
                status_code=400,
                detail="Only draft RFQs can be published",
            )

        auction = db.scalar(
            select(Auction)
            .where(Auction.rfq_id == rfq.id)
            .with_for_update()
        )

        if not auction:
            raise HTTPException(
                status_code=400,
                detail="RFQ does not have an associated auction",
            )

        now = datetime.now(timezone.utc)

        if auction.status != AuctionStatus.SCHEDULED:
            raise HTTPException(
                status_code=400,
                detail="Only scheduled auctions can be published",
            )

        if now >= auction.start_time:
            raise HTTPException(
                status_code=400,
                detail="Auction start time must be in the future",
            )

        # Publish the RFQ.
        rfq.status = RFQStatus.PUBLISHED

        # Record the publishing action.
        db.add(
            AuctionEvent(
                auction_id=auction.id,
                actor_id=current_user.id,
                event_type=AuctionEventType.RFQ_PUBLISHED,
                reason="RFQ published by buyer",
            )
        )

        db.commit()

        # Reload relationships for the response.
        db.refresh(rfq)

        return rfq

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to publish RFQ. Please try again.",
        )
