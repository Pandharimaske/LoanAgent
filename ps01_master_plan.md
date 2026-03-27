# PS-01 — The Loan Officer Who Never Forgets
## Master Build Plan · CODEAPEX 2.0 · BrainBack

---

## 0. Problem in one line

Bank agents forget everything between calls. Build an SLM-powered memory layer that makes every agent feel like they were always listening — across sessions, days, and agents.

---

## 1. Hardware & Runtime Target

| Component | Spec |
|-----------|------|
| CPU | Intel i5-12500H |
| RAM | 16 GB |
| GPU | RTX 3050 — 4 GB VRAM |
| OS | Windows / Linux |
| Inference target | Qwen2.5-3B-Instruct Q4_K_M via Ollama |
| Embedding target | paraphrase-multilingual-MiniLM-L12-v2 on CPU |
| Summarization | Anthropic Claude API (offloaded, threshold-triggered) |

---

## 2. Full Technology Stack

### Backend / Orchestration
- `langchain` — SummaryBufferMemory, document loaders
- `langgraph` — session state machine (core orchestration)
- `fastapi` — REST API layer
- `uvicorn` — ASGI server

### SLM / Inference
- `ollama` — local model server (GPU-accelerated)
- `anthropic` — Claude API for summarization when threshold exceeded
- `httpx` — async HTTP calls to Ollama

### Memory & Storage
- `chromadb` — vector store for dynamic/unstructured memories
- `SQLite` (stdlib) — structured KV store for fixed entities + history
- `sentence-transformers` — multilingual embeddings (CPU)
  - Model: `paraphrase-multilingual-MiniLM-L12-v2`

### Data Validation & Schema
- `pydantic>=2.0` — all memory models, entity schemas, API request/response
- `python-dotenv` — environment and config management
- `tiktoken` — token counting for summarization threshold

### NLP / Language
- `langdetect` — detect Hindi vs English per turn
- `indic-nlp-library` — Hindi tokenization (optional, skip if install fails)
- `tiktoken` — token threshold for memory compression trigger

### Demo UI & Dev
- `streamlit` — demo UI + live memory state panel
- `pytest` — session flow tests
- `requirements.txt` — pinned dependencies

---

## 3. Architecture Overview

```
Agent Turn Input (Hindi / English)
        ↓
  [FastAPI endpoint]
        ↓
  [LangGraph State Machine]
     ├── Node 1: load_memory
     ├── Node 2: extract_entities
     ├── Node 3: detect_conflicts
     ├── Node 4: (branch) ask_user OR update_memory
     ├── Node 5: retrieve_context
     ├── Node 6: slm_inference
     ├── Node 7: check_token_threshold → (if exceeded) summarize
     └── Node 8: end_session → persist + summarize
        ↓
  Agent Response (conversational recall)
        ↓
  [Memory Update Loop]
     ├── ChromaDB  ← unstructured / dynamic chunks
     └── SQLite    ← fixed entities + update_history
```

---

## 4. Memory Architecture (3-Tier)

### Tier 1 — Structured KV (SQLite)
For fixed, always-relevant loan entities. Fast O(1) lookup by customer_id.

**Fixed entity list (home loan):**
- income
- co_applicant name
- existing_emi amount
- land_documents (list)
- loan_amount_requested
- employment_type
- property_location
- guarantor (dynamic overflow candidate)

### Tier 2 — Vector Store (ChromaDB)
For everything dynamic that doesn't fit the fixed schema. Every conversation chunk stored with rich metadata.

```python
{
  "document": "Rajesh mentioned his father will act as guarantor",
  "metadata": {
    "customer_id": "R001",
    "session_id": "S3",
    "timestamp": "2024-01-16T14:23:00",
    "session_date_human": "last Tuesday",
    "topic_tag": "guarantor",
    "status": "active"   # or "retracted"
  }
}
```

### Tier 3 — Summary Buffer
Compressed session logs. After each session ends, SLM writes a 3-5 line summary. Next session loads last N summaries as context prefix. Also triggered mid-session when token count exceeds threshold.

