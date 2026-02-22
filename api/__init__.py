from fastapi import APIRouter
from api import auth, clubs, games

router = APIRouter(prefix="/api")

router.include_router(auth.router)
router.include_router(clubs.router)
router.include_router(games.router)
