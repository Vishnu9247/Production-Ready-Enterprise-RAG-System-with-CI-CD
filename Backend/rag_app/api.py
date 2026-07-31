"""FastAPI application entry point."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .core.config import get_settings
from .core.exceptions import UnsupportedDocumentTypeError
from .routing import api_router


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(api_router)


@app.exception_handler(UnsupportedDocumentTypeError)
def unsupported_document_handler(
    request: Request, exc: UnsupportedDocumentTypeError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        content={"detail": str(exc)},
    )


@app.exception_handler(ValueError)
def invalid_request_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(RuntimeError)
def unavailable_service_handler(request: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )
