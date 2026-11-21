
from datetime import date, datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.entities import (
    RFQStatus,
    AuctionStatus,
    TriggerType,
    ParticipantStatus,
)


class AuctionConfigCreate(BaseModel):
    trigger_type: TriggerType
    trigger_window_minutes: int = Field(gt=0, le=1440)
    extension_minutes: int = Field(gt=0, le=1440)


class AuctionCreate(BaseModel):
    start_time: datetime
    close_time: datetime
    forced_close_time: datetime
    config: AuctionConfigCreate

    @model_validator(mode="after")
    def validate_auction_times(self):
        for field_name in ("start_time", "close_time", "forced_close_time"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must include a timezone")

        if self.start_time <= datetime.now(timezone.utc):
            raise ValueError("Auction start time must be in the future")

        if self.close_time <= self.start_time:
            raise ValueError("Close time must be after start time")

        if self.forced_close_time <= self.close_time:
            raise ValueError("Forced close time must be after close time")

        return self


class RFQCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    pickup_date: date
    service_date: date
    auction: AuctionCreate

    @model_validator(mode="after")
    def validate_service_dates(self):
        if self.service_date < self.pickup_date:
            raise ValueError("Service date cannot be before pickup date")
        return self


class AuctionConfigResponse(BaseModel):
    trigger_type: TriggerType
    trigger_window_minutes: int
    extension_minutes: int

    model_config = ConfigDict(from_attributes=True)


class AuctionResponse(BaseModel):
    id: int
    start_time: datetime
    close_time: datetime
    forced_close_time: datetime
    status: AuctionStatus
    config: AuctionConfigResponse

    model_config = ConfigDict(from_attributes=True)


class RFQResponse(BaseModel):
    id: int
    reference_id: str
    name: str
    description: str | None
    buyer_id: int
    pickup_date: date
    service_date: date
    status: RFQStatus
    auction: AuctionResponse

    model_config = ConfigDict(from_attributes=True)


class SupplierRFQResponse(BaseModel):
    participant_id: int
    invitation_status: ParticipantStatus
    invited_at: datetime

    rfq_id: int
    reference_id: str
    name: str
    description: str | None
    pickup_date: date
    service_date: date

    buyer_name: str
    buyer_company_name: str | None

    auction: AuctionResponse
