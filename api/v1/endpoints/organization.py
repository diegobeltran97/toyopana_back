from fastapi import APIRouter
from datetime import datetime
from schemas.organization import OrganizationResponse
from core.supabase_client import SupabaseDB
from postgrest import APIResponse

router = APIRouter()


db = SupabaseDB()


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
    
    try:
        resp: APIResponse = db.insert("organization", data)
        return resp.data[0]
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    
