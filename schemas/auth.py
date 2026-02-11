from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None


class AuthResponse(BaseModel):
    """Response returned after login or registration."""
    access_token: str
    token_type: str = "bearer"
    user: dict