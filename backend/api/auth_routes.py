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
from auth.utils import TokenManager
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
    email: EmailStr
    name: str
    password: str


class RegisterResponse(BaseModel):
    """Registration response."""
    success: bool
    user_id: str
    email: str
    message: str


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login response with session token and JWT."""
    success: bool
    user_id: str
    email: str
    session_id: str
    jwt_token: str
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
    email: str
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
        # Generate username from email (part before @)
        username = request.email.split("@")[0]
        
        # Register user
        success, user_id, error = db.register_user(
            username=username,
            email=request.email,
            name=request.name,
            password=request.password,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error or "Registration failed",
            )

        return RegisterResponse(
            success=True,
            user_id=user_id,
            email=request.email,
            message=f"User registered successfully",
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
            email=request.email,
            password=request.password,
        )

        if not success or not session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error or "Login failed",
            )

        # Generate JWT token
        try:
            jwt_token = TokenManager.create_jwt_token(
                user_id=session.user_id,
                email=session.email,
                customer_id=session.customer_id,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Token generation error: {str(e)}",
            )

        return LoginResponse(
            success=True,
            user_id=session.user_id,
            email=session.email,
            session_id=session.session_id,
            jwt_token=jwt_token,
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
            email=session.email,
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
# ALIAS ROUTES
# ============================================================================

@router.post("/signup", response_model=RegisterResponse)
async def signup(
    request: RegisterRequest,
    db: UserDatabase = Depends(get_db),
):
    """
    Signup - Alias for register endpoint.
    Allows frontend to use either /register or /signup.
    """
    return await register(request, db)


# ============================================================================
# PROFILE ENDPOINT
# ============================================================================

from typing import Dict, Any
from fastapi import Header

class ProfileResponse(BaseModel):
    """User profile response."""
    success: bool
    user: Dict[str, Any]
    message: Optional[str] = None


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    authorization: Optional[str] = Header(None),
    session_id: Optional[str] = None,
    db: UserDatabase = Depends(get_db),
):
    """
    Get user profile data from JWT token or session_id.
    
    Args:
        authorization: Bearer token from Authorization header
        session_id: Session ID from query params (fallback)
        db: Database connection
        
    Returns:
        User profile data (name, email, customer_id, etc.)
    """
    try:
        user_id = None
        customer_id = None
        
        # Try to get user_id from JWT token
        if authorization:
            try:
                token = authorization.replace("Bearer ", "")
                payload = TokenManager.verify_jwt_token(token)
                user_id = payload.get("user_id")
                customer_id = payload.get("customer_id")
            except Exception as token_err:
                # Token verification failed, try session_id
                pass
        
        # Fallback to session_id
        if not user_id and session_id:
            session = db.get_session(session_id)
            if session:
                user_id = session.user_id
                customer_id = session.customer_id
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token or session",
            )
        
        # Get user data
        user = db.get_user(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        # Return user profile (exclude sensitive data)
        user_data = {
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
            "customer_id": customer_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
        
        return ProfileResponse(
            success=True,
            user=user_data,
            message="Profile retrieved successfully",
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Profile error: {str(e)}",
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
