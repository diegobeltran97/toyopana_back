from fastapi import APIRouter
from api.v1.endpoints import health
from api.v1.endpoints import auth
from api.v1.endpoints import users
from api.v1.endpoints import organization

router = APIRouter()
router.include_router(health.router, prefix="/api", tags=["health"])
router.include_router(auth.router, prefix="/api", tags=["auth"])
router.include_router(users.router, prefix="/api", tags=["users"])
router.include_router(organization.router, prefix="/api", tags=["organization"])