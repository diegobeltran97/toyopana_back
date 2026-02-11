from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/health", summary="Health Check", tags=["health"] )
async def health_check():
    """
    Health check endpoint to verify that the API is running.
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
