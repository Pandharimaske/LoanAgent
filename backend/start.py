#!/usr/bin/env python
"""
LoanAgent Backend Startup Script (Cross-Platform)

Works on Windows, macOS, and Linux.
Usage: python start.py
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Colors for terminal output
class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    
    @staticmethod
    def is_windows():
        return sys.platform == "win32"
    
    @staticmethod
    def disable_on_windows():
        """Disable colors on Windows unless using modern terminal"""
        if Colors.is_windows():
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except:
                pass

Colors.disable_on_windows()

def print_header(text):
    print(f"\n{Colors.BLUE}{'='*80}{Colors.RESET}")
    print(f"{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BLUE}{'='*80}{Colors.RESET}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅{Colors.RESET} {text}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️{Colors.RESET}  {text}")

def print_error(text):
    print(f"{Colors.RED}❌{Colors.RESET} {text}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️{Colors.RESET}  {text}")

# Setup paths
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = SCRIPT_DIR
DATA_DIR = PROJECT_ROOT / "data"
ENV_FILE = BACKEND_DIR / ".env"

print_header(f"🚀 LoanAgent Backend Startup - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# ============================================================================
# STEP 1: Check .env file
# ============================================================================

print(f"{Colors.BLUE}[1/4]{Colors.RESET} Checking environment configuration...")

if not ENV_FILE.exists():
    print_warning(f".env file not found at {ENV_FILE}")
    print_info("Creating template .env file...")
    
    env_template = """# Generated .env template - PLEASE UPDATE WITH REAL VALUES

# JWT Configuration
JWT_SECRET=your-secret-key-here
JWT_EXPIRES_HOURS=24

# Database Encryption
DB_ENCRYPTION_KEY=your-encryption-key-here

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_TIMEOUT=120

# Other Settings
DEBUG=true
LOG_LEVEL=INFO
"""
    
    ENV_FILE.write_text(env_template)
    print_warning("Please update .env with your JWT_SECRET and DB_ENCRYPTION_KEY!")
    print_info("Generate keys using:")
    print_info('  JWT_SECRET: python -c "import secrets; print(secrets.token_urlsafe(32))"')
    print_info('  DB_ENCRYPTION_KEY: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"')
    print_error("Cannot continue without JWT_SECRET and DB_ENCRYPTION_KEY")
    sys.exit(1)
else:
    print_success(".env file found")
    
    # Check for critical keys
    env_content = ENV_FILE.read_text()
    has_jwt = "JWT_SECRET" in env_content and "your-secret" not in env_content.lower()
    has_db_key = "DB_ENCRYPTION_KEY" in env_content and "your-encryption" not in env_content.lower()
    
    if not has_jwt or not has_db_key:
        print_error("JWT_SECRET and/or DB_ENCRYPTION_KEY not properly configured in .env")
        sys.exit(1)
    
    print_success("JWT_SECRET and DB_ENCRYPTION_KEY configured")

print()

# ============================================================================
# STEP 2: Check and create data directory
# ============================================================================

print(f"{Colors.BLUE}[2/4]{Colors.RESET} Checking database directories...")

if not DATA_DIR.exists():
    print_info("Creating data directory...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

print_success(f"Data directory: {DATA_DIR}")
print()

# ============================================================================
# STEP 3: Initialize databases
# ============================================================================

print(f"{Colors.BLUE}[3/4]{Colors.RESET} Checking databases...")

SQLITE_FILE = DATA_DIR / "memory.db"
CHROMA_DIR = DATA_DIR / "chroma_db"

# Check SQLite
if SQLITE_FILE.exists():
    size = SQLITE_FILE.stat().st_size / 1024  # KB
    print_success(f"SQLite database exists ({size:.1f}KB)")
else:
    print_warning("SQLite database not found, will be created on startup")

# Check ChromaDB
if CHROMA_DIR.exists():
    print_success("ChromaDB directory exists")
else:
    print_warning("ChromaDB directory not found, will be created on startup")

print_info("Initializing database schemas...")

# Initialize databases using Python
init_script = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from auth.user_store import UserDatabase
from memory.sqlite_store_simplified import MemoryDatabase
from memory.vector_store import VectorStore

try:
    user_db = UserDatabase()
    user_db.connect()
    user_db.init_user_schema()
    user_db.close()
    print("   ✓ User database schema initialized")
except Exception as e:
    print(f"   ✗ Error initializing user database: {e}")
    sys.exit(1)

try:
    memory_db = MemoryDatabase()
    memory_db.connect()
    memory_db.init_schema()
    memory_db.close()
    print("   ✓ Memory database schema initialized")
except Exception as e:
    print(f"   ✗ Error initializing memory database: {e}")
    sys.exit(1)

try:
    vector_store = VectorStore()
    print("   ✓ Vector store (ChromaDB) initialized")
except Exception as e:
    print(f"   ✗ Error initializing vector store: {e}")
    sys.exit(1)
"""

try:
    os.chdir(BACKEND_DIR)
    result = subprocess.run(
        [sys.executable, "-c", init_script],
        capture_output=True,
        text=True
    )
    
    if result.stdout:
        print(result.stdout, end="")
    
    if result.returncode != 0:
        print_error("Database initialization failed")
        if result.stderr:
            print(result.stderr)
        sys.exit(1)
    
    print_success("All databases initialized")
except Exception as e:
    print_error(f"Failed to initialize databases: {e}")
    sys.exit(1)

print()

# ============================================================================
# STEP 4: Start the backend server
# ============================================================================

print(f"{Colors.BLUE}[4/4]{Colors.RESET} Starting backend server...")
print()

print_header("🟢 Starting LoanAgent Backend")

print_info(f"Server will run at: {Colors.BLUE}http://localhost:8000{Colors.RESET}")
print_info(f"Swagger UI: {Colors.BLUE}http://localhost:8000/docs{Colors.RESET}")
print_info(f"ReDoc: {Colors.BLUE}http://localhost:8000/redoc{Colors.RESET}")
print()
print_info("Press Ctrl+C to stop the server")
print()
print(f"{Colors.BLUE}{'='*80}{Colors.RESET}")
print()

# Start uvicorn
os.chdir(BACKEND_DIR)

try:
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ])
except KeyboardInterrupt:
    print_info("\nShutting down...")
    sys.exit(0)
except Exception as e:
    print_error(f"Failed to start server: {e}")
    sys.exit(1)
