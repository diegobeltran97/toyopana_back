from fastapi import APIRouter, HTTPException
from schemas.auth import LoginRequest, RegisterRequest, AuthResponse
from services.supabase_auth import supabase_password_login, supabase_register_user, get_app_user_with_org

router = APIRouter()


@router.post("/auth/login")
async def login(request: LoginRequest):
    """
    Authenticate a user and return token + app_users profile.
    """
    result = await supabase_password_login(request.email, request.password)

    # Enrich with app_users data
    user_id = result.get("user", {}).get("id")
    app_user = None
    if user_id:
        app_user = await get_app_user_with_org(user_id)

    return {
        "access_token": result.get("access_token"),
        "token_type": "bearer",
        "expires_in": result.get("expires_in"),
        "user": app_user or result.get("user"),
    }


@router.post("/auth/register")
async def register(request: RegisterRequest):
    """
    Register a new user. The user is automatically associated
    with the 'toyopanatest' organization via a database trigger.
    """
    result = await supabase_register_user(
        email=request.email,
        password=request.password,
        name=request.name,
        phone=request.phone,
        address=request.address,
    )

    # Fetch the created app_users record with org data
    user_id = result.get("user", {}).get("id")
    app_user = None
    if user_id:
        app_user = await get_app_user_with_org(user_id)

    return {
        "access_token": result.get("access_token"),
        "token_type": result.get("token_type", "bearer"),
        "user": app_user or result.get("user"),
    }