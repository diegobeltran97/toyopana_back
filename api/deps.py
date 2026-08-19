from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.supabase_auth import supabase_get_user_from_token, get_app_user_with_org

# Declaring the token through HTTPBearer instead of a raw `Header` is what puts
# the "Authorize" padlock in /docs: Swagger sends the header itself once the
# token is pasted there, and the per-endpoint `authorization` text box goes away.
# The wire format is unchanged -- still `Authorization: Bearer <token>`.
#
# auto_error=False because FastAPI's built-in failures are 403 "Not
# authenticated"; the 401s below are what the frontend already handles.
bearer_scheme = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    description="Supabase access token (session.access_token)",
)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """
    Dependency that:
    1. Validates the JWT token against Supabase Auth
    2. Fetches the app_users record with organization data
    3. Returns the enriched user dict
    """
    if credentials is None:
        # With auto_error off, HTTPBearer returns None for every malformed case
        # alike, so read the raw header back to keep the reasons distinct.
        raw = request.headers.get("authorization")
        if not raw:
            raise HTTPException(status_code=401, detail="Missing authorization header")
        scheme, _, token = raw.partition(" ")
        if not scheme or not token.strip():
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        raise HTTPException(status_code=401, detail="Invalid authorization scheme")

    token = credentials.credentials

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
