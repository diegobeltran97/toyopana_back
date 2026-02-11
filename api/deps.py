from typing import Optional
from fastapi import Header, HTTPException
from services.supabase_auth import supabase_get_user_from_token, get_app_user_with_org


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    Dependency that:
    1. Validates the JWT token against Supabase Auth
    2. Fetches the app_users record with organization data
    3. Returns the enriched user dict
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    try:
        scheme, token = authorization.split()
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")

    # Step 1: Validate token and get auth user
    auth_user = await supabase_get_user_from_token(token)
    user_id = auth_user.get("id")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user data from token")

    # Step 2: Fetch app_users record with organization
    app_user = await get_app_user_with_org(user_id)

    if app_user:
        return app_user

    # Fallback: return auth user data if app_users record doesn't exist yet
    return {
        "id": user_id,
        "email": auth_user.get("email", ""),
        "name": auth_user.get("user_metadata", {}).get("name", ""),
        "role": "admin",
    }