from fastapi import APIRouter
from datetime import datetime
from schemas.organization import OrganizationResponse
from core.supabase_client import SupabaseDB
from repositories.organization_repository import OrganizationRepository

router = APIRouter()




@router.post("/create/organization", summary="Create organization", tags=["organization"])
async def create_organization(org: OrganizationResponse):
    """
    endoint to create an organization.
    """
    data = {
        "name": org.name,
        "legal_name": org.legal_name,
        "tax_id": org.tax_id,
    }
    
    org_repo = OrganizationRepository()
    
    
    try:
        create_org = await org_repo.create_organization(data)
        return {"status": "success", "data": create_org}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    
