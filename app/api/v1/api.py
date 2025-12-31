from fastapi import APIRouter
from app.api.v1.endpoints import users, login, applications, company_info, directors, documents, admin, notifications, superadmin

api_router = APIRouter()
api_router.include_router(login.router, tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(applications.router, prefix="/applications", tags=["applications"])
api_router.include_router(company_info.router, prefix="/company-info", tags=["company-info"])
api_router.include_router(directors.router, prefix="/directors", tags=["directors"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(superadmin.router, prefix="/superadmin", tags=["superadmin"])