---

## 5. Pydantic Memory Models

```python
from pydantic import BaseModel
from typing import Any, Optional, List
from datetime import datetime
from enum import Enum

class MemoryStatus(str, Enum):
    PENDING    = "pending"     # mentioned, not confirmed
    CONFIRMED  = "confirmed"   # explicitly confirmed by user
    SUPERSEDED = "superseded"  # replaced by newer confirmed value
    RETRACTED  = "retracted"   # user said this was wrong

class EntityRecord(BaseModel):
    value: Any
    status: MemoryStatus = MemoryStatus.PENDING
    timestamp: datetime
    session_id: str
    confirmed_at: Optional[datetime] = None
    retracted_reason: Optional[str] = None

class FixedEntity(BaseModel):
    current: Optional[EntityRecord] = None
    history: List[EntityRecord] = []

class CustomerMemory(BaseModel):
    customer_id: str
    name: Optional[FixedEntity] = None
    income: Optional[FixedEntity] = None
    co_applicant: Optional[FixedEntity] = None
    existing_emi: Optional[FixedEntity] = None
    land_documents: Optional[FixedEntity] = None
    loan_amount: Optional[FixedEntity] = None
    employment_type: Optional[FixedEntity] = None
    property_location: Optional[FixedEntity] = None
    created_at: datetime
    last_updated: datetime

class SessionLog(BaseModel):
    session_id: str
    customer_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    raw_turns: List[dict] = []
    agent_id: Optional[str] = None
```

---

## 6. SQLite Schema

```sql
CREATE TABLE customer_memory (
    customer_id   TEXT PRIMARY KEY,
    fixed_entities JSON,        -- serialized CustomerMemory pydantic model
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_updated  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session_log (
    session_id    TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL,
    started_at    DATETIME,
    ended_at      DATETIME,
    summary       TEXT,         -- SLM-generated session summary
    raw_turns     JSON,         -- full conversation (compressed after threshold)
    agent_id      TEXT,
    FOREIGN KEY (customer_id) REFERENCES customer_memory(customer_id)
);

CREATE INDEX idx_session_customer ON session_log(customer_id);
CREATE INDEX idx_session_started  ON session_log(started_at);
```

---

## 7. LangGraph State Machine

### State Schema
```python
from typing import TypedDict, List, Optional

class SessionState(TypedDict):
    customer_id:        str
    session_id:         str
    current_turn:       str               # latest user message
    conversation_history: List[dict]      # all turns this session
    loaded_memory:      Optional[dict]    # CustomerMemory as dict
    extracted_entities: Optional[dict]    # from current turn
    conflicts:          List[dict]        # detected conflicts
    retrieved_context:  str               # memory injected into prompt
    response:           str               # SLM output
    token_count:        int
    session_ended:      bool
```

### Graph Nodes
```
load_memory
    ↓
extract_entities         # SLM extracts structured entities from turn
    ↓
detect_conflicts         # compare extracted vs existing CONFIRMED values
    ↓
[router] ──── has_conflicts? ──── YES → ask_user (generate clarification)
    │                                        ↓
    NO                              wait for user response
    ↓                                        ↓
update_memory ←────────────────── resolve_conflict
    ↓
retrieve_context         # vector search + KV lookup + last 2 summaries
    ↓
build_prompt             # system prompt injection with memory
    ↓
slm_inference            # Ollama → Qwen2.5-3B
    ↓
check_token_threshold    # if tokens > 2000 → trigger summarization
    ↓
[router] ──── session_ended? ──── YES → end_session (summary + persist)
    │
    NO → return response to agent
```

---

## 8. Memory Retrieval — Context Builder

When building the system prompt for each turn, inject:

```
1. Structured KV facts (all CONFIRMED entities for this customer)
2. Top-5 semantically relevant chunks from ChromaDB
   (query = current turn text, filter = customer_id)
3. Last 2 session summaries in chronological order
```

