"""
ChromaDB Vector Store for LoanAgent memory.

Design:
    - One collection per customer (hard isolation between customers)
    - Each session summary stored as a separate document
    - Conversation chunks stored with session_id metadata
    - Soft-delete only — retracted docs get status="retracted" marker
    - Semantic search scoped to a single customer's collection
"""

import chromadb
from chromadb.config import Settings
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CHROMA_PATH, VECTOR_SEARCH_TOP_K

logger = logging.getLogger(__name__)


class VectorStore:
    """Per-customer ChromaDB vector store with session-level separation."""

    def __init__(self, persist_path: str = CHROMA_PATH):
        """
        Initialize ChromaDB client with persistent storage.

        Args:
            persist_path: Directory for ChromaDB persistence.
        """
        self.client = chromadb.PersistentClient(path=persist_path)
        logger.info(f"ChromaDB initialized at: {persist_path}")

    # ========================================================================
    # COLLECTION MANAGEMENT
    # ========================================================================

    def _get_collection(self, customer_id: str) -> chromadb.Collection:
        """
        Get or create a collection for a specific customer.
        Collection name: 'customer_{customer_id}'

        Args:
            customer_id: Unique customer identifier.

        Returns:
            ChromaDB Collection for this customer.
        """
        collection_name = f"customer_{customer_id}".lower()
        # ChromaDB collection names: 3-63 chars, alphanumeric + underscores/hyphens
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"customer_id": customer_id, "created_at": str(datetime.now())},
        )

    def delete_customer_collection(self, customer_id: str) -> bool:
        """
        Delete an entire customer collection (use only for admin/testing).

        Args:
            customer_id: Customer whose collection to delete.

        Returns:
            True if deleted, False if collection didn't exist.
        """
        collection_name = f"customer_{customer_id}".lower()
        try:
            self.client.delete_collection(name=collection_name)
            logger.info(f"Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.warning(f"Collection {collection_name} not found: {e}")
            return False

    # ========================================================================
    # SESSION SUMMARIES — Each stored as a separate document
    # ========================================================================

    def add_session_summary(
        self,
        customer_id: str,
        session_id: str,
        summary_text: str,
        session_date: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> str:
        """
        Store a session summary as a separate document.
        Each session gets exactly one summary doc with a deterministic ID.

        Args:
            customer_id: Customer identifier.
            session_id: Session identifier (e.g., "S1", "S3").
            summary_text: The summary text to store.
            session_date: Human-readable date (e.g., "last Tuesday").
            agent_id: ID of the agent who handled the session.

        Returns:
            Document ID of the stored summary.
        """
        collection = self._get_collection(customer_id)
        doc_id = f"{session_id}_summary"
        timestamp = str(datetime.now())

        metadata = {
            "customer_id": customer_id,
            "session_id": session_id,
            "type": "summary",
            "status": "active",
            "timestamp": timestamp,
        }

        if session_date:
            metadata["session_date_human"] = session_date
        if agent_id:
            metadata["agent_id"] = agent_id

        # Upsert — if session summary already exists, update it
        collection.upsert(
            ids=[doc_id],
            documents=[summary_text],
            metadatas=[metadata],
        )

        logger.info(f"Stored session summary: {doc_id} for customer {customer_id}")
        return doc_id

    def get_session_summary(
        self, customer_id: str, session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific session's summary by session_id.

        Args:
            customer_id: Customer identifier.
            session_id: Session to retrieve summary for.

        Returns:
            Dict with 'document' and 'metadata', or None if not found.
        """
        collection = self._get_collection(customer_id)
        doc_id = f"{session_id}_summary"

        try:
            result = collection.get(ids=[doc_id])

            if result["documents"] and result["documents"][0]:
                return {
                    "id": doc_id,
                    "document": result["documents"][0],
                    "metadata": result["metadatas"][0] if result["metadatas"] else {},
                }
        except Exception as e:
            logger.warning(f"Summary not found for {session_id}: {e}")

        return None

    def get_all_session_summaries(
        self, customer_id: str, only_active: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all session summaries for a customer.

        Args:
            customer_id: Customer identifier.
            only_active: If True, exclude retracted summaries.

        Returns:
            List of dicts with 'id', 'document', 'metadata', sorted by timestamp.
        """
        collection = self._get_collection(customer_id)

        where_filter = {"type": "summary"}
        if only_active:
            where_filter = {
                "$and": [
                    {"type": "summary"},
                    {"status": "active"},
                ]
            }

        try:
            results = collection.get(where=where_filter)
        except Exception as e:
            logger.warning(f"No summaries found for customer {customer_id}: {e}")
            return []

        summaries = []
        if results["documents"]:
            for i in range(len(results["documents"])):
                summaries.append(
                    {
                        "id": results["ids"][i],
                        "document": results["documents"][i],
                        "metadata": results["metadatas"][i]
                        if results["metadatas"]
                        else {},
                    }
                )

        # Sort by timestamp (oldest first)
        summaries.sort(key=lambda x: x["metadata"].get("timestamp", ""))
        return summaries

    def get_last_n_summaries(
        self, customer_id: str, n: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Get the last N session summaries (chronological order).
        Used for context injection into prompts.

        Args:
            customer_id: Customer identifier.
            n: Number of recent summaries to retrieve.

        Returns:
            Last N summaries, oldest first.
        """
        all_summaries = self.get_all_session_summaries(customer_id, only_active=True)
        return all_summaries[-n:] if len(all_summaries) > n else all_summaries

    # ========================================================================
    # CONVERSATION CHUNKS — Individual turns / facts
    # ========================================================================

    def add_chunk(
        self,
        customer_id: str,
        session_id: str,
        text: str,
        topic_tag: Optional[str] = None,
        turn_index: Optional[int] = None,
        chunk_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Store a conversation chunk (a fact, turn, or extracted info).

        Args:
            customer_id: Customer identifier.
            session_id: Session this chunk belongs to.
            text: The chunk content.
            topic_tag: Optional topic tag (e.g., "income", "guarantor").
            turn_index: Position in the conversation.
            chunk_id: Custom ID. If None, auto-generated.
            extra_metadata: Optional extra key-value pairs merged into metadata.

        Returns:
            Document ID of the stored chunk.
        """
        collection = self._get_collection(customer_id)
        timestamp = str(datetime.now())

        if chunk_id is None:
            # Generate deterministic ID: session + turn index or timestamp
            suffix = f"turn_{turn_index}" if turn_index is not None else timestamp.replace(" ", "_")
            chunk_id = f"{session_id}_chunk_{suffix}"

        metadata = {
            "customer_id": customer_id,
            "session_id": session_id,
            "type": "chunk",
            "status": "active",
            "timestamp": timestamp,
        }

        if topic_tag:
            metadata["topic_tag"] = topic_tag
        if turn_index is not None:
            metadata["turn_index"] = turn_index

        # Merge caller-supplied extra metadata (string values only — ChromaDB requirement)
        if extra_metadata:
            for k, v in extra_metadata.items():
                metadata[k] = str(v) if not isinstance(v, (str, int, float, bool)) else v

        collection.upsert(
            ids=[chunk_id],
            documents=[text],
            metadatas=[metadata],
        )

        logger.info(f"Stored chunk: {chunk_id} for customer {customer_id}")
        return chunk_id

    # ========================================================================
    # SEMANTIC SEARCH
    # ========================================================================

    def search(
        self,
        customer_id: str,
        query_text: str,
        n_results: int = VECTOR_SEARCH_TOP_K,
        doc_type: Optional[str] = None,
        session_id: Optional[str] = None,
        only_active: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across a customer's memory.

        Args:
            customer_id: Customer to search within.
            query_text: The search query (will be embedded).
            n_results: Max results to return.
            doc_type: Filter by type — "summary" or "chunk". None = both.
            session_id: Filter to a specific session. None = all sessions.
            only_active: Exclude retracted documents.

        Returns:
            List of results with 'id', 'document', 'metadata', 'distance'.
        """
        collection = self._get_collection(customer_id)

        # Build where filter
        conditions = []
        if only_active:
            conditions.append({"status": "active"})
        if doc_type:
            conditions.append({"type": doc_type})
        if session_id:
            conditions.append({"session_id": session_id})

        where_filter = None
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        try:
            # ChromaDB raises an error when querying a collection with 0 docs
            if collection.count() == 0:
                return []
            results = collection.query(
                query_texts=[query_text],
                n_results=min(n_results, collection.count()),
                where=where_filter,
            )
        except Exception as e:
            logger.error(f"Search failed for customer {customer_id}: {e}")
            return []

        # Flatten results into a clean list
        search_results = []
        if results["documents"] and results["documents"][0]:
            for i in range(len(results["documents"][0])):
                search_results.append(
                    {
                        "id": results["ids"][0][i],
                        "document": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i]
                        if results["metadatas"]
                        else {},
                        "distance": results["distances"][0][i]
                        if results["distances"]
                        else None,
                    }
                )

        return search_results

    def search_chunks(
        self,
        customer_id: str,
        query_text: str,
        n_results: int = VECTOR_SEARCH_TOP_K,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search only conversation chunks (not summaries)."""
        return self.search(
            customer_id=customer_id,
            query_text=query_text,
            n_results=n_results,
            doc_type="chunk",
            session_id=session_id,
        )

    def search_summaries(
        self,
        customer_id: str,
        query_text: str,
        n_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """Semantic search across session summaries only."""
        return self.search(
            customer_id=customer_id,
            query_text=query_text,
            n_results=n_results,
            doc_type="summary",
        )

    # ========================================================================
    # RETRACTION — Soft delete only
    # ========================================================================

    def retract_chunk(
        self,
        customer_id: str,
        chunk_id: str,
        session_id: str,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Soft-delete a chunk by marking it as retracted.
        Writes a retraction marker doc, then updates the original's status.

        Args:
            customer_id: Customer identifier.
            chunk_id: ID of the chunk to retract.
            session_id: Session in which the retraction happened.
            reason: Optional reason for retraction.

        Returns:
            True if retracted, False if chunk not found.
        """
        collection = self._get_collection(customer_id)

        # Fetch original document
        try:
            original = collection.get(ids=[chunk_id])
            if not original["documents"] or not original["documents"][0]:
                logger.warning(f"Chunk {chunk_id} not found for retraction.")
                return False
        except Exception:
            logger.warning(f"Chunk {chunk_id} not found.")
            return False

        original_text = original["documents"][0]
        original_metadata = original["metadatas"][0] if original["metadatas"] else {}

        # Write retraction marker document
        retraction_metadata = {
            **original_metadata,
            "status": "retracted",
            "retracted_in": session_id,
            "retracted_at": str(datetime.now()),
        }
        if reason:
            retraction_metadata["retracted_reason"] = reason

        retraction_id = f"{chunk_id}_retracted"
        collection.upsert(
            ids=[retraction_id],
            documents=[f"[RETRACTED] {original_text}"],
            metadatas=[retraction_metadata],
        )

        # Update original document status to retracted
        original_metadata["status"] = "retracted"
        original_metadata["retracted_in"] = session_id
        original_metadata["retracted_at"] = str(datetime.now())
        if reason:
            original_metadata["retracted_reason"] = reason

        collection.update(
            ids=[chunk_id],
            metadatas=[original_metadata],
        )

        logger.info(f"Retracted chunk: {chunk_id} (reason: {reason})")
        return True

    def retract_session_summary(
        self,
        customer_id: str,
        session_id: str,
        reason: Optional[str] = None,
    ) -> bool:
        """Retract a session's summary (soft delete)."""
        doc_id = f"{session_id}_summary"
        return self.retract_chunk(
            customer_id=customer_id,
            chunk_id=doc_id,
            session_id=session_id,
            reason=reason,
        )

    # ========================================================================
    # UTILITIES
    # ========================================================================

    def get_customer_doc_count(self, customer_id: str) -> int:
        """Get total number of documents stored for a customer."""
        collection = self._get_collection(customer_id)
        return collection.count()

    def get_session_chunks(
        self, customer_id: str, session_id: str, only_active: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific session.

        Args:
            customer_id: Customer identifier.
            session_id: Session to retrieve chunks for.
            only_active: Exclude retracted chunks.

        Returns:
            List of chunk dicts sorted by turn_index.
        """
        collection = self._get_collection(customer_id)

        conditions = [
            {"session_id": session_id},
            {"type": "chunk"},
        ]
        if only_active:
            conditions.append({"status": "active"})

        where_filter = {"$and": conditions}

        try:
            results = collection.get(where=where_filter)
        except Exception as e:
            logger.warning(f"No chunks found for session {session_id}: {e}")
            return []

        chunks = []
        if results["documents"]:
            for i in range(len(results["documents"])):
                chunks.append(
                    {
                        "id": results["ids"][i],
                        "document": results["documents"][i],
                        "metadata": results["metadatas"][i]
                        if results["metadatas"]
                        else {},
                    }
                )

        # Sort by turn_index if available
        chunks.sort(key=lambda x: x["metadata"].get("turn_index", 0))
        return chunks

    def list_all_customers(self) -> List[str]:
        """List all customer IDs that have collections."""
        collections = self.client.list_collections()
        customer_ids = []
        for col in collections:
            if col.name.startswith("customer_"):
                customer_ids.append(col.name.replace("customer_", "", 1))
        return customer_ids


# ============================================================================
# QUICK SMOKE TEST
# ============================================================================


if __name__ == "__main__":
    print("=" * 60)
    print("🧪 VectorStore Smoke Test")
    print("=" * 60)

    # Use a temp path for testing
    import tempfile
    import os

    test_dir = os.path.join(tempfile.gettempdir(), "chroma_test")
    store = VectorStore(persist_path=test_dir)

    customer = "RAJESH_001"

    # --- Add session summaries ---
    print("\n1. Adding session summaries...")
    store.add_session_summary(
        customer_id=customer,
        session_id="S1",
        summary_text="Rajesh applied for home loan. Income ₹45,000/year. Wife Sunita as co-applicant. Documents pending.",
        session_date="Monday, Jan 15",
        agent_id="AGENT_A",
    )
    store.add_session_summary(
        customer_id=customer,
        session_id="S2",
        summary_text="Follow-up call. Land documents submitted. Property in Pune. Loan amount ₹25 lakhs requested.",
        session_date="Wednesday, Jan 17",
        agent_id="AGENT_B",
    )
    store.add_session_summary(
        customer_id=customer,
        session_id="S3",
        summary_text="Rajesh updated income to ₹60,000. Conflict detected with earlier ₹45,000. Confirmed ₹60,000 is correct.",
        session_date="last Tuesday",
        agent_id="AGENT_A",
    )
    print("   ✅ 3 session summaries stored")

    # --- Retrieve individual summary ---
    print("\n2. Retrieving S2 summary...")
    s2 = store.get_session_summary(customer, "S2")
    if s2:
        print(f"   ✅ Found: {s2['document'][:80]}...")
    else:
        print("   ❌ Not found!")

    # --- Get all summaries ---
    print("\n3. All summaries (chronological):")
    all_sums = store.get_all_session_summaries(customer)
    for s in all_sums:
        print(f"   [{s['metadata']['session_id']}] {s['document'][:60]}...")

    # --- Last N summaries ---
    print("\n4. Last 2 summaries:")
    last_two = store.get_last_n_summaries(customer, n=2)
    for s in last_two:
        print(f"   [{s['metadata']['session_id']}] {s['document'][:60]}...")

    # --- Add chunks ---
    print("\n5. Adding conversation chunks...")
    store.add_chunk(customer, "S1", "Rajesh mentioned income is ₹45,000 per year", topic_tag="income", turn_index=1)
    store.add_chunk(customer, "S1", "Wife Sunita will be co-applicant", topic_tag="co_applicant", turn_index=2)
    store.add_chunk(customer, "S3", "Rajesh says income is now ₹60,000", topic_tag="income", turn_index=1)
    print("   ✅ 3 chunks stored")

    # --- Semantic search ---
    print("\n6. Searching: 'what is the income?'")
    results = store.search(customer, "what is the income?", n_results=3)
    for r in results:
        print(f"   [{r['metadata'].get('type')}] (dist: {r['distance']:.3f}) {r['document'][:60]}...")

    # --- Search chunks only ---
    print("\n7. Search chunks only: 'co-applicant details'")
    chunks = store.search_chunks(customer, "co-applicant details", n_results=2)
    for c in chunks:
        print(f"   [{c['metadata'].get('session_id')}] {c['document'][:60]}...")

    # --- Retraction ---
    print("\n8. Retracting S1 income chunk...")
    chunk_id = "S1_chunk_turn_1"
    retracted = store.retract_chunk(customer, chunk_id, session_id="S3", reason="Income updated to ₹60,000")
    print(f"   {'✅ Retracted' if retracted else '❌ Failed'}")

    # --- Verify retracted chunk excluded from search ---
    print("\n9. Searching after retraction: 'income'")
    results = store.search_chunks(customer, "income", n_results=3)
    for r in results:
        print(f"   [{r['metadata'].get('session_id')}] (status: {r['metadata'].get('status')}) {r['document'][:60]}...")

    # --- Stats ---
    print(f"\n10. Total docs for {customer}: {store.get_customer_doc_count(customer)}")
    print(f"    All customers: {store.list_all_customers()}")

    # Cleanup
    store.delete_customer_collection(customer)
    print("\n✅ Test complete, collection cleaned up.")
    print("=" * 60)
