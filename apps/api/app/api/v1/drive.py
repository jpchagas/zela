from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.jobs import JobPublisher, get_job_publisher
from app.db.session import get_db
from app.integrations.google.base import Google
from app.integrations.google.factory import get_google
from app.rbac.context import CondoContext, require_permission
from app.rbac.permissions import Permission
from app.schemas.drive import DriveConnectOut, DriveStatusOut
from app.services import drive

router = APIRouter(prefix="/condominiums/{condominium_id}/drive", tags=["drive"])

can_setup = require_permission(Permission.CONDOMINIUM_UPDATE)


@router.get("", response_model=DriveStatusOut)
def get_drive(
    ctx: CondoContext = Depends(can_setup),
    db: Session = Depends(get_db),
    google: Google = Depends(get_google),
):
    return drive.status(db, ctx, google)


@router.post("/connect", response_model=DriveConnectOut)
def connect(ctx: CondoContext = Depends(can_setup), google: Google = Depends(get_google)):
    """Returns Google's consent URL; the browser goes there and comes back to
    /oauth/google/callback."""
    return DriveConnectOut(authorization_url=drive.start_connect(ctx, google))


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def sync(
    ctx: CondoContext = Depends(can_setup),
    db: Session = Depends(get_db),
    publisher: JobPublisher = Depends(get_job_publisher),
):
    drive.request_sync(db, ctx, publisher)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(
    ctx: CondoContext = Depends(can_setup),
    db: Session = Depends(get_db),
    google: Google = Depends(get_google),
):
    drive.disconnect(db, ctx, google)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
