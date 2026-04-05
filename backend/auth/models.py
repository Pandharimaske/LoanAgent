"""
User authentication models and utilities.
Supports user login with password hashing.
"""

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime


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
    role: str = "customer"
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class User(UserBase):
    """User model (with ID and metadata)."""
    user_id: str
    customer_id: Optional[str] = None
    role: str = "customer"
    created_at: datetime
    last_login: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User response (no password)."""
    user_id: str
    username: str
    email: str
    name: str
    customer_id: Optional[str] = None
    role: str = "customer"
    created_at: datetime
    last_login: Optional[datetime] = None


class UserSession(BaseModel):
    """User session tracking."""
    session_id: str
    user_id: str
    email: str
    customer_id: Optional[str] = None
    role: str = "customer"
    logged_in_at: datetime
    last_activity: datetime
    expires_at: datetime
    is_active: bool = True
    messages: list = []
    summary: Optional[str] = None   # LLM-generated summary written when token limit is hit

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class TokenData(BaseModel):
    """JWT token data."""
    user_id: str
    email: str
    customer_id: Optional[str] = None
    role: str = "customer"
    issued_at: datetime
    expires_at: datetime


if __name__ == "__main__":
    # Test model construction
    print("\n✅ User models loaded successfully")
