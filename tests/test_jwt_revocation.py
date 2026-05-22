import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

import models
from core.dependencies import _token_revoked


class TokenRevocationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=models.AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def _make_user(self, cutoff: datetime | None) -> models.User:
        async with self.Session() as db:
            user = models.User(
                email="player@example.com",
                hashed_password="x",
                role="user",
                balance=0,
                tokens_invalid_before=cutoff,
            )
            db.add(user)
            await db.flush()
            res = await db.execute(select(models.User).filter_by(id=user.id))
            return res.scalars().first()

    async def test_without_cutoff_any_token_is_accepted(self):
        user = await self._make_user(cutoff=None)
        self.assertFalse(_token_revoked(user, {"iat": 0}))
        self.assertFalse(_token_revoked(user, {}))  # legacy token без iat

    async def test_with_cutoff_token_issued_before_is_revoked(self):
        cutoff = datetime.utcnow()
        user = await self._make_user(cutoff=cutoff)
        old_iat = int((cutoff - timedelta(seconds=10)).replace(tzinfo=timezone.utc).timestamp())
        self.assertTrue(_token_revoked(user, {"iat": old_iat}))

    async def test_with_cutoff_token_issued_after_is_accepted(self):
        cutoff = datetime.utcnow()
        user = await self._make_user(cutoff=cutoff)
        fresh_iat = int((cutoff + timedelta(seconds=10)).replace(tzinfo=timezone.utc).timestamp())
        self.assertFalse(_token_revoked(user, {"iat": fresh_iat}))

    async def test_with_cutoff_token_without_iat_is_revoked(self):
        """Старый токен без iat и активная ревокация — токен считается отозванным."""
        user = await self._make_user(cutoff=datetime.utcnow())
        self.assertTrue(_token_revoked(user, {"sub": "player@example.com"}))


if __name__ == "__main__":
    unittest.main()