**Prompt template:**
```
You are a bank agent assistant with perfect memory.

WHAT YOU KNOW ABOUT THIS CUSTOMER:
{structured_kv_facts}

RELEVANT PAST CONTEXT:
{vector_retrieved_chunks}

RECENT SESSION SUMMARIES:
{last_2_summaries}

CURRENT CONVERSATION:
{conversation_history}

Respond naturally. If recalling past information, reference when it was mentioned.
Never say "according to my records" — speak like you remembered it yourself.
```

---

## 9. Summarization — Sliding Window Strategy

**Trigger condition:** `token_count(conversation_history) > 2000`

**Action:**
1. Take oldest 50% of turns
2. Send to Claude API (PAN/income fields masked before sending):
   ```
   Summarize this bank loan conversation. Preserve: customer name,
   all amounts mentioned, document names, dates, co-applicant info,
   any unresolved issues. Be concise, 3-5 sentences max.
   ```
3. Replace old turns with `{"role": "system", "content": "[SUMMARY] ..."}`
4. Keep recent 50% verbatim

**Sensitive data masking before Claude API call:**
```python
import re
def mask_sensitive(text: str) -> str:
    text = re.sub(r'\b[A-Z]{5}\d{4}[A-Z]\b', '[PAN_REDACTED]', text)
    text = re.sub(r'₹[\d,]+', '[AMOUNT_REDACTED]', text)
    return text
```

---

## 10. Memory Lifecycle — States & Transitions

```
User mentions value
        ↓
    PENDING
        ↓ (agent runs end-of-session confirmation sweep OR user explicitly confirms)
    CONFIRMED
        ↓ (new conflicting value detected in later session)
  CONFLICT DETECTED
        ↓                          ↓
  new value confirmed       old value reconfirmed
  old → RETRACTED           new → RETRACTED
  new → CONFIRMED           old stays CONFIRMED
```

### Soft Delete Rule
NEVER hard delete from SQLite or ChromaDB.

For SQLite: set `status = RETRACTED`, move to `history[]`, set `current = None` or new value.

For ChromaDB: before deleting original chunk, write a retraction record:
```python
collection.add(
    documents=["[RETRACTED] " + original_text],
    metadatas=[{...original_metadata, "status": "retracted", "retracted_in": session_id}]
)
collection.delete(where={"$and": [{"customer_id": cid}, {"chunk_id": chunk_id}]})
```

---

## 11. FastAPI Endpoints

```
POST   /session/start
       body: { customer_id, agent_id }
       returns: { session_id, loaded_memory_summary }

POST   /session/{session_id}/message
       body: { text, language? }
       returns: { response, memory_state, conflicts_detected }

GET    /session/{session_id}/memory
       returns: { fixed_entities, recent_chunks, summaries }
       → used by demo UI to show live memory panel

POST   /session/{session_id}/confirm
       body: { field, value, confirmed: true/false }
       returns: { updated_memory }

POST   /session/{session_id}/retract
       body: { field?, chunk_id?, reason }
       returns: { updated_memory }

POST   /session/{session_id}/end
       returns: { summary, persisted: true }

GET    /customer/{customer_id}/history
       returns: { all_sessions, full_memory_timeline }
```

---

## 12. Hindi + English Support

**Detection per turn:**
```python
from langdetect import detect
lang = detect(user_input)   # "hi" or "en"
```

**Entity extraction prompt adapts by language:**
- If Hindi detected → include Hindi instruction: "Extract entities. Text may be in Hindi or mixed Hindi-English."
- Qwen2.5-3B handles Hinglish (Hindi-English code-switching) reasonably well at Q4

**Embedding:**
`paraphrase-multilingual-MiniLM-L12-v2` embeds Hindi and English into the same vector space — semantic search works across languages without separate indexes.

---

## 13. Demo UI — Streamlit Layout

**Left panel (60%):** Chat interface showing agent ↔ customer conversation.

**Right panel (40%):** Live memory state panel, polled every turn via `/session/{id}/memory`.

