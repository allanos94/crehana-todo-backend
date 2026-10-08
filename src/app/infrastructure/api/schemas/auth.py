"""Request/response schemas for the auth endpoints (user-auth spec)."""

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    """An access/refresh token pair, as returned by login and refresh."""

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
