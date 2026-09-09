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
            "https://toypana-frontend.vercel.app",  # Production frontend origin
            "http://localhost:3000", 
            "http://localhost:3002", # Development
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        # `*` is only honoured for non-credentialed requests, and this API is
        # mounted with allow_credentials, so any caller that turns credentials
        # on loses every exposed header. Name the ones the frontend actually
        # reads explicitly — an explicit name is always honoured.
        expose_headers=["*", "X-Total-Count"],
        max_age=3600,  # Cache preflight requests for 1 hour
    )