Memory panel shows:
- All CONFIRMED fixed entities with timestamp ("Income: ₹60,000 — confirmed S3, last Tuesday")
- PENDING entities highlighted in amber ("Co-applicant: Sunita — PENDING confirmation")
- RETRACTED entries greyed out ("₹45,000 — retracted S4")
- Last 2 session summaries collapsed/expandable
- Conflict alert banner when conflict detected

**The "wow demo moment" sequence:**
1. Session 1: Rajesh says income is ₹45,000 → stored PENDING
2. Session 1 end: agent asks confirmation → CONFIRMED
3. Session 3: Rajesh says income is ₹60,000 → conflict detected
4. Agent says: "You mentioned ₹45,000 in your first call but ₹60,000 last week — which is correct?"
5. Rajesh confirms ₹60,000 → old RETRACTED, new CONFIRMED
6. Memory panel updates live in front of judges

---

## 14. Project Folder Structure

```
ps01-memory-agent/
├── main.py                    # FastAPI app entry point
├── requirements.txt
├── .env                       # ANTHROPIC_API_KEY, OLLAMA_BASE_URL
├── config.py                  # thresholds, model names, constants
│
├── graph/
│   ├── state.py               # SessionState TypedDict
│   ├── nodes.py               # all LangGraph node functions
│   ├── edges.py               # routing logic / conditional edges
│   └── graph.py               # compiled LangGraph graph
│
├── memory/
│   ├── models.py              # all Pydantic models
│   ├── sqlite_store.py        # SQLite read/write helpers
│   ├── vector_store.py        # ChromaDB operations
│   └── retriever.py           # context builder (KV + vector + summaries)
│
├── llm/
│   ├── ollama_client.py       # async Ollama calls
│   ├── claude_client.py       # Anthropic summarization calls
│   ├── entity_extractor.py    # SLM prompt for entity extraction
│   └── prompts.py             # all prompt templates
│
├── api/
│   ├── routes.py              # FastAPI router
│   └── schemas.py             # request/response Pydantic models
│
├── utils/
│   ├── language.py            # langdetect + masking helpers
│   ├── tokenizer.py           # tiktoken token counting
│   └── date_utils.py          # human-readable date helpers ("last Tuesday")
│
├── demo/
│   └── streamlit_app.py       # demo UI
│
├── data/
│   ├── chroma_db/             # ChromaDB persistent storage
│   └── memory.db              # SQLite database
│
└── tests/
    ├── test_memory.py         # unit tests for memory lifecycle
    ├── test_conflicts.py      # conflict detection tests
    └── test_session_flow.py   # end-to-end 3-session Rajesh scenario
```

---

## 15. `requirements.txt`

```txt
langchain
langgraph
langchain-community
fastapi
uvicorn

ollama
anthropic
httpx

chromadb
sentence-transformers

pydantic>=2.0
python-dotenv

langdetect
tiktoken
indic-nlp-library

streamlit
pytest
```

---

## 16. Environment Variables (`.env`)

```
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2
TOKEN_THRESHOLD=2000
CHROMA_PATH=./data/chroma_db
SQLITE_PATH=./data/memory.db
SUMMARIZE_LANGUAGE=en
```

---

## 17. 24-Hour Execution Timeline

### Hours 0–1: Environment Setup
- `ollama pull qwen2.5:3b`
- pip install all dependencies
- test Ollama responds: `ollama run qwen2.5:3b "say hello"`
- create SQLite DB + ChromaDB directory
- confirm sentence-transformers downloads embedding model

### Hours 1–4: Core Models + Storage
- write all Pydantic models (`memory/models.py`)
- write SQLite helpers: `load_customer_memory`, `save_customer_memory`
- write ChromaDB helpers: `add_chunk`, `search_chunks`, `retract_chunk`
- write basic entity extraction prompt + test it manually against Rajesh scenario

### Hours 4–9: LangGraph State Machine
- define `SessionState` TypedDict
- implement nodes: `load_memory`, `extract_entities`, `detect_conflicts`, `update_memory`
- implement routing edges (conflict → ask_user branch)
- implement `retrieve_context` (KV + vector + summaries)
- compile and test graph with a single-turn mock session

