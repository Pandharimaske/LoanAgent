"""
FastAPI main application entry point.
Initializes app with all routes, middleware, and configuration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import DEBUG, LOG_LEVEL
from api.auth_routes import router as auth_router
from auth.user_store import UserDatabase

# Create FastAPI app
app = FastAPI(
    title="LoanAgent Backend",
    description="Memory-powered bank loan agent with conversation recall",
    version="0.1.0",
    debug=DEBUG,
)

# ============================================================================
# MIDDLEWARE
# ============================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# ROUTES
# ============================================================================

# Include auth routes
app.include_router(auth_router)


# ============================================================================
# ROOT ENDPOINT
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "service": "LoanAgent Backend",
        "version": "0.1.0",
        "status": "running",
        "debug": DEBUG,
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "auth": {
                "register": "POST /auth/register",
                "login": "POST /auth/login",
                "logout": "POST /auth/logout",
                "check_session": "GET /auth/session/{session_id}",
                "health": "GET /auth/health",
            },
            "docs": {
                "swagger": "/docs",
                "redoc": "/redoc",
                "openapi": "/openapi.json",
            },
        },
    }


@app.get("/health")
async def health():
    """Global health check endpoint."""
    return {
        "status": "healthy",
        "service": "LoanAgent",
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================================
# ERROR HANDLERS
# ============================================================================


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle uncaught exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc),
            "code": "INTERNAL_SERVER_ERROR",
        },
    )


# ============================================================================
# STARTUP/SHUTDOWN EVENTS
# ============================================================================


@app.on_event("startup")
async def startup():
    """Initialize app on startup."""
    print("\n" + "=" * 70)
    print("🚀 LoanAgent Backend Starting")
    print("=" * 70)
    print(f"   Debug: {DEBUG}")
    print(f"   Log Level: {LOG_LEVEL}")
    print(f"   Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)
    
    # Initialize user database schema
    try:
        db = UserDatabase()
        db.connect()
        db.init_user_schema()
        db.close()
        print("✅ User database schema initialized")
    except Exception as e:
        print(f"❌ Error initializing user database: {e}")
    
    print("=" * 70 + "\n")


@app.on_event("shutdown")
async def shutdown():
    """Clean up on shutdown."""
    print("\n" + "=" * 70)
    print("🛑 LoanAgent Backend Shutting Down")
    print("=" * 70 + "\n")


# ============================================================================
# DEVELOPMENT RUNNING
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=DEBUG,
        log_level=LOG_LEVEL.lower(),
    )
