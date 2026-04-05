"""
FastAPI Admin routes.
Protected routes for the secure admin dashboard.
"""

import os
from fastapi import APIRouter, HTTPException, status, Header, Depends
from typing import Annotated

from auth.utils import TokenManager
from memory.sqlite_store import MemoryDatabase
from config import SQLITE_PATH

# Create router
router = APIRouter(prefix="/admin", tags=["admin"])

# Dependency to check admin authorization
async def verify_admin_token(authorization: Annotated[str | None, Header()] = None):
    """
    Verify the user is an admin via JWT token.
    Throws 403 if missing, invalid, or role is not admin.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
        
    token = authorization.replace("Bearer ", "")
    payload = TokenManager.verify_jwt_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing or expired",
        )
        
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Admin access required.",
        )
        
    return payload


@router.get("/users")
async def get_all_users_decrypted(
    admin_payload: dict = Depends(verify_admin_token)
):
    """
    Get all users.
    Returns decrypted data from the MemoryDatabase.
    Requires admin privileges.
    """
    try:
        mem_db = MemoryDatabase(db_path=SQLITE_PATH)
        mem_db.connect()
        
        # In a real app we might paginate or only fetch summaries
        # Here we fetch all customer memories (which are decrypted automatically)
        customer_ids = mem_db.list_all_customers()
        users = []
        for cid in customer_ids:
            mem = mem_db.load_customer_memory(cid)
            if mem:
                users.append({
                    "customer_id": mem.customer_id,
                    "full_name": mem.full_name,
                    "last_updated": mem.last_updated.isoformat() if mem.last_updated else None,
                    "data": mem.model_dump()
                })
        mem_db.close()
        
        return {
            "success": True,
            "users": users
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch users: {str(e)}"
        )
