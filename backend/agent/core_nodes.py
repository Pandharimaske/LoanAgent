"""
Core infrastructure nodes for LangGraph workflow.

Nodes:
- check_token_threshold: Count tokens; summarize + trim if threshold exceeded
- load_memory: Retrieve customer context from SQLite + ChromaDB
- router: LLM-based intelligent routing to appropriate handler
- end_session: Persist all updates after session completes
"""

import sys
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.state import SessionState
from agent.prompts import ROUTER_PROMPT
from agent.schemas import RouterDecision
from agent.helpers import extract_conflicts_with_llm, format_conversation_history, create_llm
from memory.sqlite_store_simplified import MemoryDatabase
from memory.vector_store import VectorStore
from config import (
    SQLITE_PATH,
    CHROMA_PATH,
    TOKEN_THRESHOLD_PERCENT,
    SESSION_CONTEXT_WINDOW,
    VECTOR_SEARCH_TOP_K,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token counting utility (tiktoken — already in pyproject deps)
# ---------------------------------------------------------------------------

def _count_tokens(messages: List[Dict[str, str]]) -> int:
    """
    Count total tokens across all messages using tiktoken cl100k_base.
    Falls back to a rough char/4 estimate if tiktoken unavailable.
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return sum(len(enc.encode(m.get("content", "") or "")) for m in messages)
    except Exception:
        # Rough fallback: ~4 chars per token
        return sum(len(m.get("content", "") or "") // 4 for m in messages)


# ============================================================================
# NODE 1: CHECK_TOKEN_THRESHOLD
# FIX #6 — actually count tokens, summarize old messages if over threshold
# ============================================================================

async def check_token_threshold(state: SessionState) -> SessionState:
    """
    Count tokens in current message history.
    If ≥ 80 % of context window → LLM-summarize the older half, trim buffer,
    recount tokens, and store summary to ChromaDB for cross-session recall.

    Runs FIRST in every session turn.
    """
    try:
        messages: List[Dict[str, str]] = state.get("messages") or []
        current_tokens = _count_tokens(messages)
        state["total_tokens"] = current_tokens

        threshold = int(SESSION_CONTEXT_WINDOW * TOKEN_THRESHOLD_PERCENT)
        logger.info(f"📊 Token Check: {current_tokens}/{threshold} (window={SESSION_CONTEXT_WINDOW})")

        if current_tokens >= threshold and len(messages) > 2:
            logger.warning("⚠️  Token threshold exceeded — summarizing older messages")

            # Keep the most recent 50 % of messages intact; summarize the rest
            split = max(1, len(messages) // 2)
            old_msgs  = messages[:split]
            keep_msgs = messages[split:]

            # Build summary prompt
            old_text = "\n".join(
                f"{m.get('role','?').upper()}: {m.get('content','')}" for m in old_msgs
            )
            summary_prompt = (
                "Summarize the following loan advisor conversation concisely, "
                "preserving all key facts (income, loan amount, employment, CIBIL, "
                "decisions made, and open questions):\n\n" + old_text
            )

            try:
                llm = create_llm(temperature=0.2)
                summary_resp = await llm.ainvoke(summary_prompt)
                summary_text = (
                    summary_resp.content
                    if hasattr(summary_resp, "content")
                    else str(summary_resp)
                )
            except Exception as e:
                logger.error(f"❌ Summarization LLM call failed: {e}")
                # Soft fallback: just trim without a meaningful summary
                summary_text = f"[Earlier conversation ({len(old_msgs)} messages) — details omitted to save context]"

            # Replace old messages with a single summary entry
            summary_entry: Dict[str, str] = {
                "role": "system",
                "content": f"[Conversation summary — earlier turns]: {summary_text}",
                "timestamp": datetime.now().isoformat(),
            }
            state["messages"] = [summary_entry] + keep_msgs
            state["total_tokens"] = _count_tokens(state["messages"])
            state["should_summarize"] = True
            state["summary"] = summary_text

            # Persist summary to ChromaDB for cross-session recall
            customer_id = state.get("customer_id")
            session_id  = state.get("session_id")
            if customer_id and session_id:
                try:
                    vs = VectorStore(persist_path=CHROMA_PATH)
                    vs.add_session_summary(
                        customer_id=customer_id,
                        session_id=session_id,
                        summary_text=summary_text,
                    )
                    logger.info("📄 In-session summary persisted to ChromaDB")
                except Exception as e:
                    logger.warning(f"⚠️  Could not persist summary to ChromaDB: {e}")

            logger.info(
                f"✅ Compressed: {current_tokens} → {state['total_tokens']} tokens "
                f"({len(old_msgs)} messages summarized)"
            )
        else:
            state["should_summarize"] = False
            state["summary"] = None

        return state

    except Exception as e:
        logger.error(f"❌ check_token_threshold failed: {e}", exc_info=True)
        state["error"] = str(e)
        state["should_summarize"] = False
        return state


# ============================================================================
# NODE 2: LOAD_MEMORY
# FIX #3 — use "document" key (not "text") when reading ChromaDB results
# FIX #5 — never reset messages; only initialise if truly absent
# ============================================================================

async def load_memory(state: SessionState) -> SessionState:
    """
    Load customer context from SQLite (confirmed facts) + ChromaDB (semantic).

    Does NOT reset message history — that is managed by check_token_threshold
    and chat_routes.  Only appends the current user input to history.

    Tier 1 — SQLite  : confirmed structured facts (income, CIBIL, name …)
    Tier 2 — ChromaDB: top-K semantically relevant chunks for this query
    """
    try:
        customer_id = state.get("customer_id")
        if not customer_id:
            state["error"] = "No customer_id in state"
            return state

        session_id  = state.get("session_id", f"session_{datetime.now().timestamp()}")
        user_input  = (state.get("user_input") or "").strip()

        # ----------------------------------------------------------------
        # FIX #5 — only initialise messages list if it is truly absent.
        # Chat routes already carries messages forward across turns.
        # ----------------------------------------------------------------
        if "messages" not in state or state["messages"] is None:
            state["messages"] = []

        # Append current user turn to in-memory history
        if user_input:
            state["messages"].append({
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now().isoformat(),
            })

        # ----------------------------------------------------------------
        # Tier 1 — SQLite: confirmed facts
        # ----------------------------------------------------------------
        try:
            with MemoryDatabase(db_path=SQLITE_PATH) as db:
                db.init_schema()   # no-op if schema already exists
                confirmed_facts = db.get_confirmed_facts(customer_id)
        except Exception as e:
            logger.error(f"❌ SQLite load failed: {e}")
            confirmed_facts = {}

        state["confirmed_facts"] = confirmed_facts
        logger.info(f"✅ SQLite: {len(confirmed_facts)} fact groups for {customer_id}")

        # ----------------------------------------------------------------
        # Tier 2 — ChromaDB: semantic search on user query
        # FIX #3 — results use key "document", not "text"
        # ----------------------------------------------------------------
        dynamic_context: List[str] = []
        if user_input:
            try:
                vs = VectorStore(persist_path=CHROMA_PATH)

                # Embed current user message for future retrieval
                vs.add_chunk(
                    customer_id=customer_id,
                    session_id=session_id,
                    text=user_input[:500],
                    topic_tag="user_input",
                )

                # Semantic search scoped to this customer
                results = vs.search(
                    customer_id=customer_id,
                    query_text=user_input,
                    n_results=VECTOR_SEARCH_TOP_K,
                )

                # FIX #3: key is "document", NOT "text"
                dynamic_context = [
                    r["document"] for r in results if r.get("document")
                ]
                logger.info(f"✅ ChromaDB: {len(dynamic_context)} chunks retrieved")
            except Exception as e:
                logger.warning(f"⚠️  ChromaDB load failed (non-fatal): {e}")

        state["dynamic_context"]  = dynamic_context
        state["session_summaries"] = []   # populated on demand; summaries go to ChromaDB

        return state

    except Exception as e:
        logger.error(f"❌ load_memory failed: {e}", exc_info=True)
        state["error"] = str(e)
        return state


# ============================================================================
# NODE 3: ROUTER
# ============================================================================

async def router(state: SessionState) -> SessionState:
    """
    LLM-based router using structured output binding (RouterDecision).
    Decides which handler node to invoke next.
    """
    try:
        user_input      = state.get("user_input", "")
        confirmed_facts = state.get("confirmed_facts", {})
        dynamic_context = state.get("dynamic_context", [])

        if not user_input:
            state["next_handler"] = "handle_general"
            state["error"] = "No user input provided"
            logger.warning("⚠️  Router: no user input — defaulting to handle_general")
            return state

        # Prepare context strings for the prompt
        facts_summary   = json.dumps(confirmed_facts, indent=2) if confirmed_facts else "No confirmed facts"
        context_summary = "\n".join(dynamic_context[:3]) if dynamic_context else "No relevant context"
        messages        = state.get("messages") or []
        # Exclude the current message (last item) from history shown to router
        conv_history    = format_conversation_history(messages[:-1])

        # Structured LLM chain
        base_llm       = create_llm(temperature=0.3)
        structured_llm = base_llm.with_structured_output(RouterDecision)
        chain          = ROUTER_PROMPT | structured_llm

        decision: RouterDecision = await chain.ainvoke({
            "user_input":           user_input,
            "facts_summary":        facts_summary,
            "context_summary":      context_summary,
            "conversation_history": conv_history,
        })

        state["next_handler"]       = decision.next_handler
        state["router_reasoning"]   = decision.reasoning
        state["router_confidence"]  = decision.confidence

        # If routing to mismatch handler, run a second LLM pass for conflict details
        if decision.next_handler == "handle_mismatch_confirmation":
            logger.info("🔍 Running conflict extraction pass …")
            mismatches = await extract_conflicts_with_llm(
                user_input, confirmed_facts, dynamic_context
            )
            state["mismatched_fields"] = mismatches
            state["has_mismatch"]      = bool(mismatches)
        else:
            state["mismatched_fields"] = {}
            state["has_mismatch"]      = False

        logger.info(
            f"🤖 Router → {decision.next_handler} "
            f"(conf={decision.confidence:.2f}) | {decision.reasoning[:80]}"
        )
        return state

    except Exception as e:
        logger.error(f"❌ Router failed: {e}", exc_info=True)
        state.update({
            "next_handler":      "handle_general",
            "error":             f"Router error: {str(e)}",
            "has_mismatch":      False,
            "mismatched_fields": {},
            "router_reasoning":  "Fallback due to error",
            "router_confidence": 0.0,
        })
        return state


# ============================================================================
# NODE 4: END_SESSION
# FIX #1 — move `messages` assignment BEFORE the loop that iterates over it
# ============================================================================

async def end_session(state: SessionState) -> SessionState:
    """
    Persist session results to SQLite + ChromaDB.

    Steps:
    1. Append agent response to message history
    2. Store ALL messages session-wise to ChromaDB
    3. Create and store session summary to ChromaDB
    4. Update token count
    """
    try:
        customer_id    = state.get("customer_id")
        session_id     = state.get("session_id")
        agent_response = state.get("agent_response", "")

        if not customer_id:
            state["error"] = "No customer_id — cannot persist"
            return state

        # ----------------------------------------------------------------
        # 1. Append agent response to message history
        # ----------------------------------------------------------------
        if "messages" not in state or state["messages"] is None:
            state["messages"] = []

        state["messages"].append({
            "role": "assistant",
            "content": agent_response,
            "timestamp": datetime.now().isoformat(),
        })

        # ----------------------------------------------------------------
        # FIX #1 — assign `messages` BEFORE the loop that uses it
        # ----------------------------------------------------------------
        messages: List[Dict[str, str]] = state["messages"]

        # ----------------------------------------------------------------
        # 2. Store all messages session-wise to ChromaDB
        # ----------------------------------------------------------------
        try:
            vs = VectorStore(persist_path=CHROMA_PATH)
            stored = 0
            for msg in messages:
                role    = msg.get("role", "unknown")
                content = msg.get("content", "")
                if not content:
                    continue
                vs.add_chunk(
                    customer_id=customer_id,
                    session_id=session_id,
                    text=content[:500],
                    topic_tag=f"{role}_message",
                )
                stored += 1
            logger.info(f"✅ ChromaDB: {stored} messages stored for session {session_id}")
        except Exception as e:
            logger.warning(f"⚠️  ChromaDB message persistence failed: {e}")

        # ----------------------------------------------------------------
        # 3. Create and store session summary
        # ----------------------------------------------------------------
        if len(messages) >= 2:
            try:
                # Compact summary: final response + turn count
                summary_text = (
                    f"Session {session_id} | {len(messages)} turns | "
                    f"Last response: {agent_response[:300]}"
                )
                vs.add_session_summary(
                    customer_id=customer_id,
                    session_id=session_id,
                    summary_text=summary_text,
                )
                logger.info("📄 Session summary stored to ChromaDB")
            except Exception as e:
                logger.warning(f"⚠️  Session summary failed: {e}")

        # ----------------------------------------------------------------
        # 4. Recount tokens after appending assistant turn
        # ----------------------------------------------------------------
        state["total_tokens"] = _count_tokens(messages)
        state["session_end_time"] = datetime.now().isoformat()

        logger.info(
            f"✅ end_session complete | tokens={state['total_tokens']} | "
            f"msgs={len(messages)}"
        )
        return state

    except Exception as e:
        logger.error(f"❌ end_session failed: {e}", exc_info=True)
        state["error"] = str(e)
        return state
