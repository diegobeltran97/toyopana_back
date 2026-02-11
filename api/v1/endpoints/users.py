from fastapi import APIRouter, Depends
from api.deps import get_current_user
from schemas.users import UserResponse

router = APIRouter()


@router.get("/user/me", response_model=UserResponse)
async def get_current_user_info(user: dict = Depends(get_current_user)):
    """
    Returns the current user's profile from app_users, including organization info.
    """
    return UserResponse(
        id=user.get("id", ""),
        email=user.get("email", ""),
        name=user.get("name", ""),
        role=user.get("role", ""),
        phone=user.get("phone"),
        address=user.get("address"),
        organization_id=str(user.get("organization_id", "")) if user.get("organization_id") else None,
        organization_name=user.get("organization", {}).get("name") if isinstance(user.get("organization"), dict) else None,
        created_at=str(user.get("created_at", "")) if user.get("created_at") else None,
    )


@router.get("/protected")
async def protected_route(user: dict = Depends(get_current_user)):
    return {"message": "This is protected", "user_email": user.get("email")}