
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.entities import ParticipantStatus


class ParticipantInviteRequest(BaseModel):
    supplier_emails: list[EmailStr]


class ParticipantResponse(BaseModel):
    id: int
    auction_id: int
    supplier_id: int
    status: ParticipantStatus
    invited_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvitationResponse(BaseModel):
    participant_id: int
    rfq_reference_id: str
    rfq_name: str
    buyer_name: str
    status: ParticipantStatus
    invited_at: datetime


class InvitationActionResponse(BaseModel):
    message: str
    invitation: ParticipantResponse
