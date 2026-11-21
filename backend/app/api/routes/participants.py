
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_db, require_roles
from app.models.entities import (
    User,
    UserRole,
    RFQ,
    Auction,
    AuctionParticipant,
    ParticipantStatus,
    AuctionEvent,
    AuctionEventType,
)
from app.schemas.participant import (
    ParticipantInviteRequest,
    ParticipantResponse,
    InvitationResponse,
    InvitationActionResponse,
)


router = APIRouter(
    prefix="/participants",
    tags=["Supplier Invitations"],
)


# ---------------------------------------------------------
# BUYER: INVITE SUPPLIERS TO AN RFQ
# ---------------------------------------------------------

@router.post(
    "/rfqs/{rfq_id}/invite",
    response_model=list[ParticipantResponse],
    status_code=status.HTTP_201_CREATED,
)
def invite_suppliers(
    rfq_id: int,
    payload: ParticipantInviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.BUYER)),
):
    rfq = db.scalar(
        select(RFQ)
        .where(
            RFQ.id == rfq_id,
            RFQ.buyer_id == current_user.id,
        )
        .options(selectinload(RFQ.auction))
    )

    if not rfq:
        raise HTTPException(
            status_code=404,
            detail="RFQ not found or you do not own this RFQ",
        )

    if not rfq.auction:
        raise HTTPException(
            status_code=400,
            detail="This RFQ does not have an auction",
        )

    # Normalize and remove duplicate emails in the request.
    emails = list(dict.fromkeys(
        str(email).strip().lower()
        for email in payload.supplier_emails
    ))

    if not emails:
        raise HTTPException(
            status_code=400,
            detail="At least one supplier email is required",
        )

    suppliers = db.scalars(
        select(User).where(
            func.lower(User.email).in_(emails),
            User.role == UserRole.SUPPLIER,
            User.is_active.is_(True),
        )
    ).all()

    supplier_by_email = {
        supplier.email.lower(): supplier
        for supplier in suppliers
    }

    missing_emails = [
        email for email in emails
        if email not in supplier_by_email
    ]

    if missing_emails:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "Some supplier accounts were not found or are inactive",
                "emails": missing_emails,
            },
        )

    supplier_ids = [
        supplier_by_email[email].id
        for email in emails
    ]

    existing = db.scalars(
        select(AuctionParticipant).where(
            AuctionParticipant.auction_id == rfq.auction.id,
            AuctionParticipant.supplier_id.in_(supplier_ids),
        )
    ).all()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="One or more suppliers have already been invited",
        )

    created_participants = []

    try:
        for email in emails:
            supplier = supplier_by_email[email]

            participant = AuctionParticipant(
                auction_id=rfq.auction.id,
                supplier_id=supplier.id,
                status=ParticipantStatus.INVITED,
            )

            db.add(participant)
            db.flush()

            event = AuctionEvent(
                auction_id=rfq.auction.id,
                actor_id=current_user.id,
                event_type=AuctionEventType.PARTICIPANT_INVITED,
                reason=f"Supplier {supplier.email} was invited to the auction",
            )

            db.add(event)
            created_participants.append(participant)

        db.commit()

        for participant in created_participants:
            db.refresh(participant)

        return created_participants

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A supplier invitation already exists",
        )
    except Exception:
        db.rollback()
        raise


# ---------------------------------------------------------
# SUPPLIER: VIEW MY INVITATIONS
# ---------------------------------------------------------

@router.get(
    "/my-invitations",
    response_model=list[InvitationResponse],
)
def get_my_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPPLIER)),
):
    statement = (
        select(AuctionParticipant, RFQ, User)
        .join(Auction, Auction.id == AuctionParticipant.auction_id)
        .join(RFQ, RFQ.id == Auction.rfq_id)
        .join(User, User.id == RFQ.buyer_id)
        .where(
            AuctionParticipant.supplier_id == current_user.id
        )
        .order_by(AuctionParticipant.invited_at.desc())
    )

    results = db.execute(statement).all()

    return [
        InvitationResponse(
            participant_id=participant.id,
            rfq_reference_id=rfq.reference_id,
            rfq_name=rfq.name,
            buyer_name=buyer.name,
            status=participant.status,
            invited_at=participant.invited_at,
        )
        for participant, rfq, buyer in results
    ]


# ---------------------------------------------------------
# SUPPLIER: ACCEPT OR DECLINE AN INVITATION
# ---------------------------------------------------------

def update_invitation_status(
    participant_id: int,
    new_status: ParticipantStatus,
    db: Session,
    current_user: User,
):
    participant = db.get(AuctionParticipant, participant_id)

    if not participant or participant.supplier_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail="Invitation not found",
        )

    if participant.status != ParticipantStatus.INVITED:
        raise HTTPException(
            status_code=409,
            detail="This invitation has already been responded to",
        )

    participant.status = new_status

    try:
        db.commit()
        db.refresh(participant)
    except Exception:
        db.rollback()
        raise

    return participant


@router.post(
    "/{participant_id}/accept",
    response_model=InvitationActionResponse,
)
def accept_invitation(
    participant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPPLIER)),
):
    participant = update_invitation_status(
        participant_id,
        ParticipantStatus.ACCEPTED,
        db,
        current_user,
    )

    return {
        "message": "Invitation accepted successfully",
        "invitation": participant,
    }


@router.post(
    "/{participant_id}/decline",
    response_model=InvitationActionResponse,
)
def decline_invitation(
    participant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.SUPPLIER)),
):
    participant = update_invitation_status(
        participant_id,
        ParticipantStatus.DECLINED,
        db,
        current_user,
    )

    return {
        "message": "Invitation declined successfully",
        "invitation": participant,
    }


# ---------------------------------------------------------
# BUYER: VIEW INVITATIONS FOR AN RFQ
# ---------------------------------------------------------

@router.get(
    "/rfqs/{rfq_id}",
    response_model=list[ParticipantResponse],
)
def get_rfq_participants(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.BUYER)),
):
    rfq = db.scalar(
        select(RFQ).where(
            RFQ.id == rfq_id,
            RFQ.buyer_id == current_user.id,
        ).options(selectinload(RFQ.auction))
    )

    if not rfq or not rfq.auction:
        raise HTTPException(
            status_code=404,
            detail="RFQ or auction not found",
        )

    return db.scalars(
        select(AuctionParticipant)
        .where(AuctionParticipant.auction_id == rfq.auction.id)
        .order_by(AuctionParticipant.invited_at.desc())
    ).all()
