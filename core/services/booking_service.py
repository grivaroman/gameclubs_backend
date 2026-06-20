"""Бизнес-логика бронирования и освобождения ПК."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import models
from config import settings
from core.finance import credit_user_balance, debit_user_balance
from core.fraud import evaluate_admin_pc_override, evaluate_booking_success, evaluate_failed_payment
from core.services.access import user_can_manage_club
from core.services.exceptions import (
    AuthRequiredError,
    ConflictError,
    ForbiddenError,
    InsufficientFundsError,
    NotFoundError,
    ValidationError,
)
from core.ws import safe_send_pc_command


@dataclass
class BookingResult:
    booking_id: int
    pc_number: int
    duration_minutes: int
    message: str


@dataclass
class FreeSeatResult:
    pc_number: int
    message: str


@dataclass
class BookingRequestResult:
    booking_id: int
    pc_number: int
    mode: str
    amount_charged: int
    message: str


@dataclass
class BookingModerationResult:
    booking_id: int
    pc_number: int
    status: str
    refunded: int
    message: str


class BookingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _lock_active_user(self, user_id: int) -> models.User:
        res = await self.db.execute(
            select(models.User)
            .filter(models.User.id == user_id, models.User.is_active == 1)
            .with_for_update()
        )
        user = res.scalars().first()
        if not user:
            raise AuthRequiredError("Необходима авторизация")
        return user

    async def book_seat(self, *, user_id: int, pc_id: int, package_id: int) -> BookingResult:
        user = await self._lock_active_user(user_id)

        res = await self.db.execute(
            select(models.Computer).filter(models.Computer.id == pc_id).with_for_update()
        )
        pc = res.scalars().first()
        if not pc:
            raise NotFoundError("Компьютер не найден")
        if pc.status != "free":
            raise ConflictError("Место уже занято")

        res_club = await self.db.execute(
            select(models.Club).filter(models.Club.id == pc.club_id, models.Club.status == "active")
        )
        if not res_club.scalars().first():
            raise ConflictError("Клуб сейчас недоступен для бронирования")

        res_pkg = await self.db.execute(
            select(models.Package).filter(
                models.Package.id == package_id,
                models.Package.club_id == pc.club_id,
            )
        )
        package = res_pkg.scalars().first()
        if not package:
            raise NotFoundError("Тариф не найден")
        if package.pc_category != pc.category:
            raise ValidationError("Тариф не подходит для выбранного ПК")
        if package.price < 0 or package.duration_minutes < 1:
            raise ValidationError("Тариф настроен некорректно")

        if user.balance < package.price:
            await evaluate_failed_payment(
                self.db,
                user=user,
                event_type="player_booking_insufficient_funds",
                amount=package.price,
                balance=user.balance,
                club_id=pc.club_id,
            )
            await self.db.commit()
            raise InsufficientFundsError(f"Недостаточно средств. Нужно {package.price}₸")

        pc.status = "busy"
        pc.current_user_id = user.id
        pc.end_time = datetime.utcnow() + timedelta(minutes=package.duration_minutes)
        booking = models.Booking(
            user_id=user.id,
            computer_id=pc.id,
            amount_paid=package.price,
            status="active",
            starts_at=datetime.utcnow(),
            ends_at=pc.end_time,
        )
        self.db.add(booking)
        await self.db.flush()
        await debit_user_balance(
            self.db,
            user=user,
            amount=package.price,
            kind="booking_debit",
            club_id=pc.club_id,
            booking_id=booking.id,
            reason="Бронирование ПК",
            metadata={"pc_id": pc.id, "package_id": package.id, "duration_minutes": package.duration_minutes},
        )
        self.db.add(models.Notification(
            kind="booking",
            club_id=pc.club_id,
            title="Новое бронирование",
            message=f"ПК #{pc.number} забронирован на {package.duration_minutes} мин.",
        ))
        await evaluate_booking_success(self.db, user=user, pc=pc, package=package)
        await self.db.commit()

        await safe_send_pc_command(pc.id, {"command": "unlock", "user": user.email})
        return BookingResult(
            booking_id=booking.id,
            pc_number=pc.number,
            duration_minutes=package.duration_minutes,
            message=f"Бронирование на {package.duration_minutes} мин. успешно!",
        )

    async def free_seat(self, *, actor: models.User, pc_id: int) -> FreeSeatResult:
        res = await self.db.execute(select(models.Computer).filter(models.Computer.id == pc_id))
        pc = res.scalars().first()
        if not pc:
            raise NotFoundError("Компьютер не найден")

        can_manage = await user_can_manage_club(self.db, actor, pc.club_id)
        if not can_manage and pc.current_user_id != actor.id:
            raise ForbiddenError("Вы не можете освободить чужое место")

        if can_manage:
            await evaluate_admin_pc_override(self.db, admin=actor, pc=pc, new_status="free")

        pc.status = "free"
        pc.current_user_id = None
        pc.end_time = None
        await self.db.execute(
            update(models.Booking)
            .filter(models.Booking.computer_id == pc.id, models.Booking.status == "active")
            .values(status="completed")
        )
        await self.db.commit()

        await safe_send_pc_command(pc.id, {"command": "lock"})
        return FreeSeatResult(pc_number=pc.number, message="Место успешно освобождено!")

    async def create_booking_request(
        self, *, user_id: int, pc_id: int, starts_at=None, ends_at=None
    ) -> BookingRequestResult:
        """Клиентская заявка на бронь (агрегатор).

        Режим определяется клубом:
          * 'request'  — бесплатная заявка, владелец подтверждает в админке;
          * 'prepaid'  — при оформлении списывается депозит club.booking_deposit
                         (возвращается, если владелец отклонит заявку).
        ПК НЕ занимается до подтверждения — несколько заявок на одно место возможны.
        """
        user = await self._lock_active_user(user_id)

        res = await self.db.execute(
            select(models.Computer).filter(models.Computer.id == pc_id).with_for_update()
        )
        pc = res.scalars().first()
        if not pc:
            raise NotFoundError("Компьютер не найден")

        res_club = await self.db.execute(
            select(models.Club).filter(models.Club.id == pc.club_id, models.Club.status == "active")
        )
        club = res_club.scalars().first()
        if not club:
            raise ConflictError("Клуб сейчас недоступен для бронирования")

        # M3: валидируем окно времени, заданное клиентом, иначе ПК можно
        # «забронировать» в прошлое или на годы вперёд (и он залипнет в busy).
        now = datetime.utcnow()
        starts = starts_at or now
        if starts < now - timedelta(minutes=5):   # допускаем небольшой clock skew
            raise ValidationError("Время начала не может быть в прошлом")
        if ends_at is not None:
            if ends_at <= starts:
                raise ValidationError("Время окончания должно быть позже начала")
            duration_minutes = (ends_at - starts).total_seconds() / 60
            if duration_minutes > settings.max_booking_duration_minutes:
                max_hours = settings.max_booking_duration_minutes // 60
                raise ValidationError(f"Бронь не может быть длиннее {max_hours} ч")

        res_dup = await self.db.execute(
            select(models.Booking.id).filter(
                models.Booking.user_id == user.id,
                models.Booking.computer_id == pc.id,
                models.Booking.status == "pending",
            )
        )
        if res_dup.scalars().first():
            raise ConflictError("Вы уже отправили заявку на это место")

        mode = club.booking_mode or "request"
        deposit = (club.booking_deposit or 0) if mode == "prepaid" else 0
        if deposit > 0 and user.balance < deposit:
            raise InsufficientFundsError(f"Недостаточно средств для депозита. Нужно {deposit}₸")

        booking = models.Booking(
            user_id=user.id,
            computer_id=pc.id,
            amount_paid=0,
            status="pending",
            starts_at=starts,
            ends_at=ends_at,
        )
        self.db.add(booking)
        await self.db.flush()

        if deposit > 0:
            await debit_user_balance(
                self.db,
                user=user,
                amount=deposit,
                kind="booking_deposit",
                club_id=club.id,
                booking_id=booking.id,
                reason="Депозит за бронь",
                metadata={"pc_id": pc.id},
            )
            booking.amount_paid = deposit

        self.db.add(models.Notification(
            kind="booking",
            club_id=club.id,
            title="Новая заявка на бронь",
            message=f"ПК #{pc.number}: заявка от клиента ({'депозит ' + str(deposit) + '₸' if deposit else 'без предоплаты'}).",
        ))
        await self.db.commit()

        if deposit > 0:
            message = f"Заявка на ПК #{pc.number} отправлена. Списан депозит {deposit}₸ (вернётся при отклонении)."
        else:
            message = f"Заявка на ПК #{pc.number} отправлена. Ожидайте подтверждения клуба."
        return BookingRequestResult(
            booking_id=booking.id,
            pc_number=pc.number,
            mode=mode,
            amount_charged=deposit,
            message=message,
        )

    async def confirm_request(self, *, actor: models.User, booking_id: int) -> BookingModerationResult:
        """Владелец подтверждает заявку: бронь -> active, ПК занимается (если свободен)."""
        res = await self.db.execute(
            select(models.Booking).filter(models.Booking.id == booking_id).with_for_update()
        )
        booking = res.scalars().first()
        if not booking:
            raise NotFoundError("Заявка не найдена")

        res_pc = await self.db.execute(
            select(models.Computer).filter(models.Computer.id == booking.computer_id).with_for_update()
        )
        pc = res_pc.scalars().first()
        if not pc or not await user_can_manage_club(self.db, actor, pc.club_id):
            raise ForbiddenError("Нет доступа к этой заявке")
        if booking.status != "pending":
            raise ConflictError("Заявка уже обработана")
        # M1: нельзя подтвердить заявку на занятый ПК — иначе две 'active'-брони на одно
        # место (овербукинг). ПК под FOR UPDATE, занимаем атомарно.
        if pc.status != "free":
            raise ConflictError("ПК сейчас занят — освободите его перед подтверждением заявки")

        booking.status = "active"
        # M3: гарантируем конечный end_time. Если клиент не задал ends_at (или он в прошлом),
        # ставим дефолтную длительность — иначе ПК залипнет в 'busy' навсегда
        # (cleanup освобождает только по end_time <= now, а NULL под это не попадает).
        end_time = booking.ends_at
        if end_time is None or end_time <= datetime.utcnow():
            end_time = datetime.utcnow() + timedelta(minutes=settings.default_booking_session_minutes)
            booking.ends_at = end_time
        pc.status = "busy"
        pc.current_user_id = booking.user_id
        pc.end_time = end_time

        self.db.add(models.Notification(
            kind="booking",
            club_id=pc.club_id,
            title="Заявка подтверждена",
            message=f"Бронь ПК #{pc.number} подтверждена.",
        ))
        await self.db.commit()
        return BookingModerationResult(
            booking_id=booking.id, pc_number=pc.number, status="active", refunded=0,
            message=f"Заявка на ПК #{pc.number} подтверждена.",
        )

    async def reject_request(self, *, actor: models.User, booking_id: int) -> BookingModerationResult:
        """Владелец отклоняет заявку: бронь -> rejected, депозит (если был) возвращается."""
        res = await self.db.execute(
            select(models.Booking).filter(models.Booking.id == booking_id).with_for_update()
        )
        booking = res.scalars().first()
        if not booking:
            raise NotFoundError("Заявка не найдена")

        res_pc = await self.db.execute(
            select(models.Computer).filter(models.Computer.id == booking.computer_id)
        )
        pc = res_pc.scalars().first()
        if not pc or not await user_can_manage_club(self.db, actor, pc.club_id):
            raise ForbiddenError("Нет доступа к этой заявке")
        if booking.status != "pending":
            raise ConflictError("Заявка уже обработана")

        refunded = 0
        if booking.amount_paid and booking.amount_paid > 0:
            res_user = await self.db.execute(
                select(models.User).filter(models.User.id == booking.user_id).with_for_update()
            )
            target = res_user.scalars().first()
            if target:
                await credit_user_balance(
                    self.db,
                    user=target,
                    amount=booking.amount_paid,
                    kind="booking_refund",
                    actor=actor,
                    club_id=pc.club_id,
                    booking_id=booking.id,
                    reason="Возврат депозита за отклонённую бронь",
                )
                refunded = booking.amount_paid

        booking.status = "rejected"
        self.db.add(models.Notification(
            kind="booking",
            club_id=pc.club_id,
            title="Заявка отклонена",
            message=f"Бронь ПК #{pc.number} отклонена{' (депозит возвращён)' if refunded else ''}.",
        ))
        await self.db.commit()
        return BookingModerationResult(
            booking_id=booking.id, pc_number=pc.number, status="rejected", refunded=refunded,
            message=f"Заявка на ПК #{pc.number} отклонена.",
        )

    async def expire_stale_requests(self, *, limit: int = 100) -> int:
        """M2: авто-отклоняет pending-заявки старше TTL и возвращает депозиты.

        Без этого списанный депозит висит бесконечно, если владелец не реагирует.
        Вызывается из фоновой чистки. Возвращает число протухших заявок.
        Заявки берём с FOR UPDATE skip_locked, чтобы не гоняться с confirm/reject.
        """
        cutoff = datetime.utcnow() - timedelta(minutes=settings.booking_request_ttl_minutes)
        res = await self.db.execute(
            select(models.Booking)
            .filter(models.Booking.status == "pending", models.Booking.starts_at < cutoff)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        stale = res.scalars().all()
        count = 0
        for booking in stale:
            if booking.amount_paid and booking.amount_paid > 0:
                res_user = await self.db.execute(
                    select(models.User).filter(models.User.id == booking.user_id).with_for_update()
                )
                target = res_user.scalars().first()
                if target:
                    await credit_user_balance(
                        self.db,
                        user=target,
                        amount=booking.amount_paid,
                        kind="booking_refund",
                        booking_id=booking.id,
                        reason="Возврат депозита: заявка истекла без ответа",
                    )
            booking.status = "rejected"
            count += 1
        if count:
            await self.db.commit()
        return count
