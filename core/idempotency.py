"""Идемпотентность денежных действий по заголовку Idempotency-Key.

Паттерн «сначала бронируем ключ»: вставка записи с уникальным (user_id, idem_key)
проходит только у одного из параллельных запросов — остальные видят либо
готовый ответ, либо 409 «в обработке». Так двойной тап / ретрай сети не
приводит к двойному списанию.
"""
import json
from typing import Awaitable, Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

import models
from core.services.exceptions import ConflictError

IN_PROGRESS = "in_progress"
COMPLETED = "completed"


async def _get(db, user_id: int, key: str) -> models.IdempotencyKey | None:
    res = await db.execute(
        select(models.IdempotencyKey).filter(
            models.IdempotencyKey.user_id == user_id,
            models.IdempotencyKey.idem_key == key,
        )
    )
    return res.scalars().first()


async def run_idempotent(db, *, user_id: int, key: str | None, run: Callable[[], Awaitable[dict]]) -> dict:
    """Выполняет `run` идемпотентно по ключу.

    `run` — async-колбэк, возвращающий JSON-сериализуемый dict (тело успешного
    ответа); при бизнес-ошибке он бросает исключение (бронь ключа снимается,
    клиент может повторить). Без ключа выполняется как обычно.
    """
    if not key:
        return await run()

    existing = await _get(db, user_id, key)
    if existing:
        if existing.status == COMPLETED:
            return json.loads(existing.response_body)
        raise ConflictError("Запрос уже обрабатывается")

    rec = models.IdempotencyKey(user_id=user_id, idem_key=key, status=IN_PROGRESS)
    db.add(rec)
    try:
        await db.commit()                       # бронируем ключ (уникальность)
    except IntegrityError:
        await db.rollback()
        existing = await _get(db, user_id, key)
        if existing and existing.status == COMPLETED:
            return json.loads(existing.response_body)
        raise ConflictError("Запрос уже обрабатывается")

    try:
        body = await run()                      # сам money-экшен (коммитит свою транзакцию)
    except Exception:
        # действие не выполнилось — освобождаем ключ, чтобы клиент мог повторить
        stale = await _get(db, user_id, key)
        if stale is not None:
            await db.delete(stale)
            await db.commit()
        raise

    rec.status = COMPLETED
    rec.response_body = json.dumps(body, ensure_ascii=False, default=str)
    await db.commit()
    return body
