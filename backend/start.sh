#!/bin/bash

###############################################################################
# LoanAgent Backend Startup Script
# 
# This script:
# 1. Checks if .env file exists
# 2. Verifies all required databases are initialized
# 3. Creates databases if missing
# 4. Starts the FastAPI backend server
###############################################################################

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
BACKEND_DIR="$SCRIPT_DIR"
DATA_DIR="$PROJECT_ROOT/data"

echo ""
echo "============================================================================"
echo -e "${BLUE}🚀 LoanAgent Backend Startup${NC}"
echo "============================================================================"
echo ""

# ============================================================================
# STEP 1: Check .env file
# ============================================================================

echo -e "${BLUE}[1/5]${NC} Checking environment configuration..."

if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found at $BACKEND_DIR/.env${NC}"
    echo -e "${YELLOW}    Creating template .env file...${NC}"
    
    cat > "$BACKEND_DIR/.env" << 'EOF'
# Generated .env template - PLEASE UPDATE WITH REAL VALUES

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
EOF
    
    echo -e "${YELLOW}    Please update .env with your JWT_SECRET and DB_ENCRYPTION_KEY!${NC}"
    echo -e "${YELLOW}    Generate keys using:${NC}"
    echo -e "${YELLOW}    JWT_SECRET: uv run python -c \"import secrets; print(secrets.token_urlsafe(32))\"${NC}"
    echo -e "${YELLOW}    DB_ENCRYPTION_KEY: uv run python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"${NC}"
    echo ""
else
    echo -e "${GREEN}✅${NC} .env file found"
    
    # Check for critical keys
    if ! grep -q "JWT_SECRET" "$BACKEND_DIR/.env"; then
        echo -e "${RED}❌ JWT_SECRET not found in .env${NC}"
        exit 1
    fi
    
    if ! grep -q "DB_ENCRYPTION_KEY" "$BACKEND_DIR/.env"; then
        echo -e "${RED}❌ DB_ENCRYPTION_KEY not found in .env${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅${NC} JWT_SECRET and DB_ENCRYPTION_KEY configured"
fi

echo ""

# ============================================================================
# STEP 2: Check and create data directory
# ============================================================================

echo -e "${BLUE}[2/5]${NC} Checking database directories..."

if [ ! -d "$DATA_DIR" ]; then
    echo -e "${YELLOW}📁 Creating data directory...${NC}"
    mkdir -p "$DATA_DIR"
fi

echo -e "${GREEN}✅${NC} Data directory: $DATA_DIR"

# ============================================================================
# STEP 3: Initialize databases if missing
# ============================================================================

echo ""
echo -e "${BLUE}[3/5]${NC} Checking databases..."

SQLITE_FILE="$DATA_DIR/memory.db"
CHROMA_DIR="$DATA_DIR/chroma_db"

# Check SQLite database
if [ -f "$SQLITE_FILE" ]; then
    SIZE=$(du -h "$SQLITE_FILE" | cut -f1)
    echo -e "${GREEN}✅${NC} SQLite database exists ($SIZE)"
else
    echo -e "${YELLOW}📝 SQLite database not found, will be created on startup${NC}"
fi

# Check ChromaDB directory
if [ -d "$CHROMA_DIR" ]; then
    echo -e "${GREEN}✅${NC} ChromaDB directory exists"
else
    echo -e "${YELLOW}📝 ChromaDB directory not found, will be created on startup${NC}"
fi

# Initialize databases using Python
echo -e "${YELLOW}🔧 Initializing database schemas...${NC}"

cd "$BACKEND_DIR"

uv run python << 'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from auth.user_store import UserDatabase
from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore

try:
    # Initialize user database
    user_db = UserDatabase()
    user_db.connect()
    user_db.init_user_schema()
    user_db.close()
    print("   ✓ User database schema initialized")
except Exception as e:
    print(f"   ✗ Error initializing user database: {e}")
    sys.exit(1)

try:
    # Initialize memory database
    memory_db = MemoryDatabase()
    memory_db.connect()
    memory_db.init_schema()
    memory_db.close()
    print("   ✓ Memory database schema initialized")
except Exception as e:
    print(f"   ✗ Error initializing memory database: {e}")
    sys.exit(1)

try:
    # Initialize vector store
    vector_store = VectorStore()
    print("   ✓ Vector store (ChromaDB) initialized")
except Exception as e:
    print(f"   ✗ Error initializing vector store: {e}")
    sys.exit(1)
PYEOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅${NC} All databases initialized"
else
    echo -e "${RED}❌ Database initialization failed${NC}"
    exit 1
fi

cd "$PROJECT_ROOT"

echo ""

# ============================================================================
# STEP 4: Ingest loan products into ChromaDB (runs only if collection is empty)
# ============================================================================

echo -e "${BLUE}[4/5]${NC} Checking loan product knowledge base..."

LOAN_JSON="$BACKEND_DIR/data/loan_products.json"

if [ ! -f "$LOAN_JSON" ]; then
    echo -e "${YELLOW}⚠️  data/loan_products.json not found — skipping loan knowledge ingestion${NC}"
    echo -e "${YELLOW}    Copy your loan_products.json to backend/data/ and restart.${NC}"
else
    # Check if the loan_products ChromaDB collection already has data
    LOAN_COUNT=$(uv run python -c "
import sys; sys.path.insert(0,'.')
try:
    from memory.loan_knowledge_store import LoanKnowledgeStore
    print(LoanKnowledgeStore().count())
except Exception:
    print(0)
" 2>/dev/null || echo "0")

    if [ "$LOAN_COUNT" -gt "0" ] 2>/dev/null; then
        echo -e "${GREEN}✅${NC} Loan knowledge base already populated ($LOAN_COUNT chunks) — skipping ingestion"
    else
        echo -e "${YELLOW}📚 Ingesting loan products into ChromaDB...${NC}"
        if uv run python scripts/ingest_loan_data.py --json "$LOAN_JSON"; then
            echo -e "${GREEN}✅${NC} Loan products ingested successfully"
        else
            echo -e "${YELLOW}⚠️  Loan product ingestion failed (non-fatal — server will still start)${NC}"
        fi
    fi
fi

echo ""

# ============================================================================
# STEP 4: Start the backend server
# ============================================================================

echo -e "${BLUE}[5/5]${NC} Starting backend server..."
echo ""

echo "============================================================================"
echo -e "${GREEN}🟢 Starting LoanAgent Backend${NC}"
echo "============================================================================"
echo ""
echo -e "Server will run at: ${BLUE}http://localhost:8000${NC}"
echo -e "Swagger UI: ${BLUE}http://localhost:8000/docs${NC}"
echo -e "ReDoc: ${BLUE}http://localhost:8000/redoc${NC}"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
echo "============================================================================"
echo ""

# Start the backend
cd "$BACKEND_DIR"
uv run -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
