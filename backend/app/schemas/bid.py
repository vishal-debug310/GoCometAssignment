
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BidCreate(BaseModel):
    freight_charges: Decimal = Field(
        ge=0,
        max_digits=14,
        decimal_places=2,
    )
    origin_charges: Decimal = Field(
        ge=0,
        max_digits=14,
        decimal_places=2,
    )
    destination_charges: Decimal = Field(
        ge=0,
        max_digits=14,
        decimal_places=2,
    )
    transit_time_days: int = Field(ge=0)
    quote_valid_until: datetime

    @field_validator("quote_valid_until")
    @classmethod
    def validate_quote_expiry(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Quote validity must include a timezone"
            )
        return value


class BidResponse(BaseModel):
    id: int
    auction_id: int
    supplier_id: int
    freight_charges: Decimal
    origin_charges: Decimal
    destination_charges: Decimal
    total_price: Decimal
    transit_time_days: int
    quote_valid_until: datetime
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RankingResponse(BaseModel):
    supplier_id: int
    rank: int
    total_price: Decimal
    latest_bid_id: int

    model_config = ConfigDict(from_attributes=True)


class BidSubmissionResponse(BaseModel):
    message: str
    bid: BidResponse
    rankings: list[RankingResponse]
    current_close_time: datetime
    extension_applied: bool
    extension_reason: str | None = None


class AuctionEventResponse(BaseModel):
    id: int
    auction_id: int
    actor_id: int | None
    event_type: str
    reason: str | None
    old_close_time: datetime | None
    new_close_time: datetime | None
    bid_id: int | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
