from typing import Optional
from pydantic import BaseModel


class OrganizationResponse(BaseModel):
    name: str
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None