"""
User authentication models and utilities.
Supports customer login with password hashing.
"""

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class UserRole(str, Enum):
    """User roles."""
    CUSTOMER = "customer"
    AGENT = "agent"
    ADMIN = "admin"


class UserStatus(str, Enum):
    """User account status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    VERIFIED = "verified"
    PENDING_VERIFICATION = "pending_verification"


class UserBase(BaseModel):
    """Base user model."""
    username: str
    email: EmailStr
    name: str
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not all(c.isalnum() or c == '_' for c in v):
            raise ValueError("Username must be alphanumeric or underscore")
        return v


class UserCreate(UserBase):
    """User creation request."""
    password: str
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain digit")
        return v


class User(UserBase):
    """User model (with ID and metadata)."""
    user_id: str
    role: UserRole = UserRole.CUSTOMER
    status: UserStatus = UserStatus.ACTIVE
    is_verified: bool = False
    customer_id: Optional[str] = None  # For customers, link to customer_id
    created_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UserRole: lambda v: v.value,
            UserStatus: lambda v: v.value,
        }


class UserLogin(BaseModel):
    """User login request."""
    username: str
    password: str


class UserResponse(BaseModel):
    """User response (no password)."""
    user_id: str
    username: str
    email: str
    name: str
    role: UserRole
    status: UserStatus
    is_verified: bool
    customer_id: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None


class UserSession(BaseModel):
    """User session tracking."""
    session_id: str
    user_id: str
    username: str
    customer_id: Optional[str] = None
    logged_in_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_active: bool = True
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class TokenData(BaseModel):
    """JWT token data."""
    user_id: str
    username: str
    customer_id: Optional[str] = None
    role: UserRole
    issued_at: datetime
    expires_at: datetime


if __name__ == "__main__":
    # Test model construction
    print("\n✅ User models loaded successfully")
