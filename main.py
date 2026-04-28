from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from core.cors import add_cors
from api.v1.router import router as v1_router

def create_app() -> FastAPI:
    app = FastAPI(title="WhatsApp Metrics API", version="1.0.0")

    # Add CORS middleware first
    add_cors(app)

    # Add exception handler to ensure CORS headers on errors
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true",
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers={
                "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
                "Access-Control-Allow-Credentials": "true",
            }
        )

    @app.get("/")
    async def root():
        return {
            "message": "WhatsApp Metrics API",
            "version": "1.0.0",
            "status": "running",
        }

    app.include_router(v1_router)
    return app

app = create_app()