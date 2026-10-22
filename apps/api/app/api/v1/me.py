from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.tenancy import MembershipSummary, MeOut
from app.services import condominiums

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeOut)
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_platform_admin=user.is_platform_admin,
        condominiums=[
            MembershipSummary(
                organization_id=c.organization_id,
                condominium_id=c.id,
                condominium_name=c.name,
                role=role,
            )
            for c, role in condominiums.list_accessible(db, user)
        ],
    )
