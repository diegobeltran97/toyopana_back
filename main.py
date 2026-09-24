import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from core.cors import add_cors
from api.v1.router import router as v1_router
from integrations.messaging.factory import verify_provider_configured


def _configurar_logs() -> None:
    """Hacer visibles los logs de la aplicación.

    uvicorn configura sus propios loggers pero NO el root, así que sin esto
    todo `logger.info(...)` de services/ y repositories/ se descarta y solo
    sobreviven los warning -- pelados, sin hora ni nivel.

    Eso deja media aplicación muda justo donde hace falta mirar: "Avisada la
    cita X" y "Cita X sin teléfono" son las dos líneas que distinguen un aviso
    enviado de uno saltado, y ninguna de las dos llegaba a la consola.
    """
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def create_app() -> FastAPI:
    _configurar_logs()
    app = FastAPI(title="WhatsApp Metrics API", version="1.0.0")

    # Fail on boot, not on the first customer message, if WHATSAPP_PROVIDER
    # names a provider that does not exist.
    verify_provider_configured()

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