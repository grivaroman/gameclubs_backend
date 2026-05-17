import unittest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import models
from core.ws import authenticate_pc_websocket, generate_pc_token, hash_pc_token, issue_pc_token, verify_pc_token


class PcWebSocketTokenTests(unittest.TestCase):
    def test_generated_token_is_prefixed_and_high_entropy(self):
        token = generate_pc_token()
        self.assertTrue(token.startswith("pc_"))
        self.assertGreaterEqual(len(token), 40)

    def test_verify_pc_token_rejects_missing_or_wrong_token(self):
        token = generate_pc_token()
        pc_hash = hash_pc_token(token)
        self.assertTrue(verify_pc_token(token, pc_hash))
        self.assertFalse(verify_pc_token(None, pc_hash))
        self.assertFalse(verify_pc_token(token, None))
        self.assertFalse(verify_pc_token("wrong-token", pc_hash))


class PcWebSocketAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)
        self.Session = sessionmaker(bind=self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_authenticates_pc_with_issued_token_only(self):
        async with self.Session() as db:
            pc = models.Computer(number=1, category="Standard", status="free")
            db.add(pc)
            await db.flush()

            token = await issue_pc_token(db, pc)
            await db.commit()

            self.assertIsNotNone(pc.ws_token_hash)
            self.assertNotEqual(pc.ws_token_hash, token)

            authenticated = await authenticate_pc_websocket(db, pc.id, token)
            rejected = await authenticate_pc_websocket(db, pc.id, "wrong-token")
            missing = await authenticate_pc_websocket(db, pc.id, None)

            self.assertEqual(authenticated.id, pc.id)
            self.assertIsNone(rejected)
            self.assertIsNone(missing)


if __name__ == "__main__":
    unittest.main()
