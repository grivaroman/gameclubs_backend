from datetime import datetime

from config import settings
from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

club_games = Table(
    "club_games",
    Base.metadata,
    Column("club_id", Integer, ForeignKey("clubs.id"), primary_key=True),
    Column("game_id", Integer, ForeignKey("games.id"), primary_key=True),
)


class Computer(Base):
    __tablename__ = "computers"
    __table_args__ = (
        UniqueConstraint("club_id", "number", name="uq_computers_club_number"),
        CheckConstraint("number IS NULL OR number > 0", name="ck_computers_number_positive"),
        CheckConstraint("status IS NULL OR status IN ('free', 'busy', 'reserved')", name="ck_computers_status_valid"),
        Index("ix_computers_club_id", "club_id"),
        Index("ix_computers_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    number = Column(Integer)
    category = Column(String)
    status = Column(String, default="free")
    club_id = Column(Integer, ForeignKey("clubs.id"))
    current_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    end_time = Column(DateTime, nullable=True)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)
    ws_token_hash = Column(String, nullable=True)
    ws_token_created_at = Column(DateTime, nullable=True)

    bookings = relationship("Booking", back_populates="computer")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price IS NULL OR price >= 0", name="ck_products_price_non_negative"),
        Index("ix_products_club_id", "club_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Integer)
    image_url = Column(String, nullable=True)
    club_id = Column(Integer, ForeignKey("clubs.id"))

    orders = relationship("Order", back_populates="product")
    club = relationship("Club", back_populates="products")


class ClubIntegration(Base):
    __tablename__ = "club_integrations"
    __table_args__ = (UniqueConstraint("club_id", name="uq_club_integrations_club_id"),)

    id = Column(Integer, primary_key=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    provider = Column(String, default="1c_http")
    base_url = Column(String, nullable=False)
    username = Column(String, nullable=True)
    secret_env_key = Column(String, nullable=True)
    health_path = Column(String, default="/")
    sync_products = Column(Integer, default=1)
    sync_orders = Column(Integer, default=1)
    sync_balances = Column(Integer, default=0)
    last_status = Column(String, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    club = relationship("Club", back_populates="integration")


class Club(Base):
    __tablename__ = "clubs"
    __table_args__ = (
        CheckConstraint(
            "status IS NULL OR status IN ('pending', 'active', 'blocked', 'rejected')",
            name="ck_clubs_status_valid",
        ),
        CheckConstraint(
            "booking_mode IS NULL OR booking_mode IN ('request', 'prepaid')",
            name="ck_clubs_booking_mode_valid",
        ),
        CheckConstraint(
            "booking_deposit IS NULL OR booking_deposit >= 0",
            name="ck_clubs_booking_deposit_non_negative",
        ),
        Index("ix_clubs_owner_id", "owner_id"),
        Index("ix_clubs_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    address = Column(String)
    city = Column(String, default="")
    photo_url = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    working_hours = Column(String, default="24/7")
    description = Column(Text)
    amenities = Column(Text)
    # Как клуб принимает брони: 'request' — бесплатная заявка с подтверждением владельцем,
    # 'prepaid' — списывается депозит booking_deposit при оформлении (возвращается при отклонении).
    booking_mode = Column(String, default="request")
    booking_deposit = Column(Integer, default=0)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, default="pending")
    moderation_comment = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)

    packages = relationship("Package", back_populates="club", cascade="all, delete-orphan")
    games = relationship("Game", secondary=club_games, back_populates="clubs")
    products = relationship("Product", back_populates="club")
    computers = relationship("Computer")
    owner = relationship("User", back_populates="clubs")
    integration = relationship("ClubIntegration", back_populates="club", uselist=False, cascade="all, delete-orphan")
    reviews = relationship("ClubReview", back_populates="club", cascade="all, delete-orphan")


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    clubs = relationship("Club", secondary=club_games, back_populates="games")


class Package(Base):
    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint("price IS NULL OR price >= 0", name="ck_packages_price_non_negative"),
        CheckConstraint("duration_minutes IS NULL OR duration_minutes > 0", name="ck_packages_duration_positive"),
        CheckConstraint("paid_minutes IS NULL OR paid_minutes > 0", name="ck_packages_paid_minutes_positive"),
        CheckConstraint("bonus_minutes IS NULL OR bonus_minutes >= 0", name="ck_packages_bonus_minutes_non_negative"),
        Index("ix_packages_club_id", "club_id"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Integer)
    duration_minutes = Column(Integer, default=60)
    paid_minutes = Column(Integer, nullable=True)
    bonus_minutes = Column(Integer, default=0)
    pc_category = Column(String)
    club_id = Column(Integer, ForeignKey("clubs.id"))

    club = relationship("Club", back_populates="packages")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("balance IS NULL OR balance >= 0", name="ck_users_balance_non_negative"),
        CheckConstraint("is_active IS NULL OR is_active IN (0, 1)", name="ck_users_is_active_boolean"),
        CheckConstraint(
            "role IS NULL OR role IN ('user', 'pending_owner', 'admin', 'owner', 'superadmin')",
            name="ck_users_role_valid",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    balance = Column(Integer, default=0)
    is_active = Column(Integer, default=1)
    tokens_invalid_before = Column(DateTime, nullable=True)

    orders = relationship("Order", back_populates="user")
    clubs = relationship("Club", back_populates="owner")
    reviews = relationship("ClubReview", back_populates="user")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount_paid IS NULL OR amount_paid >= 0", name="ck_orders_amount_paid_non_negative"),
        CheckConstraint("status IS NULL OR status IN ('pending', 'new', 'completed', 'cancelled')", name="ck_orders_status_valid"),
        Index("ix_orders_user_id", "user_id"),
        Index("ix_orders_product_id", "product_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    computer_id = Column(Integer, ForeignKey("computers.id"), nullable=True)
    amount_paid = Column(Integer, default=0)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="orders")
    product = relationship("Product", back_populates="orders")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("amount_paid IS NULL OR amount_paid >= 0", name="ck_bookings_amount_paid_non_negative"),
        CheckConstraint(
            "status IS NULL OR status IN ('pending', 'active', 'completed', 'expired', 'cancelled', 'rejected')",
            name="ck_bookings_status_valid",
        ),
        Index("ix_bookings_user_id", "user_id"),
        Index("ix_bookings_computer_id", "computer_id"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_starts_at", "starts_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    computer_id = Column(Integer, ForeignKey("computers.id"))
    amount_paid = Column(Integer, default=0)
    status = Column(String, default="active")
    starts_at = Column(DateTime, default=datetime.utcnow)
    ends_at = Column(DateTime, nullable=True)

    user = relationship("User")
    computer = relationship("Computer", back_populates="bookings")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount_positive"),
    )

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    title = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    category = Column(String, default="other")
    comment = Column(Text, nullable=True)
    spent_at = Column(DateTime, default=datetime.utcnow)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("is_read IS NULL OR is_read IN (0, 1)", name="ck_notifications_is_read_boolean"),
        Index("ix_notifications_club_id", "club_id"),
        Index("ix_notifications_is_read", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, default="system")
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    title = Column(String)
    message = Column(Text)
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class FraudSignal(Base):
    __tablename__ = "fraud_signals"
    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_fraud_signals_score_range"),
        CheckConstraint("severity IS NULL OR severity IN ('low', 'medium', 'high')", name="ck_fraud_signals_severity_valid"),
    )

    id = Column(Integer, primary_key=True, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_role = Column(String, nullable=True)
    subject_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    event_type = Column(String, nullable=False)
    severity = Column(String, default="low")
    score = Column(Integer, default=0)
    reason = Column(Text)
    metadata_json = Column(Text, nullable=True)
    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)


class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"
    __table_args__ = (
        CheckConstraint("amount <> 0", name="ck_balance_transactions_amount_non_zero"),
        Index("ix_balance_transactions_user_id", "user_id"),
        Index("ix_balance_transactions_actor_user_id", "actor_user_id"),
        Index("ix_balance_transactions_club_id", "club_id"),
        Index("ix_balance_transactions_created_at", "created_at"),
        Index("ix_balance_transactions_kind", "kind"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    amount = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    kind = Column(String, nullable=False)
    reason = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ClubReview(Base):
    __tablename__ = "club_reviews"
    __table_args__ = (
        UniqueConstraint("club_id", "user_id", name="uq_club_reviews_club_user"),
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_club_reviews_rating_range"),
        Index("ix_club_reviews_club_id", "club_id"),
        Index("ix_club_reviews_user_id", "user_id"),
        Index("ix_club_reviews_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    club = relationship("Club", back_populates="reviews")
    user = relationship("User", back_populates="reviews")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_transactions_amount_positive"),
        CheckConstraint("status IN ('pending', 'paid', 'failed', 'cancelled')", name="ck_payment_transactions_status_valid"),
        Index("ix_payment_transactions_user_id", "user_id"),
        Index("ix_payment_transactions_provider", "provider"),
        Index("ix_payment_transactions_status", "status"),
        Index("ix_payment_transactions_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String, default="pending", nullable=False)
    external_reference = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
