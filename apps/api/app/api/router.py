from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.telegram_account import router as telegram_account_router
from app.api.routes.users import router as users_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(telegram_account_router)
router.include_router(users_router)
