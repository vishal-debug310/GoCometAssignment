
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now():
    return datetime.now(timezone.utc)


# --------------------------------------------------
# ENUMS
# --------------------------------------------------

class UserRole(str, PyEnum):
    BUYER = "BUYER"
    SUPPLIER = "SUPPLIER"
    ADMIN = "ADMIN"


class RFQStatus(str, PyEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class AuctionStatus(str, PyEnum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    FORCE_CLOSED = "FORCE_CLOSED"
    CANCELLED = "CANCELLED"


class TriggerType(str, PyEnum):
    ANY_BID = "ANY_BID"
    ANY_RANK_CHANGE = "ANY_RANK_CHANGE"
    L1_RANK_CHANGE = "L1_RANK_CHANGE"


class ParticipantStatus(str, PyEnum):
    INVITED = "INVITED"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class AuctionEventType(str, PyEnum):
    BID_SUBMITTED = "BID_SUBMITTED"
    RANKING_CHANGED = "RANKING_CHANGED"
    AUCTION_EXTENDED = "AUCTION_EXTENDED"
    AUCTION_STARTED = "AUCTION_STARTED"
    AUCTION_CLOSED = "AUCTION_CLOSED"
    AUCTION_FORCE_CLOSED = "AUCTION_FORCE_CLOSED"
    PARTICIPANT_INVITED = "PARTICIPANT_INVITED"
    RFQ_PUBLISHED = "RFQ_PUBLISHED"


# --------------------------------------------------
# USERS
# --------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False),
        nullable=False,
        default=UserRole.SUPPLIER,
    )

    company_name: Mapped[str | None] = mapped_column(String(200))

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


# --------------------------------------------------
# RFQ
# --------------------------------------------------

class RFQ(Base):
    __tablename__ = "rfqs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    reference_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    description: Mapped[str | None] = mapped_column(Text)

    buyer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    pickup_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[RFQStatus] = mapped_column(
        Enum(RFQStatus, native_enum=False),
        default=RFQStatus.DRAFT,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    buyer = relationship("User")

    auction = relationship(
        "Auction", back_populates="rfq", uselist=False
    )


# --------------------------------------------------
# AUCTIONS
# --------------------------------------------------

class Auction(Base):
    __tablename__ = "auctions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    rfq_id: Mapped[int] = mapped_column(
        ForeignKey("rfqs.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    forced_close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    status: Mapped[AuctionStatus] = mapped_column(
        Enum(AuctionStatus, native_enum=False),
        default=AuctionStatus.SCHEDULED,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "forced_close_time > close_time",
            name="ck_auction_forced_close_after_close",
        ),
        CheckConstraint(
            "close_time > start_time",
            name="ck_auction_close_after_start",
        ),
    )

    rfq = relationship("RFQ", back_populates="auction")

    config = relationship(
        "AuctionConfig", back_populates="auction", uselist=False
    )

    bids = relationship("Bid", back_populates="auction")

    events = relationship("AuctionEvent", back_populates="auction")


# --------------------------------------------------
# AUCTION CONFIGURATION
# --------------------------------------------------

class AuctionConfig(Base):
    __tablename__ = "auction_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    auction_id: Mapped[int] = mapped_column(
        ForeignKey("auctions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType, native_enum=False),
        nullable=False,
    )

    trigger_window_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10
    )

    extension_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )

    auction = relationship("Auction", back_populates="config")

    __table_args__ = (
        CheckConstraint(
            "trigger_window_minutes > 0",
            name="ck_trigger_window_positive",
        ),
        CheckConstraint(
            "extension_minutes > 0",
            name="ck_extension_positive",
        ),
    )


# --------------------------------------------------
# AUCTION PARTICIPANTS
# --------------------------------------------------

class AuctionParticipant(Base):
    __tablename__ = "auction_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    auction_id: Mapped[int] = mapped_column(
        ForeignKey("auctions.id", ondelete="CASCADE"),
        nullable=False,
    )

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[ParticipantStatus] = mapped_column(
        Enum(ParticipantStatus, native_enum=False),
        default=ParticipantStatus.INVITED,
        nullable=False,
    )

    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "auction_id",
            "supplier_id",
            name="uq_auction_supplier",
        ),
    )

    supplier = relationship("User")


# --------------------------------------------------
# BIDS - IMMUTABLE BID HISTORY
# --------------------------------------------------

class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    auction_id: Mapped[int] = mapped_column(
        ForeignKey("auctions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    freight_charges: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )

    origin_charges: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )

    destination_charges: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )

    total_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )

    transit_time_days: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    quote_valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    auction = relationship("Auction", back_populates="bids")

    supplier = relationship("User")

    __table_args__ = (
        CheckConstraint(
            "freight_charges >= 0 AND origin_charges >= 0 "
            "AND destination_charges >= 0",
            name="ck_bid_charges_nonnegative",
        ),
        CheckConstraint(
            "total_price > 0",
            name="ck_bid_total_positive",
        ),
        CheckConstraint(
            "transit_time_days >= 0",
            name="ck_bid_transit_nonnegative",
        ),
        Index("ix_bid_auction_submitted", "auction_id", "submitted_at"),
    )


# --------------------------------------------------
# CURRENT SUPPLIER RANKINGS
# --------------------------------------------------

class AuctionRanking(Base):
    __tablename__ = "auction_rankings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    auction_id: Mapped[int] = mapped_column(
        ForeignKey("auctions.id", ondelete="CASCADE"),
        nullable=False,
    )

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    total_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )

    latest_bid_id: Mapped[int] = mapped_column(
        ForeignKey("bids.id", ondelete="RESTRICT"),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "auction_id", "supplier_id",
            name="uq_auction_ranking_supplier",
        ),
        UniqueConstraint(
            "auction_id", "rank",
            name="uq_auction_ranking_position",
        ),
        CheckConstraint("rank > 0", name="ck_ranking_positive"),
    )


# --------------------------------------------------
# AUCTION ACTIVITY / AUDIT LOG
# --------------------------------------------------

class AuctionEvent(Base):
    __tablename__ = "auction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    auction_id: Mapped[int] = mapped_column(
        ForeignKey("auctions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    event_type: Mapped[AuctionEventType] = mapped_column(
        Enum(AuctionEventType, native_enum=False),
        nullable=False,
    )

    reason: Mapped[str | None] = mapped_column(Text)

    old_close_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    new_close_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    bid_id: Mapped[int | None] = mapped_column(
        ForeignKey("bids.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    auction = relationship("Auction", back_populates="events")

    actor = relationship("User")