### Hours 9–14: Multi-Session Flow
- implement `check_token_threshold` + Claude summarization call
- implement `end_session` node (summary + full persist)
- test 3-session Rajesh scenario manually:
  - S1: income ₹45k, co-applicant Sunita
  - S3: income changes to ₹60k → conflict
  - S4: confirmation sweep, retraction
- verify memory panel shows correct state after each session

### Hours 14–17: FastAPI Layer
- wire all endpoints in `api/routes.py`
- test all endpoints via curl / httpie
- test `/session/{id}/memory` returns correct live state

### Hours 17–20: Hindi Support + Edge Cases
- test Hindi input turns end-to-end
- test Hinglish code-switching (mixed turns)
- test graceful handling of SLM hallucinated JSON (Pydantic catches + retry)
- test retraction flow in ChromaDB

### Hours 20–23: Streamlit Demo UI
- build chat panel (left) + memory state panel (right)
- wire to FastAPI endpoints
- script the demo scenario with hardcoded customer_id "RAJESH_001"
- rehearse the "wow moment" sequence

### Hour 23–24: Final Polish
- write 3-session test in `tests/test_session_flow.py`
- confirm system runs from cold start in <2 minutes
- prepare demo script for judges

---

## 18. Judging Criteria — How We Hit Each One

| Criterion | How we address it |
|-----------|-------------------|
| Memory survives session endings | SQLite + ChromaDB both persist to disk. Cold restart → memory loads immediately. |
| Recall feels conversational | Prompt template instructs SLM to speak naturally, reference dates, never say "according to records". |
| SLM stays within context window | Sliding window summarization at 2000 tokens. Compress + retrieve, never dump full history. |
| Sensitive data never leaves server (bonus) | Regex masking of PAN + amounts before any Claude API call. All inference is local Ollama. |
| Memory survives reconnections across days | Timestamps stored on every entity record. Human-readable date computed at retrieval ("last Tuesday"). |

---

## 19. Questions to Confirm with BrainBack Before Building

1. Is `customer_id` pre-existing (bank account / Aadhaar-linked) or do we handle identity ourselves?
2. Are inputs simulated transcripts or live audio → text? (affects input layer design)
3. How many sessions per customer should the demo simulate — 3 enough?
4. Is the demo format a live conversation or a UI walkthrough with pre-scripted turns?
5. Fixed entity list — home loan only, or must system work across loan types?
6. For sensitive data bonus — does local SQLite with field masking count, or is stronger encryption expected?
7. Will a laptop GPU be available at demo, or should we ensure CPU-only fallback works?
8. Is there a specific test conversation script the judges will run, or is demo free-form?

---

## 20. Key Design Decisions Summary

| Decision | Choice | Reason |
|----------|--------|--------|
| SLM model | Qwen2.5-3B Q4_K_M | Fits 4GB VRAM, tool calling support, Hindi capable |
| Memory structure | Hybrid (fixed schema + dynamic vector) | Fixed = fast recall, dynamic = "recall everything" |
| Conflict strategy | Detect + ask user, soft delete only | Audit trail + natural agent behavior |
| Summarization | Sliding window at 2000 tokens, Claude API | Same pattern Claude uses, low API cost |
| Storage | SQLite + ChromaDB | No server overhead, runs fully offline |
| Orchestration | LangGraph over LangChain agents | Better state control, debuggable, less latency |
| Embedding model | multilingual MiniLM on CPU | Handles Hindi+English in same vector space |
| Demo UI | Streamlit with live memory panel | Shows internal state — differentiates demo |

---

## 21. Clarifications & Runtime Implementation Notes

### A. Async/Await Patterns (CRITICAL)
All LangGraph node functions **MUST be `async`**. 
- Ollama calls via `httpx.AsyncClient`
- ChromaDB operations via async wrapper
- FastAPI endpoints are naturally async

