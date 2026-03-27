"""
FastAPI authentication routes.
Endpoints for user registration, login, logout, and session management.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

from auth.models import UserLogin, UserResponse, UserSession
from auth.user_store import UserDatabase
from config import SQLITE_PATH

# Create router
router = APIRouter(prefix="/auth", tags=["authentication"])

# Dependency to get database
def get_db():
    """Get database connection."""
    db = UserDatabase(db_path=SQLITE_PATH)
    db.connect()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================


class RegisterRequest(BaseModel):
    """User registration request."""
    username: str
    email: EmailStr
    name: str
    password: str
    customer_id: Optional[str] = None


class RegisterResponse(BaseModel):
    """Registration response."""
    success: bool
    user_id: str
    username: str
    email: str
    message: str


class LoginRequest(BaseModel):
    """User login request."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response with session token."""
    success: bool
    user_id: str
    username: str
    session_id: str
    expires_at: str
    customer_id: Optional[str] = None
    message: str


class LogoutRequest(BaseModel):
    """Logout request."""
    session_id: str


class LogoutResponse(BaseModel):
    """Logout response."""
    success: bool
    message: str


class SessionCheckResponse(BaseModel):
    """Session status response."""
    session_id: str
    user_id: str
    username: str
    customer_id: Optional[str] = None
    is_active: bool
    expires_at: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool
    error: str
    code: str


# ============================================================================
# ROUTES
# ============================================================================


@router.post("/register", response_model=RegisterResponse)
async def register(
    request: RegisterRequest,
    db: UserDatabase = Depends(get_db),
):
    """
    Register a new user.
    
    Args:
        request: Registration details
        db: Database connection
        
    Returns:
        RegisterResponse with user_id if successful
        
    Raises:
        HTTPException 400: If validation fails or user exists
    """
    try:
        # Register user
        success, user_id, error = db.register_user(
            username=request.username,
            email=request.email,
            name=request.name,
            password=request.password,
            customer_id=request.customer_id,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error or "Registration failed",
            )

        return RegisterResponse(
            success=True,
            user_id=user_id,
            username=request.username,
            email=request.email,
            message=f"User {request.username} registered successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration error: {str(e)}",
        )


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: UserDatabase = Depends(get_db),
):
    """
    Login user and create session.
    
    Args:
        request: Login credentials
        db: Database connection
        
    Returns:
        LoginResponse with session_id and token if successful
        
    Raises:
        HTTPException 401: If credentials invalid
    """
    try:
        # Attempt login
        success, session, error = db.login(
            username=request.username,
            password=request.password,
        )

        if not success or not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error or "Login failed",
            )

        return LoginResponse(
            success=True,
            user_id=session.user_id,
            username=session.username,
            session_id=session.session_id,
            expires_at=session.expires_at.isoformat(),
            customer_id=session.customer_id,
            message=f"Login successful. Session valid until {session.expires_at.isoformat()}",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login error: {str(e)}",
        )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: LogoutRequest,
    db: UserDatabase = Depends(get_db),
):
    """
    Logout user (invalidate session).
    
    Args:
        request: Session ID to invalidate
        db: Database connection
        
    Returns:
        LogoutResponse with success status
    """
    try:
        success = db.logout(request.session_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to logout",
            )

        return LogoutResponse(
            success=True,
            message="Logout successful",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout error: {str(e)}",
        )


@router.get("/session/{session_id}", response_model=SessionCheckResponse)
async def check_session(
    session_id: str,
    db: UserDatabase = Depends(get_db),
):
    """
    Check if a session is active and valid.
    
    Args:
        session_id: Session ID to check
        db: Database connection
        
    Returns:
        SessionCheckResponse with session status
        
    Raises:
        HTTPException 401: If session not found or expired
    """
    try:
        session = db.get_session(session_id)

        if not session or not session.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session not found or expired",
            )

        return SessionCheckResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            username=session.username,
            customer_id=session.customer_id,
            is_active=session.is_active,
            expires_at=session.expires_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Session check error: {str(e)}",
        )


# ============================================================================
# HEALTH CHECK
# ============================================================================


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "auth",
        "timestamp": datetime.now().isoformat(),
    }
