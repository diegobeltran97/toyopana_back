from fastapi import FastAPI
from core.cors import add_cors
from api.v1.router import router as v1_router

def create_app() -> FastAPI:
    app = FastAPI(title="WhatsApp Metrics API", version="1.0.0")
    add_cors(app)

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