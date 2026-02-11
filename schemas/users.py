from typing import Optional
from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    phone: Optional[str] = None
    address: Optional[str] = None
    organization_id: Optional[str] = None
    organization_name: Optional[str] = None
    created_at: Optional[str] = None