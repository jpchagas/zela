from fastapi import APIRouter

from app.api.v1 import (
    audit,
    condominiums,
    conversations,
    documents,
    drive,
    emergency_contacts,
    me,
    residents,
    staff,
    tickets,
    units,
)

api_router = APIRouter(prefix="/v1")
for module in (
    me,
    condominiums,
    drive,
    units,
    residents,
    staff,
    conversations,
    tickets,
    documents,
    emergency_contacts,
    audit,
):
    api_router.include_router(module.router)
