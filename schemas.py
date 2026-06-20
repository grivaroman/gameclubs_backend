from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List

from core.security import MIN_PASSWORD_LENGTH

# --- Auth & User ---
class UserBase(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    balance: int = 0

class UserCreate(UserBase):
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# --- Game ---
class GameResponse(BaseModel):
    id: int
    name: str

class GameCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)

# --- Package ---
class PackageResponse(BaseModel):
    id: int
    name: str
    price: int
    duration_minutes: int
    paid_minutes: Optional[int] = None
    bonus_minutes: int = 0
    pc_category: str

class PackageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    price: int = Field(..., ge=0)
    duration_minutes: int = Field(60, gt=0)
    paid_minutes: Optional[int] = Field(None, gt=0)
    bonus_minutes: int = Field(0, ge=0)
    pc_category: str = "Standard"

# --- Club ---
class ClubCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    address: str = Field(..., min_length=1, max_length=255)
    city: Optional[str] = None
    photo_url: Optional[str] = None
    contact_phone: Optional[str] = None
    working_hours: Optional[str] = "24/7"
    description: Optional[str] = None
    amenities: Optional[str] = None
    game_ids: List[int] = Field(default_factory=list)
    packages: List[PackageCreate] = Field(default_factory=list)

class ClubListResponse(BaseModel):
    id: int
    name: str
    address: str
    city: Optional[str] = None
    photo_url: Optional[str] = None
    working_hours: Optional[str] = None
    description: Optional[str] = None
    booking_mode: str = "request"
    booking_deposit: int = 0

class ClubResponse(BaseModel) :
    id: int
    name: str
    address: str
    city: Optional[str] = None
    photo_url: Optional[str] = None
    contact_phone: Optional[str] = None
    working_hours: Optional[str] = None
    description: Optional[str] = None
    amenities: Optional[str] = None
    booking_mode: str = "request"
    booking_deposit: int = 0
    games: List[GameResponse] = Field(default_factory=list)
    packages: List[PackageResponse] = Field(default_factory=list)

class MessageResponse(BaseModel):
    success: bool
    message: str

class OrderResponse(BaseModel):
    id: int
    user_id: int
    product_id: Optional[int]
    computer_id: Optional[int]
    amount_paid: int = 0
    status: str
    created_at: str


# --- Mobile API schemas ---

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str

class UserMeResponse(BaseModel):
    id: int
    email: str
    phone: Optional[str] = None
    balance: int
    role: str

class ComputerResponse(BaseModel):
    # Публичная витрина ПК. НЕ раскрываем current_user_id (кто играет) — это PII;
    # отдаём только статус и время освобождения для UX «занят до …».
    id: int
    number: int
    category: str
    status: str
    end_time: Optional[datetime] = None
    position_x: int = 0
    position_y: int = 0

class ProductResponse(BaseModel):
    id: int
    name: str
    price: int
    image_url: Optional[str] = None
    club_id: int

class BookingResponse(BaseModel):
    id: int
    computer_id: int
    computer_number: Optional[int] = None
    club_id: Optional[int] = None
    club_name: Optional[str] = None
    amount_paid: int
    status: str
    starts_at: datetime
    ends_at: Optional[datetime] = None

class OrderDetailResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    club_id: Optional[int] = None
    club_name: Optional[str] = None
    amount_paid: int
    status: str
    created_at: datetime

class NotificationResponse(BaseModel):
    id: int
    kind: str
    title: str
    message: str
    is_read: bool
    created_at: datetime

class TransactionResponse(BaseModel):
    id: int
    amount: int            # < 0 — списание, > 0 — пополнение
    balance_after: int
    kind: str
    reason: Optional[str] = None
    created_at: datetime

class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)

class ActionResponse(BaseModel):
    status: str
    message: str
