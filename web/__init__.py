from fastapi import APIRouter
from web import auth, user, admin, superadmin

router = APIRouter()
router.include_router(auth.router)
router.include_router(user.router)
router.include_router(admin.router)
router.include_router(superadmin.router)
