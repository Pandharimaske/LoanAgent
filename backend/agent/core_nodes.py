"""
Core infrastructure nodes for LangGraph workflow.

Nodes:
- check_token_threshold : Count tokens; LLM-summarize + trim if over threshold
- load_memory           : Load SQLite facts + ChromaDB context → memory_prompt_block
- router                : Route to handler (programmatic overrides → LLM decision)
- end_session           : Append assistant turn; write real LLM summary to ChromaDB
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
from agent.helpers import format_conversation_history, create_llm, rewrite_query_for_retrieval
from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from memory.retriever import MemoryRetriever
from auth.user_store import UserDatabase
from config import (
    SQLITE_PATH,
    CHROMA_PATH,
    TOKEN_THRESHOLD_PERCENT,
    SESSION_CONTEXT_WINDOW,
    VECTOR_SEARCH_TOP_K,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token counter
# ---------------------------------------------------------------------------

def _count_tokens(messages: List[Dict[str, str]]) -> int:
    """tiktoken cl100k_base; falls back to char/4 estimate."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return sum(len(enc.encode(m.get("content", "") or "")) for m in messages)
    except Exception:
        return sum(len(m.get("content", "") or "") // 4 for m in messages)


# ============================================================================
# NODE 1: CHECK_TOKEN_THRESHOLD
# ============================================================================

async def check_token_threshold(state: SessionState) -> SessionState:
    """
    Count tokens in message history.
    If ≥ 80 % of context window:
      - LLM-summarizes the older half of messages
      - Replaces them with a single system summary entry
      - Persists summary to ChromaDB for cross-session recall
    """
    try:
        messages: List[Dict[str, str]] = state.get("messages") or []
        current_tokens = _count_tokens(messages)
        state["total_tokens"] = current_tokens

        threshold = int(SESSION_CONTEXT_WINDOW * TOKEN_THRESHOLD_PERCENT)
        logger.info(
            f"[check_token_threshold] session={state.get('session_id','?')!r} "
            f"tokens={current_tokens} threshold={threshold} "
            f"msgs={len(messages)}"
        )

        if current_tokens >= threshold and len(messages) > 2:
            logger.warning("⚠️  Threshold exceeded — summarizing older half")

            split     = max(1, len(messages) // 2)
            old_msgs  = messages[:split]
            keep_msgs = messages[split:]

            old_text = "\n".join(
                f"{m.get('role','?').upper()}: {m.get('content','')}" for m in old_msgs
            )
            summary_prompt = (
                "Summarize this loan advisor conversation in 2-3 sentences. "
                "Keep all key facts: income, loan amount, employment, CIBIL, "
                "decisions, and open questions. Skip pleasantries.\n\n" + old_text
            )

            llm_generated = False
            try:
                llm = create_llm(temperature=0.2)
                resp = await llm.ainvoke(summary_prompt)
                summary_text  = resp.content if hasattr(resp, "content") else str(resp)
                summary_text  = summary_text.strip()
                llm_generated = bool(summary_text)   # True only when LLM returned real text
            except Exception as e:
                logger.error(f"❌ Summarization LLM call failed: {e}")
                summary_text  = f"[{len(old_msgs)} earlier messages summarized]"
                llm_generated = False  # fallback — do NOT persist this to DB

            state["messages"] = [{
                "role": "system",
                "content": f"[Earlier conversation summary]: {summary_text}",
                "timestamp": datetime.now().isoformat(),
            }] + keep_msgs
            state["total_tokens"]    = _count_tokens(state["messages"])
            state["should_summarize"] = True
            state["summary"]          = summary_text if llm_generated else None

            # Persist real LLM summary to ChromaDB
            customer_id = state.get("customer_id")
            session_id  = state.get("session_id")
            if llm_generated and customer_id and session_id:
                try:
                    vs = VectorStore(persist_path=CHROMA_PATH)
                    vs.add_session_summary(
                        customer_id=customer_id,
                        session_id=session_id,
                        summary_text=summary_text,
                    )
                    logger.info(f"📄 LLM summary → ChromaDB: {summary_text[:80]}…")
                except Exception as e:
                    logger.warning(f"⚠️  ChromaDB summary write failed: {e}")

                # ── Also persist summary to user_sessions.summary in SQLite ──
                try:
                    logger.info(
                        f"[summary_save] Saving to DB: session_id={session_id!r} "
                        f"summary_len={len(summary_text)} chars"
                    )
                    with UserDatabase(db_path=SQLITE_PATH) as db:
                        db.init_user_schema()   # ensure migration applied
                        saved = db.save_session_summary(session_id, summary_text)
                    if saved:
                        logger.info(f"[summary_save] SUCCESS: summary saved to user_sessions")
                    else:
                        logger.warning(f"[summary_save] FAIL: save_session_summary returned False for {session_id!r}")
                except Exception as e:
                    logger.warning(f"[summary_save] EXCEPTION: {e}")

            elif not llm_generated:
                logger.warning(
                    "⚠️  LLM summary FAILED — using fallback placeholder. "
                    "Summary NOT saved to DB. Check Ollama is running."
                )

            logger.info(f"✅ Compressed: {current_tokens} → {state['total_tokens']} tokens")
        else:
            state["should_summarize"] = False
            state["summary"]          = None

        return state

    except Exception as e:
        logger.error(f"❌ check_token_threshold failed: {e}", exc_info=True)
        state["error"]           = str(e)
        state["should_summarize"] = False
        return state


# ============================================================================
# NODE 2: LOAD_MEMORY
# ============================================================================

async def load_memory(state: SessionState) -> SessionState:
    """
    Build memory_prompt_block from 3 tiers:
      Tier 1 — SQLite structured facts (all known customer data)
      Tier 2 — ChromaDB top-K contextual chunks (semantic match to query)
      Tier 3 — ChromaDB real LLM session summaries (cross-session recall)

    Appends current user turn to messages. Does NOT reset history.
    """
    try:
        customer_id = state.get("customer_id")
        if not customer_id:
            state["error"] = "No customer_id in state"
            return state

        user_input = (state.get("user_input") or "").strip()

        # Init message list only if truly absent
        if "messages" not in state or state["messages"] is None:
            state["messages"] = []

        # Append current user turn
        if user_input:
            state["messages"].append({
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now().isoformat(),
            })

        # Build 3-tier context
        try:
            # Rewrite the raw user query into a keyword-dense retrieval query
            # before passing it to ChromaDB — improves semantic match quality
            messages_so_far = state.get("messages") or []
            conv_history = format_conversation_history(messages_so_far[:-1]) if messages_so_far else "No prior conversation"
            retrieval_query = await rewrite_query_for_retrieval(
                user_input=user_input or "general customer profile",
                conversation_history=conv_history,
            )

            retriever = MemoryRetriever(
                db=MemoryDatabase(db_path=SQLITE_PATH),
                vector_store=VectorStore(persist_path=CHROMA_PATH),
            )
            ctx = retriever.build_context(
                customer_id=customer_id,
                current_turn=retrieval_query,   # ← rewritten, not raw
                n_chunks=VECTOR_SEARCH_TOP_K,
                n_summaries=2,
            )
            retriever.close()

            with MemoryDatabase(db_path=SQLITE_PATH) as db:
                db.init_schema()
                customer_facts = db.get_all_facts_grouped(customer_id)

            state["customer_facts"]      = customer_facts
            state["memory_prompt_block"] = ctx["prompt_block"]
            state["dynamic_context"]     = [
                r["document"] for r in ctx["relevant_chunks"] if r.get("document")
            ]
            state["session_summaries"]   = [
                s["document"] for s in ctx["session_summaries"] if s.get("document")
            ]
            logger.info(
                f"✅ Memory: {len(customer_facts)} fact groups | "
                f"{len(state['dynamic_context'])} chunks | "
                f"{len(state['session_summaries'])} summaries"
            )
        except Exception as e:
            logger.error(f"❌ MemoryRetriever failed: {e}")
            state["customer_facts"]      = {}
            state["memory_prompt_block"] = ""
            state["dynamic_context"]     = []
            state["session_summaries"]   = []

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
    Routing priority:
      1. HITL pending fields   → handle_save_confirmation   (programmatic)
      2. Detected mismatches   → handle_mismatch_confirmation (programmatic)
      3. LLM decision          → handle_query | handle_general
    """
    try:
        user_input = state.get("user_input", "")
        if not user_input:
            state["next_handler"] = "handle_general"
            state["error"]        = "No user input"
            return state

        messages      = state.get("messages") or []
        conv_history  = format_conversation_history(messages[:-1], max_turns=6)
        memory_ctx    = state.get("memory_prompt_block") or "No context available"

        # 1. HITL override
        if state.get("pending_fields") and not state.get("memory_mismatches"):
            state["next_handler"]      = "handle_save_confirmation"
            state["router_reasoning"]  = "Financial fields staged — HITL confirmation needed"
            state["router_confidence"] = 1.0
            state["detected_intent"]   = "save_confirmation"
            logger.info("⏳ Router → handle_save_confirmation (HITL)")
            return state

        # 2. Mismatch override
        if state.get("memory_mismatches"):
            state["next_handler"]      = "handle_mismatch_confirmation"
            state["router_reasoning"]  = "Programmatic conflict detected"
            state["router_confidence"] = 1.0
            state["detected_intent"]   = "update_info (mismatch)"
            logger.info(f"⚠️  Router → handle_mismatch_confirmation ({len(state['memory_mismatches'])} conflicts)")
            return state

        # 3. LLM decision
        base_llm       = create_llm(temperature=0.3)
        structured_llm = base_llm.with_structured_output(RouterDecision)
        chain          = ROUTER_PROMPT | structured_llm

        decision: RouterDecision = await chain.ainvoke({
            "user_input":          user_input,
            "memory_context":      memory_ctx,
            "conversation_history": conv_history,
        })

        intent_map = {"handle_query": "query_loan", "handle_general": "general_chat"}
        state.update({
            "next_handler":      decision.next_handler,
            "router_reasoning":  decision.reasoning,
            "router_confidence": decision.confidence,
            "detected_intent":   intent_map.get(decision.next_handler, decision.next_handler),
            "intent_confidence": decision.confidence,
        })
        logger.info(f"🤖 Router → {decision.next_handler} ({decision.confidence:.2f})")
        return state

    except Exception as e:
        logger.error(f"❌ Router failed: {e}", exc_info=True)
        state.update({
            "next_handler":      "handle_general",
            "error":             f"Router error: {e}",
            "router_reasoning":  "Fallback due to error",
            "router_confidence": 0.0,
        })
        return state


# ============================================================================
# NODE 4: END_SESSION
# ============================================================================

async def end_session(state: SessionState) -> SessionState:
    """
    1. Append assistant response to message history.
    2. Write a REAL LLM-generated summary to ChromaDB (only if ≥4 turns).
       — No more fake template strings ("Session X | N turns | Last response:…")
    3. Recount tokens.
    """
    try:
        customer_id    = state.get("customer_id")
        session_id     = state.get("session_id")
        agent_response = state.get("agent_response", "")

        if not customer_id:
            state["error"] = "No customer_id — cannot persist"
            return state

        # 1. Append assistant turn
        if "messages" not in state or state["messages"] is None:
            state["messages"] = []

        state["messages"].append({
            "role": "assistant",
            "content": agent_response,
            "timestamp": datetime.now().isoformat(),
        })
        messages: List[Dict[str, str]] = state["messages"]

        # 2. Write REAL LLM summary to ChromaDB — only when meaningful content exists
        #    Threshold: ≥4 messages (2 user + 2 assistant turns minimum).
        #    We generate a compact fact-dense summary, NOT a template string.
        if len(messages) >= 4:
            try:
                # Only include user/assistant turns (skip system summary entries)
                turns_text = "\n".join(
                    f"{m.get('role','?').upper()}: {m.get('content','')}"
                    for m in messages
                    if m.get("role") in ("user", "assistant")
                )[:1500]  # cap prompt length

                summary_prompt = (
                    "Summarize this loan advisor conversation in 2-3 sentences. "
                    "Include only concrete facts: income figures, loan amounts, "
                    "employment details, CIBIL score, decisions made, and open questions. "
                    "Skip greetings and filler.\n\n" + turns_text
                )

                llm  = create_llm(temperature=0.2)
                resp = await llm.ainvoke(summary_prompt)
                summary_text = (
                    resp.content if hasattr(resp, "content") else str(resp)
                ).strip()

                if summary_text:
                    vs = VectorStore(persist_path=CHROMA_PATH)
                    vs.add_session_summary(
                        customer_id=customer_id,
                        session_id=session_id,
                        summary_text=summary_text,
                    )
                    logger.info(f"📄 Session summary → ChromaDB: {summary_text[:80]}…")

            except Exception as e:
                logger.warning(f"⚠️  Session summary write failed (non-fatal): {e}")

        # 3. Recount tokens
        state["total_tokens"]     = _count_tokens(messages)
        state["session_end_time"] = datetime.now().isoformat()

        logger.info(
            f"✅ end_session | tokens={state['total_tokens']} | msgs={len(messages)}"
        )
        return state

    except Exception as e:
        logger.error(f"❌ end_session failed: {e}", exc_info=True)
        state["error"] = str(e)
        return state
