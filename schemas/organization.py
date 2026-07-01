from typing import Optional
from pydantic import BaseModel


class OrganizationResponse(BaseModel):
    name: str
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    logo_url: Optional[str] = None
    slug: Optional[str] = None
    features_enabled: Optional[list] = None
    subscription_plan: Optional[str] = None
    whapi_token: Optional[str] = None
    whapi_phone: Optional[str] = None
    
class OrganizationCreateRequest(BaseModel):
    name: str
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    logo_url: Optional[str] = None
    slug: Optional[str] = None
    features_enabled: Optional[list[str]] = None
    
    