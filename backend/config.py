"""
Configuration module for LoanAgent backend.
Loads settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# ============================================================================
# DIRECTORIES
# ============================================================================

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ============================================================================
# OLLAMA / LLM INFERENCE
# ============================================================================

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))

# ============================================================================
# EMBEDDINGS
# ============================================================================

EMBED_MODEL = os.getenv(
    "EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
)
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "32"))

# ============================================================================
# MEMORY & STORAGE
# ============================================================================

SQLITE_PATH = os.getenv("SQLITE_PATH", str(DATA_DIR / "memory.db"))
CHROMA_PATH = os.getenv("CHROMA_PATH", str(DATA_DIR / "chroma_db"))

# Create paths if they don't exist
Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)

# ============================================================================
# MEMORY THRESHOLDS & LIMITS
# ============================================================================

TOKEN_THRESHOLD = int(os.getenv("TOKEN_THRESHOLD", "2000"))
SESSION_CONTEXT_WINDOW = int(os.getenv("SESSION_CONTEXT_WINDOW", "4096"))
MAX_SESSION_TURNS = int(os.getenv("MAX_SESSION_TURNS", "50"))
VECTOR_SEARCH_TOP_K = int(os.getenv("VECTOR_SEARCH_TOP_K", "5"))

# ============================================================================
# LANGUAGE & NLP
# ============================================================================

DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "en")
SUPPORTED_LANGUAGES = ["en", "hi", "mixed"]
ENABLE_HINDI_SUPPORT = os.getenv("ENABLE_HINDI_SUPPORT", "true").lower() == "true"

# ============================================================================
# LOGGING & DEBUG
# ============================================================================

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ============================================================================
# DISPLAY CONFIG (for debugging)
# ============================================================================


def print_config():
    """Print current configuration (useful for debugging)."""
    print("\n" + "=" * 70)
    print("🔧 LoanAgent Configuration")
    print("=" * 70)
    
    print("\n📁 Directories:")
    print(f"   PROJECT_ROOT:  {PROJECT_ROOT}")
    print(f"   DATA_DIR:      {DATA_DIR}")
    print(f"   SQLITE_PATH:   {SQLITE_PATH}")
    print(f"   CHROMA_PATH:   {CHROMA_PATH}")
    
    print("\n🤖 Ollama / LLM:")
    print(f"   OLLAMA_BASE_URL:   {OLLAMA_BASE_URL}")
    print(f"   OLLAMA_MODEL:      {OLLAMA_MODEL}")
    print(f"   OLLAMA_TIMEOUT:    {OLLAMA_TIMEOUT}s")
    print(f"   OLLAMA_MAX_RETRIES: {OLLAMA_MAX_RETRIES}")
    
    print("\n🧠 Memory:")
    print(f"   TOKEN_THRESHOLD:        {TOKEN_THRESHOLD}")
    print(f"   SESSION_CONTEXT_WINDOW: {SESSION_CONTEXT_WINDOW}")
    print(f"   VECTOR_SEARCH_TOP_K:    {VECTOR_SEARCH_TOP_K}")
    
    print("\n🗣️  Language:")
    print(f"   DEFAULT_LANGUAGE:    {DEFAULT_LANGUAGE}")
    print(f"   ENABLE_HINDI_SUPPORT: {ENABLE_HINDI_SUPPORT}")
    
    print("\n⚙️  Other:")
    print(f"   DEBUG:    {DEBUG}")
    print(f"   LOG_LEVEL: {LOG_LEVEL}")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    print_config()
