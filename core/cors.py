from fastapi.middleware.cors import CORSMiddleware
from core.config import settings

def add_cors(app):
    """
    Add CORS middleware to the FastAPI app
    Allow frontend to call backend
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://yourapp.vercel.app",  # Production
            "http://localhost:3000",        # Development
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )