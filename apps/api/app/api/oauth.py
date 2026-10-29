"""Browser redirect targets for OAuth providers. No bearer token arrives here; the signed
state carries who started the flow, and access is re-checked before anything is stored."""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.jobs import JobPublisher, get_job_publisher
from app.db.session import get_db
from app.integrations.google.base import Google
from app.integrations.google.factory import get_google
from app.services import drive

router = APIRouter(prefix="/oauth", tags=["oauth"])


@router.get("/google/callback", include_in_schema=False)
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    google: Google = Depends(get_google),
    publisher: JobPublisher = Depends(get_job_publisher),
):
    web = get_settings().web_base_url.rstrip("/")
    try:
        condominium_id = drive.complete_connect(
            db, google, publisher, code=code, state=state, error=error
        )
    except drive.ConnectFailed as exc:
        path = f"/c/{exc.condominium_id}" if exc.condominium_id else "/"
        return RedirectResponse(f"{web}{path}?{urlencode({'drive_error': exc.code})}", 303)
    return RedirectResponse(f"{web}/c/{condominium_id}?drive=connected", 303)
