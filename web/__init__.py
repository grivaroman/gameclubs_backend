from fastapi import APIRouter
from web import auth, user, admin

router = APIRouter()
router.include_router(auth.router)
router.include_router(user.router)
router.include_router(admin.router)
