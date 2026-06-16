from fastapi import APIRouter
from api import auth, clubs, games, me, actions, notifications

router = APIRouter(prefix="/api")

router.include_router(auth.router)
router.include_router(clubs.router)
router.include_router(games.router)
router.include_router(me.router)
router.include_router(actions.router)
router.include_router(notifications.router)
