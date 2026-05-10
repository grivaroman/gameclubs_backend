from datetime import datetime

from config import settings
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
Base = declarative_base()

club_games = Table(
    "club_games",
    Base.metadata,
    Column("club_id", Integer, ForeignKey("clubs.id"), primary_key=True),
    Column("game_id", Integer, ForeignKey("games.id"), primary_key=True),
)


class Computer(Base):
    __tablename__ = "computers"

    id = Column(Integer, primary_key=True)
    number = Column(Integer)
    category = Column(String)
    status = Column(String, default="free")
    club_id = Column(Integer, ForeignKey("clubs.id"))
    current_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    end_time = Column(DateTime, nullable=True)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)

    bookings = relationship("Booking", back_populates="computer")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Integer)
    image_url = Column(String, nullable=True)
    club_id = Column(Integer, ForeignKey("clubs.id"))

    orders = relationship("Order", back_populates="product")
    club = relationship("Club", back_populates="products")


class Club(Base):
    __tablename__ = "clubs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    address = Column(String)
    city = Column(String, default="")
    photo_url = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    working_hours = Column(String, default="24/7")
    description = Column(Text)
    amenities = Column(Text)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    packages = relationship("Package", back_populates="club", cascade="all, delete-orphan")
    games = relationship("Game", secondary=club_games, back_populates="clubs")
    products = relationship("Product", back_populates="club")
    computers = relationship("Computer")
    owner = relationship("User", back_populates="clubs")


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    clubs = relationship("Club", secondary=club_games, back_populates="games")


class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Integer)
    duration_minutes = Column(Integer, default=60)
    pc_category = Column(String)
    club_id = Column(Integer, ForeignKey("clubs.id"))

    club = relationship("Club", back_populates="packages")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")
    balance = Column(Integer, default=0)

    orders = relationship("Order", back_populates="user")
    clubs = relationship("Club", back_populates="owner")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    computer_id = Column(Integer, ForeignKey("computers.id"), nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="orders")
    product = relationship("Product", back_populates="orders")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    computer_id = Column(Integer, ForeignKey("computers.id"))
    status = Column(String, default="active")
    starts_at = Column(DateTime, default=datetime.utcnow)
    ends_at = Column(DateTime, nullable=True)

    user = relationship("User")
    computer = relationship("Computer", back_populates="bookings")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, default="system")
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    title = Column(String)
    message = Column(Text)
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
