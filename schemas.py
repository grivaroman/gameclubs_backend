from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List

# --- Auth & User ---
class UserBase(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    role: str = "user"

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

# --- Game ---
class GameResponse(BaseModel):
    id: int
    name: str

class GameCreate(BaseModel):
    name: str

# --- Package ---
class PackageResponse(BaseModel):
    id: int
    name: str
    price: int
    pc_category: str

class PackageCreate(BaseModel):
    name: str
    price: int
    pc_category: str = "Standard"

# --- Club ---
class ClubCreate(BaseModel):
    name: str
    address: str
    description: Optional[str] = None
    amenities: Optional[str] = None
    game_ids: List[int] = []
    packages: List[PackageCreate] = []

class ClubResponse(BaseModel):
    id: int
    name: str
    address: str
    description: Optional[str] = None
    games: List[GameResponse] = []
    packages: List[PackageResponse] = []

class MessageResponse(BaseModel):
    success: bool
    message: str