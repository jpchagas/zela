"""Domain errors raised by services and mapped to HTTP responses in one place."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class Forbidden(DomainError):
    status_code = 403
    code = "forbidden"


class Unauthenticated(DomainError):
    status_code = 401
    code = "unauthenticated"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class InvalidInput(DomainError):
    status_code = 422
    code = "invalid_input"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if isinstance(exc, Unauthenticated) else None
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=headers,
        )
