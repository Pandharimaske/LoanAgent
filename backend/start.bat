@echo off
REM LoanAgent Backend Startup Script for Windows
REM This script checks databases and starts the FastAPI backend

setlocal enabledelayedexpansion

REM Get the directory of this script
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR:~0,-1%\..
set BACKEND_DIR=%SCRIPT_DIR:~0,-1%
set DATA_DIR=%PROJECT_ROOT%\data
set ENV_FILE=%BACKEND_DIR%\.env

cls
echo.
echo ============================================================================
echo 🚀 LoanAgent Backend Startup
echo ============================================================================
echo.

REM ============================================================================
REM STEP 1: Check .env file
REM ============================================================================

echo [1/4] Checking environment configuration...
echo.

if not exist "%ENV_FILE%" (
    echo ⚠️  .env file not found at %ENV_FILE%
    echo Creating template .env file...
    
    (
        echo # Generated .env template - PLEASE UPDATE WITH REAL VALUES
        echo.
        echo # JWT Configuration
        echo JWT_SECRET=your-secret-key-here
        echo JWT_EXPIRES_HOURS=24
        echo.
        echo # Database Encryption
        echo DB_ENCRYPTION_KEY=your-encryption-key-here
        echo.
        echo # Ollama Configuration
        echo OLLAMA_BASE_URL=http://localhost:11434
        echo OLLAMA_MODEL=qwen2.5:3b
        echo OLLAMA_TIMEOUT=120
        echo.
        echo # Other Settings
        echo DEBUG=true
        echo LOG_LEVEL=INFO
    ) > "%ENV_FILE%"
    
    echo ⚠️  Please update .env with your JWT_SECRET and DB_ENCRYPTION_KEY!
    echo.
    pause
    exit /b 1
) else (
    echo ✅ .env file found
    
    REM Check for critical keys
    findstr /M "JWT_SECRET" "%ENV_FILE%" >nul
    if !errorlevel! neq 0 (
        echo ❌ JWT_SECRET not found in .env
        pause
        exit /b 1
    )
    
    findstr /M "DB_ENCRYPTION_KEY" "%ENV_FILE%" >nul
    if !errorlevel! neq 0 (
        echo ❌ DB_ENCRYPTION_KEY not found in .env
        pause
        exit /b 1
    )
    
    echo ✅ JWT_SECRET and DB_ENCRYPTION_KEY configured
)

echo.

REM ============================================================================
REM STEP 2: Check and create data directory
REM ============================================================================

echo [2/4] Checking database directories...
echo.

if not exist "%DATA_DIR%" (
    echo Creating data directory...
    mkdir "%DATA_DIR%"
)

echo ✅ Data directory: %DATA_DIR%
echo.

REM ============================================================================
REM STEP 3: Initialize databases
REM ============================================================================

echo [3/4] Checking databases...
echo.

if exist "%DATA_DIR%\memory.db" (
    echo ✅ SQLite database exists
) else (
    echo 📝 SQLite database not found, will be created on startup
)

if exist "%DATA_DIR%\chroma_db" (
    echo ✅ ChromaDB directory exists
) else (
    echo 📝 ChromaDB directory not found, will be created on startup
)

echo.
echo Initializing database schemas...
echo.

cd /d "%BACKEND_DIR%"

REM Initialize databases using Python
python -c "^
import sys; ^
from pathlib import Path; ^
sys.path.insert(0, str(Path.cwd())); ^
from auth.user_store import UserDatabase; ^
from memory.sqlite_store import MemoryDatabase; ^
from memory.vector_store import VectorStore; ^
try: ^
    user_db = UserDatabase(); ^
    user_db.connect(); ^
    user_db.init_user_schema(); ^
    user_db.close(); ^
    print('   ✓ User database schema initialized'); ^
except Exception as e: ^
    print(f'   ✗ Error: {e}'); ^
    sys.exit(1); ^
try: ^
    memory_db = MemoryDatabase(); ^
    memory_db.connect(); ^
    memory_db.init_schema(); ^
    memory_db.close(); ^
    print('   ✓ Memory database schema initialized'); ^
except Exception as e: ^
    print(f'   ✗ Error: {e}'); ^
    sys.exit(1); ^
try: ^
    vector_store = VectorStore(); ^
    print('   ✓ Vector store (ChromaDB) initialized'); ^
except Exception as e: ^
    print(f'   ✗ Error: {e}'); ^
    sys.exit(1); ^
"

if !errorlevel! neq 0 (
    echo ❌ Database initialization failed
    pause
    exit /b 1
)

echo ✅ All databases initialized
echo.

REM ============================================================================
REM STEP 4: Start the backend server
REM ============================================================================

echo [4/4] Starting backend server...
echo.

echo ============================================================================
echo 🟢 Starting LoanAgent Backend
echo ============================================================================
echo.

echo Server will run at: http://localhost:8000
echo Swagger UI: http://localhost:8000/docs
echo ReDoc: http://localhost:8000/redoc
echo.
echo Press Ctrl+C to stop the server
echo.
echo ============================================================================
echo.

REM Start uvicorn
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

if !errorlevel! neq 0 (
    echo.
    echo ❌ Failed to start server
    pause
    exit /b 1
)

endlocal
