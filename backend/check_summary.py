"""
Inspector: checks all sessions for LLM-generated summaries.
Explicitly distinguishes real LLM output from the fallback template string.

Run from d:/LoanAgent/backend/:
    uv run python check_summary.py
"""
import sys, json, sqlite3, re
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, ".")
from config import SQLITE_PATH, SESSION_CONTEXT_WINDOW, TOKEN_THRESHOLD_PERCENT

THRESHOLD = int(SESSION_CONTEXT_WINDOW * TOKEN_THRESHOLD_PERCENT)

# Fallback template written when Ollama fails (core_nodes.py line ~94)
# Pattern: "[N earlier messages summarized]"
FALLBACK_PATTERN = re.compile(r"^\[\d+ earlier messages summarized\]$")

def classify_summary(text: str) -> tuple[str, str]:
    """
    Returns (label, detail) where label is one of:
      LLM-GENERATED  - real LLM output (what we want)
      FALLBACK        - Ollama failed; this is just a template string
    """
    if FALLBACK_PATTERN.match(text.strip()):
        return "FALLBACK", "Ollama failed during compression — this is NOT an LLM summary"
    return "LLM-GENERATED", "Real LLM output stored correctly"


print(f"\n{'=' * 65}")
print(f"  LoanAgent Session Summary Inspector")
print(f"  DB           : {SQLITE_PATH}")
print(f"  Context win  : {SESSION_CONTEXT_WINDOW} tokens")
print(f"  Threshold    : {THRESHOLD} tokens ({TOKEN_THRESHOLD_PERCENT*100:.0f}% of window)")
print(f"{'=' * 65}\n")

con = sqlite3.connect(SQLITE_PATH)
con.row_factory = sqlite3.Row
cur = con.cursor()

# Check summary column exists
cur.execute("PRAGMA table_info(user_sessions)")
cols = [r["name"] for r in cur.fetchall()]
if "summary" not in cols:
    print("[FAIL] 'summary' column NOT found in user_sessions.")
    print("       Restart the backend once to apply the migration.")
    sys.exit(1)

print("[OK] 'summary' column present\n")

# Fetch recent sessions with JOIN to get username
cur.execute("""
    SELECT s.session_id, s.is_active, s.last_activity,
           s.summary, s.messages,
           u.username, u.email
    FROM user_sessions s
    LEFT JOIN users u ON s.user_id = u.user_id
    ORDER BY s.last_activity DESC
    LIMIT 10
""")
rows = cur.fetchall()
con.close()

if not rows:
    print("No sessions found — start a chat first.\n")
    sys.exit(0)

llm_count      = 0
fallback_count = 0
no_summary     = 0

for i, row in enumerate(rows, 1):
    data    = dict(row)
    sid     = data["session_id"]
    active  = "ACTIVE" if data["is_active"] else "inactive"
    last    = data["last_activity"] or "unknown"
    summary = data["summary"]
    user    = data.get("username") or "unknown"
    email   = data.get("email") or ""

    try:
        msgs      = json.loads(data["messages"] or "[]")
        msg_count = len(msgs)
        # Count approx tokens
        approx_tokens = sum(len(m.get("content","")) for m in msgs) // 4
    except Exception:
        msg_count     = "?"
        approx_tokens = "?"

    print(f"[{i}] Session  : {sid[:24]}...")
    print(f"     User     : {user} ({email})")
    print(f"     Status   : {active}  |  Last active: {last}")
    print(f"     Messages : {msg_count} in DB  (~{approx_tokens} tokens)")

    if summary:
        label, detail = classify_summary(summary)
        if label == "LLM-GENERATED":
            print(f"     Summary  : [LLM-GENERATED] -- real LLM output confirmed")
            print(f"     Text     : {summary[:300]}{'...' if len(summary) > 300 else ''}")
            llm_count += 1
        else:
            print(f"     Summary  : [FALLBACK] -- Ollama FAILED during compression")
            print(f"     Text     : {summary}")
            print(f"     Action   : Check that Ollama is running; next compression will retry")
            fallback_count += 1
    else:
        status = f"[NOT YET] -- {THRESHOLD - approx_tokens} more tokens needed" if isinstance(approx_tokens, int) else "[NOT YET]"
        print(f"     Summary  : {status}")
        no_summary += 1

    print(f"     {'-' * 58}")

print(f"\nSummary Report:")
print(f"  LLM-generated summaries : {llm_count}")
print(f"  Fallback (Ollama failed) : {fallback_count}")
print(f"  No summary yet          : {no_summary}")
if llm_count > 0:
    print(f"\n  RESULT: LLM summary generation is working correctly.")
elif fallback_count > 0:
    print(f"\n  RESULT: Summaries exist but Ollama failed — check Ollama service.")
else:
    print(f"\n  RESULT: No summaries yet. Chat more messages to hit the {THRESHOLD}-token threshold.")
