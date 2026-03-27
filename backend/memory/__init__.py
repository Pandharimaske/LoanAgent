"""
Memory module for LoanAgent.

Exports:
    Models:         MemoryStatus, ApplicationStatus, EntityRecord, FixedEntity,
                    CustomerMemoryNonPII, CustomerMemoryPII, SessionLog, FieldChangeLog
    SQLite store:   MemoryDatabase
    Vector store:   VectorStore
    Retriever:      MemoryRetriever
    Encryption:     EncryptionManager, get_encryption_manager
"""

from memory.models import (
    MemoryStatus,
    ApplicationStatus,
    EntityRecord,
    FixedEntity,
    CoApplicant,
    Guarantor,
    LoanRequest,
    DocumentSubmission,
    EmploymentHistory,
    CustomerMemoryNonPII,
    CustomerMemoryPII,
    SessionLog,
    FieldChangeLog,
    hash_pan,
    hash_aadhaar,
)

from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from memory.retriever import MemoryRetriever
from memory.encryption import EncryptionManager, get_encryption_manager

__all__ = [
    # Enums
    "MemoryStatus",
    "ApplicationStatus",
    # Core models
    "EntityRecord",
    "FixedEntity",
    "CoApplicant",
    "Guarantor",
    "LoanRequest",
    "DocumentSubmission",
    "EmploymentHistory",
    "CustomerMemoryNonPII",
    "CustomerMemoryPII",
    "SessionLog",
    "FieldChangeLog",
    # Helpers
    "hash_pan",
    "hash_aadhaar",
    # Storage
    "MemoryDatabase",
    "VectorStore",
    "MemoryRetriever",
    # Encryption
    "EncryptionManager",
    "get_encryption_manager",
]
