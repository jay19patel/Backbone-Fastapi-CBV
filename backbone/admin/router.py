from fastapi import APIRouter

from .auth_routes import router as auth_router
from .dashboard import router as dashboard_router
from .data_routes import router as data_router
from .model_routes import router as model_router
from .store_routes import router as store_router

router = APIRouter(prefix="/admin")
router.include_router(dashboard_router)
router.include_router(auth_router)
router.include_router(data_router)
router.include_router(store_router)
router.include_router(model_router)