Example node signature:
```python
async def load_memory(state: SessionState) -> dict:
    # fetch from SQLite / ChromaDB
    # NO blocking I/O
    return {"loaded_memory": ...}
```

### B. Conflict Resolution Flow
**Problem**: "ask_user" node needs to block and wait for user input. 

**Solution**: 
1. Client must handle **conflict detection response** from `/session/{id}/message`
2. If `conflicts_detected: true`, return response with choices
3. Client collects user input and POSTs to `/session/{id}/confirm` (new endpoint)
4. Continue session from state snapshot
5. OR: Use message queue + polling if required

**State tracking**: Add `awaiting_confirmation: bool` + `pending_confirmation_id: str` to SessionState

### C. Error Handling Strategy

| Failure | Handling |
|---------|----------|
| Ollama unreachable | Retry 3x with exponential backoff, then fail gracefully with "system unavailable" |
| Pydantic validation fails on SLM JSON | Retry prompt, parse as fallback plain text, log error |
| ChromaDB add/search fails | Log to SQLite error_log table, continue without vector context |
| Sensitive data masking misses PII | Log as security event, fail the turn (safe default) |
| Token count accuracy error | Use Qwen's own tokenizer (`ollama show qwen2.5:3b`) or conservative overestimate |

### D. Token Counting — Use Qwen's Count
Do NOT use tiktoken directly — Qwen's encoding differs from ChatGPT.

**Workaround**:
```python
# Option 1: Ask Ollama during init
ollama run qwen2.5:3b "How many tokens in 'hello world'?" → parse response

# Option 2: Conservative estimate
estimated_tokens = len(text) // 3.5  # Qwen ~3.5 chars per token (conservative)
if estimated_tokens > 1800:  # leave 200 token buffer
    trigger_summarization()
```

### E. Prompt Injection Prevention
Before ANY prompt insertion of user input:
```python
def sanitize_for_prompt(text: str) -> str:
    # Remove any prompt-like patterns
    text = re.sub(r'(system:|assistant:|user:|{|}<|>|```)', '', text)
    text = text.strip()[:500]  # Hard length limit
    return text
```

Apply to: current_turn, extracted entities, any user-provided field

### F. Retraction in SQLite (Detailed)
When retracting an entity in SQLite:
```python
def retract_entity(customer_id: str, field: str, reason: str, session_id: str):
    record = db.load_customer_memory(customer_id)
    if record[field].current:
        # Move current to history, mark as retracted
        record[field].history.append(
            EntityRecord(
                value=record[field].current.value,
                status=MemoryStatus.RETRACTED,
                session_id=record[field].current.session_id,
                retracted_at=datetime.now(),
                retracted_in=session_id,
                retracted_reason=reason
            )
        )
        record[field].current = None
    db.save_customer_memory(record)
```

Same for ChromaDB — write retraction marker before deleting:
```python
collection.add(
    documents=["[RETRACTED] " + original_doc],
    metadatas=[{**metadata, "status": "retracted", "retracted_in": session_id}],
    ids=[original_id + "_retracted"]
)
# Query filters out retracted docs: where={"status": {"$ne": "retracted"}}
```

### G. Session Interruption & Resume
**New endpoint**: `POST /session/{session_id}/resume`

Save on every node completion:
```python
session_checkpoint = {
    "state": state,
    "checkpoint_at": datetime.now(),
    "last_node": current_node_name
}
redis.set(f"session:{session_id}:checkpoint", json.dumps(session_checkpoint))
```

On resume: Load checkpoint state and continue from last node + 1

### H. Language Detection Robustness
```python
def detect_language(text: str) -> str:
    try:
        # If confidence < 0.7, assume mixed input
        lang = detect(text)
        confidence = detect_langs(text)[0].prob
        if confidence < 0.7:
            return "mixed"  # Handle both Hindi + English
        return lang
    except:
        return "unknown"

# In entity extraction prompt:
if language in ["hi", "mixed"]:
    prompt += "Input may contain Hindi, English, or Hinglish (code-switching). Preserve exact spellings."
