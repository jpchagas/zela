from fastapi import APIRouter

from app.api.v1 import audit, condominiums, me, residents, staff, units

api_router = APIRouter(prefix="/v1")
for module in (me, condominiums, units, residents, staff, audit):
    api_router.include_router(module.router)
