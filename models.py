import os
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Table, Enum
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
import enum
from sqlalchemy import create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:12345678@localhost:5432/club")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Таблица связи М:М для клубов и игр
club_games = Table('club_games', Base.metadata,
    Column('club_id', Integer, ForeignKey('clubs.id'), primary_key=True),
    Column('game_id', Integer, ForeignKey('games.id'), primary_key=True)
)

class Computer(Base):
    __tablename__ = "computers"
    id = Column(Integer, primary_key=True)
    number = Column(Integer) # Номер ПК
    category = Column(String) # Standard/VIP
    status = Column(String, default="free") # free/busy/reserved
    club_id = Column(Integer, ForeignKey("clubs.id"))
    # Для карты зала (координаты на сетке)
    position_x = Column(Integer, default=0)
    position_y = Column(Integer, default=0)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Integer)
    image_url = Column(String, nullable=True) # Фото еды
    club_id = Column(Integer, ForeignKey("clubs.id"))

    orders = relationship("Order", back_populates="product")


class Club(Base):
    __tablename__ = 'clubs'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    address = Column(String)
    description = Column(Text)
    amenities = Column(Text)
    
    packages = relationship("Package", back_populates="club", cascade="all, delete-orphan")
    games = relationship("Game", secondary=club_games, back_populates="clubs")

class Game(Base):
    __tablename__ = 'games'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    clubs = relationship("Club", secondary=club_games, back_populates="games")

class Package(Base):
    __tablename__ = 'packages'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    price = Column(Integer)
    pc_category = Column(String)
    club_id = Column(Integer, ForeignKey('clubs.id'))
    club = relationship("Club", back_populates="packages")



class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user") # "admin" или "user"

    orders = relationship("Order", back_populates="user")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    product_id = Column(Integer, ForeignKey("products.id"))
    status = Column(String, default="pending") # pending, completed

    # ДОБАВЬ ЭТИ ДВЕ СТРОКИ:
    user = relationship("User", back_populates="orders")
    product = relationship("Product", back_populates="orders")