```

### I. Test Fixtures — Rajesh 3-Session Scenario
**Create conftest.py with:**
```python
RAJESH_SCENARIO = {
    "customer_id": "RAJESH_001",
    "sessions": [
        {
            "session_id": "S1",
            "turns": [
                {"role": "user", "text": "मेरी सालाना आय ₹45,000 है"},
                {"role": "assistant", "text": "Got it, annual income ₹45,000..."},
                {"role": "user", "text": "हाँ, और मेरी पत्नी सुनीता को co-applicant बनाएं"}
            ],
            "expected_memory": {
                "income": {"value": "45000", "status": "PENDING"},
                "co_applicant": {"value": "Sunita", "status": "PENDING"}
            }
        },
        # ... S3, S4 variations
    ]
}
```

Run as pytest parametrized test:
```python
@pytest.mark.parametrize("session", RAJESH_SCENARIO["sessions"])
def test_session_flow(session):
    # Execute, verify memory updates
```

---

## 22. Updated Folder Structure with Error Handling + Config

```
ps01-memory-agent/
├── main.py
├── config.py                  # .env loader, constants, thresholds
├── conftest.py                # pytest fixtures + RAJESH_SCENARIO
│
├── graph/
│   ├── state.py               # SessionState TypedDict
│   ├── nodes.py               # ALL async node functions
│   ├── edges.py               # routing + conditional edges
│   └── graph.py               # compiled graph + error handlers
│
├── memory/
│   ├── models.py              # Pydantic models + MemoryStatus enum
│   ├── sqlite_store.py        # sync SQLite helpers
│   ├── vector_store.py        # ChromaDB async wrapper
│   ├── retriever.py           # context builder (3-part retrieval)
│   └── errors.py              # custom exceptions (MemoryStoreError, etc)
│
├── llm/
│   ├── ollama_client.py       # AsyncOllamaClient + retry logic
│   ├── claude_client.py       # Anthropic async wrapper + masking
│   ├── entity_extractor.py    # SLM prompt building
│   ├── prompts.py             # all templates (system, extraction, etc)
│   └── errors.py              # LLMError, TokenLimitExceeded
│
├── api/
│   ├── routes.py              # FastAPI router (all endpoints)
│   ├── schemas.py             # request/response Pydantic models
│   └── middleware.py          # error handling, logging middleware
│
├── utils/
│   ├── language.py            # detect_language, sanitize_for_prompt
│   ├── tokenizer.py           # qwen_token_count + conservative estimate
│   ├── date_utils.py          # human_readable_date helpers
│   └── security.py            # sensitive data masking, PII detection
│
├── demo/
│   └── streamlit_app.py       # Streamlit UI
│
├── data/
│   ├── chroma_db/             # ChromaDB persistence
│   └── memory.db              # SQLite DB
│
├── tests/
│   ├── test_memory_models.py  # Pydantic model tests
│   ├── test_sqlite_store.py   # SQLite CRUD + retraction
│   ├── test_vector_store.py   # ChromaDB operations
│   ├── test_entities.py       # extraction prompt variations
│   ├── test_session_flow.py   # 3-session Rajesh scenario
│   ├── test_error_handling.py # Ollama down, ChromaDB fail, etc
│   └── conftest.py            # fixtures + RAJESH_SCENARIO
│
├── .env                       # (add QWEN_TOKENIZER_MODEL)
├── .env.example
├── requirements.txt           # pinned versions + test deps
├── pytest.ini                 # test config
└── README.md                  # updated setup instructions
```

---

## 23. Questions for User Before Full Implementation

1. **Blocking on conflicts** — Should we implement message queue/polling or callback-based confirmation?
2. **Checkpoint storage** — Use Redis for session snapshots, or keep in-memory during demo?
3. **Security level** — Is field-level masking + regex PII detection sufficient, or encrypt SQLite?
4. **Fixed schema flexibility** — Should system support multiple loan types (home/auto/personal) or home-loan-only?
5. **Recording consent** — Do we log all turns end-to-end or only confirmed facts? (affects data volume)
