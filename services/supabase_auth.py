from typing import Optional
import httpx
from fastapi import HTTPException
from core.config import settings


SUPABASE_HEADERS = {
    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
    "Content-Type": "application/json",
}


async def supabase_password_login(email: str, password: str) -> dict:
    """Authenticate user with email/password via Supabase Auth."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers={
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Content-Type": "application/json",
                },
                json={"email": email, "password": password},
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail=f"Invalid credentials: {resp.text}")

        return resp.json()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def supabase_register_user(
    email: str,
    password: str,
    name: str,
    phone: Optional[str] = None,
    address: Optional[str] = None,
) -> dict:
    """
    Register a new user via Supabase Admin API.
    
    The Postgres trigger 'on_auth_user_created' will automatically
    insert a row into app_users with the metadata provided here.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.SUPABASE_URL}/auth/v1/admin/users",
                headers=SUPABASE_HEADERS,
                json={
                    "email": email,
                    "password": password,
                    "email_confirm": True,  # Auto-confirm for now
                    "user_metadata": {
                        "name": name,
                        "phone": phone,
                        "address": address,
                        # organization_id is handled by the DB trigger (defaults to toyopanatest)
                    },
                },
            )

        if resp.status_code not in (200, 201):
            detail = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
            raise HTTPException(status_code=resp.status_code, detail=f"Registration failed: {detail}")

        user_data = resp.json()
        
        # After creating the user, log them in to get an access token
        login_result = await supabase_password_login(email, password)
        
        return {
            "user": user_data,
            "access_token": login_result.get("access_token"),
            "token_type": "bearer",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def supabase_get_user_from_token(token: str) -> dict:
    """
    Validates a Supabase JWT and returns the auth user payload.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.SUPABASE_URL}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
                },
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail=f"Invalid token: {resp.text}")

        return resp.json()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_app_user_with_org(user_id: str) -> Optional[dict]:
    """
    Fetch the app_users record joined with organization data.
    Uses the service role key so RLS doesn't block the query.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.SUPABASE_URL}/rest/v1/app_users",
                headers=SUPABASE_HEADERS,
                params={
                    "select": "*, organization:organization_id(id, name, legal_name, tax_id)",
                    "id": f"eq.{user_id}",
                },
            )

        if resp.status_code != 200:
            return None

        data = resp.json()
        return data[0] if data else None

    except Exception:
        return None