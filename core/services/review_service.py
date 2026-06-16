"""Бизнес-логика отзывов о клубах."""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from config import settings
from core.services.exceptions import NotFoundError, ValidationError


@dataclass
class ReviewResult:
    created: bool
    message: str


def normalize_comment(comment: str | None) -> str | None:
    normalized = " ".join((comment or "").strip().split())
    if not normalized:
        return None
    return normalized[: settings.max_review_comment_length]


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_review(self, *, user_id: int, club_id: int, rating: int, comment: str | None) -> ReviewResult:
        if rating < 1 or rating > 5:
            raise ValidationError("Оценка должна быть от 1 до 5")

        res = await self.db.execute(
            select(models.Club.id).filter(models.Club.id == club_id, models.Club.status == "active")
        )
        if not res.scalars().first():
            raise NotFoundError("Клуб не найден")

        normalized = normalize_comment(comment)
        res_review = await self.db.execute(
            select(models.ClubReview).filter(
                models.ClubReview.club_id == club_id,
                models.ClubReview.user_id == user_id,
            )
        )
        review = res_review.scalars().first()
        if review:
            review.rating = rating
            review.comment = normalized
            review.updated_at = datetime.utcnow()
            created = False
            message = "Отзыв обновлён"
        else:
            self.db.add(models.ClubReview(
                club_id=club_id,
                user_id=user_id,
                rating=rating,
                comment=normalized,
            ))
            created = True
            message = "Отзыв добавлен"
        await self.db.commit()
        return ReviewResult(created=created, message=message)
