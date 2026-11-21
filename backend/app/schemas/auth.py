from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal

from app.models.entities import UserRole


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal[UserRole.BUYER, UserRole.SUPPLIER] = UserRole.SUPPLIER
    company_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: UserRole
    company_name: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
