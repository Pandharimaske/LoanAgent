import React, { useState, useRef, useEffect } from "react";
import { LogOut, Send, ShieldCheck, Loader2, Bot, User, Zap, Sparkles, ArrowLeft, CheckCircle, XCircle, Edit3, Save } from "lucide-react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

const BASE_URL = import.meta.env.VITE_BASE_URL || "http://localhost:8000";

const dummyChat = [
  { id: 1, role: "agent", text: "Welcome to BrainBack Secure Banking. How can I help you today?", response_type: "options", options: ["📋 Check loan eligibility", "💰 View loan options", "📁 Update my profile", "❓ Ask a question"], options_consumed: false },
];

export default function DashboardPage() {
  const navigate = useNavigate();
  const [chat, setChat] = useState(dummyChat);
  const [input, setInput] = useState("");
  const [userData, setUserData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [langMode, setLangMode] = useState("auto"); 
  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const messageIdRef = useRef(2);

  useEffect(() => {
    const fetchUserData = async () => {
      const sessionId = localStorage.getItem("sessionId");
      const token = localStorage.getItem("token");
      if (!sessionId || !token) { navigate("/login"); return; }
      try {
        const response = await axios.get(`${BASE_URL}/auth/session/${sessionId}`, { headers: { Authorization: `Bearer ${token}` } });
        if (response.data.is_active) {
          setUserData({ email: response.data.email, user_id: response.data.user_id, customer_id: response.data.customer_id || "Not assigned", session_id: response.data.session_id, session_expires: response.data.expires_at });
        } else { throw new Error("Session expired"); }
      } catch (err) {
        console.error("Session validation failed", err);
        ["token","sessionId","userId","user_id","customer_id"].forEach(k => localStorage.removeItem(k));
        navigate("/login");
      } finally { setLoading(false); }
    };
    fetchUserData();
  }, [navigate]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chat]);

  const handleLogout = () => {
    ["token","sessionId","userId","user_id","customer_id"].forEach(k => localStorage.removeItem(k));
    navigate("/login");
  };

  const handleSend = async (text) => {
    const msgText = (text || input).trim();
    if (!msgText || sending) return;

    setInput("");
    setError("");
    const userMessageId = messageIdRef.current++;
    setChat(prev => [...prev, { id: userMessageId, role: "user", text: msgText }]);
    setSending(true);

    try {
      const sessionId = localStorage.getItem("sessionId");
      const response = await axios.post(`${BASE_URL}/session/message`, {
        session_id: sessionId || "demo_session",
        user_input: msgText,
        language: langMode,
      });

      const data = response.data;
      const agentText = data.agent_response || "I couldn't process that. Please try again.";
      const responseType = data.response_type || "text";
      const options = data.response_options || [];
      const pendingFields = data.pending_fields || null;

      console.log("[Chat] response_type:", responseType, "| pending_fields:", pendingFields);

      // Store pending_fields in session storage for /confirm-save call
      if (pendingFields && Object.keys(pendingFields).length > 0) {
        sessionStorage.setItem("pending_fields", JSON.stringify(pendingFields));
      }

      const agentMessageId = messageIdRef.current++;
    
      setChat(prev => [
        ...prev.map(m => m.role === "agent" && m.options ? { ...m, options_consumed: true } : m),
        {
          id: agentMessageId,
          role: "agent",
          text: agentText,
          response_type: responseType,
          options: options,
          options_consumed: false,
          pending_fields: pendingFields,
        }
      ]);

      if (data.error) setError(data.error);
    } catch (err) {
      const errorText = err.response?.data?.detail || "Connection error. Please try again.";
      setChat(prev => [...prev, { id: messageIdRef.current++, role: "agent", text: "⚠️ " + errorText, options_consumed: true }]);
      setError(errorText);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleConfirmSave = async (approved, editedFields = null) => {
    const sessionId = localStorage.getItem("sessionId");
    // customer_id may be stored separately; fall back to userData
    const customerId =
      localStorage.getItem("customer_id") ||
      userData?.customer_id ||
      sessionId; // last-resort: backend will derive it from the session

    // Optimistic UI — mark last save_confirmation message as resolved
    setChat(prev => prev.map(m => m.response_type === "save_confirmation" ? { ...m, response_type: "resolved" } : m));

    try {
      const payload = { customer_id: customerId, session_id: sessionId, approved };
      if (editedFields) payload.edited_fields = editedFields;

      const res = await axios.post(`${BASE_URL}/chat/confirm-save`, payload);
      const confirmMsg = res.data.response || (approved ? "Details saved!" : "No problem, details not saved.");

      setChat(prev => [...prev, { id: messageIdRef.current++, role: "agent", text: confirmMsg, response_type: "text", options: ["💰 Check loan eligibility", "📋 View my profile", "❓ Ask another question"] }]);
      sessionStorage.removeItem("pending_fields");
    } catch (err) {
      console.error("confirm-save error:", err.response?.data || err.message);
      setChat(prev => [...prev, { id: messageIdRef.current++, role: "agent", text: "⚠️ Failed to save details. Please try again.", response_type: "text" }]);
    }
  };

  /* ─── Loading Screen ─── */
  if (loading) {
    return (
      <div style={styles.loadingWrap}>
        <div style={styles.loadingInner}>
          <div style={styles.loadingIcon}><ShieldCheck size={34} color="#fff" /></div>
          <p style={styles.loadingTitle}>Authenticating Session</p>
          <p style={styles.loadingSubtitle}>Verifying your secure connection…</p>
          <div style={styles.dotsRow}>{[0,1,2].map(i => <div key={i} className="typing-dot" style={styles.dot} />)}</div>
        </div>
      </div>
    );
  }

  const isFirstLoad = chat.length === 1;

  /* ─── Dashboard ─── */
  return (
    <div style={styles.root}>
      <div style={styles.bgGrid} />
      <div style={{ ...styles.bgOrb, top: "-180px", left: "-180px", width: "550px", height: "550px", background: "radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 70%)", animationDuration: "9s" }} />
      <div style={{ ...styles.bgOrb, bottom: "-150px", right: "-100px", width: "450px", height: "450px", background: "radial-gradient(circle, rgba(139,92,246,0.09) 0%, transparent 70%)", animationDuration: "13s", animationDirection: "reverse" }} />

      {/* ── Navbar ── */}
      <nav style={styles.nav}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <button onClick={() => navigate("/")} style={styles.backBtn} onMouseEnter={e => Object.assign(e.currentTarget.style, styles.backBtnHover)} onMouseLeave={e => Object.assign(e.currentTarget.style, styles.backBtnBase)} title="Back to Home">
            <ArrowLeft size={18} />
          </button>
          <div style={styles.brand}>
            <div style={styles.brandIcon}><ShieldCheck size={22} color="#fff" /></div>
            <div><span style={styles.brandName}>BrainBack.AI</span></div>
          </div>
        </div>

        {userData && (
          <div style={styles.navCenter}>
            <Sparkles size={13} color="#f59e0b" />
            <span style={styles.greeting}>{userData.email}</span>
          </div>
        )}

        <div style={styles.navRight}>
          <div className="pulse-badge" style={styles.activeBadge}>
            <div style={styles.activeDot} />
            <span style={styles.activeTxt}>Session Active</span>
          </div>
          <button id="logout-btn" onClick={handleLogout} style={styles.logoutBtn} onMouseEnter={e => Object.assign(e.currentTarget.style, styles.logoutBtnHover)} onMouseLeave={e => Object.assign(e.currentTarget.style, styles.logoutBtnBase)}>
            <LogOut size={15} />Logout
          </button>
        </div>
      </nav>

      {/* ── Chat Container ── */}
      <div style={styles.chatWrap}>
        <div style={styles.chatCard}>
          {/* Chat header */}
          <div style={styles.chatHeader}>
            <div style={styles.agentAvatar}><Bot size={22} color="#fff" /></div>
            <div>
              <p style={styles.agentName}>Loan Agent AI</p>
              <p style={styles.agentStatus}><span style={styles.statusDot} />Online · Powered by BrainBack Intelligence</p>
            </div>
            <div style={styles.msgCount}><Zap size={13} color="#f59e0b" /><span style={styles.msgCountTxt}>{chat.length} messages</span></div>

            {/* ── Language Toggle ── */}
            <div style={langToggleStyles.wrap}>
              {[["auto", "AUTO"], ["en", "EN"], ["hi", "हिं"]].map(([val, label]) => (
                <button
                  key={val}
                  onClick={() => setLangMode(val)}
                  style={{
                    ...langToggleStyles.btn,
                    ...(langMode === val ? langToggleStyles.active : langToggleStyles.inactive),
                  }}
                  title={val === "auto" ? "Auto-detect language" : val === "en" ? "English" : "Hindi / Hinglish"}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {/* Messages area */}
          <div style={styles.messagesArea}>
            {error && <div style={styles.errorBanner}>⚠ {error}</div>}

            {isFirstLoad && (
              <div style={styles.heroWrap}>
                <div style={styles.heroGlow} />
                <div style={styles.heroIcon}><ShieldCheck size={26} color="#fff" /></div>
                <h2 style={styles.heroTitle}>{
                  langMode === "hi"
                    ? "आज मैं आपकी कैसे मदद कर सकता हूँ?"
                    : langMode === "en"
                    ? "How can I help you today?"
                    : "How can I help you? / Main aapki kaise help kar sakta hun?"
                }</h2>
                <p style={styles.heroSubtitle}>{
                  langMode === "hi"
                    ? "लोन, पात्रता, दरें या अपने खाते के बारे में कुछ भी पूछें।"
                    : langMode === "en"
                    ? "Ask me anything about loans, eligibility, rates, or your account."
                    : "Loan, eligibility, rates ke baare mein kuch bhi poochhein."
                }</p>
              </div>
            )}

            {/* Messages */}
            {chat.map((msg, idx) => {
              const isLastAgentMsg =
                msg.role === "agent" &&
                [...chat].reverse().findIndex(m => m.role === "agent") ===
                  chat.length - 1 - idx;

              return (
              <div key={msg.id}>
                {/* Message bubble */}
                <div style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start", alignItems: "flex-end", gap: "10px", marginBottom: "4px" }}>
                  {msg.role === "agent" && <div style={styles.agentBubbleAvatar}><Bot size={16} color="#fff" /></div>}
                  <div style={{
                    maxWidth: "68%", padding: "13px 18px", fontSize: "14px", lineHeight: "1.65",
                    whiteSpace: "pre-line", wordBreak: "break-word",
                    borderRadius: msg.role === "user" ? "20px 20px 4px 20px" : "20px 20px 20px 4px",
                    ...(msg.role === "user"
                      ? { background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)", color: "#fff", boxShadow: "0 6px 24px rgba(59,130,246,0.35)" }
                      : { background: "rgba(255,255,255,0.06)", color: "#e2e8f0", border: "1px solid rgba(255,255,255,0.09)", boxShadow: "0 2px 12px rgba(0,0,0,0.25)" }),
                  }}>
                    {msg.text}
                  </div>
                  {msg.role === "user" && <div style={styles.userBubbleAvatar}><User size={16} color="#fff" /></div>}
                </div>

                {/* Save Confirmation Card — only on last agent message with pending_fields */}
                {isLastAgentMsg && msg.response_type === "save_confirmation" && msg.pending_fields && (
                  <SaveConfirmationCard
                    pendingFields={msg.pending_fields}
                    onConfirm={handleConfirmSave}
                  />
                )}

                {/* Mismatch Card — only on last agent message */}
                {isLastAgentMsg && msg.response_type === "mismatch_confirmation" && (
                  <MismatchCard onConfirm={(useNew) => {
                    handleSend(useNew ? "✅ Yes, use the new value" : "❌ No, keep my old value");
                    setChat(prev => prev.map(m => m.id === msg.id ? { ...m, response_type: "resolved" } : m));
                  }} />
                )}

                {/* Quick Reply Chips — ONLY on the last agent message, and only if not consumed */}
                {isLastAgentMsg &&
                  !msg.options_consumed &&
                  (msg.response_type === "text" || msg.response_type === "options") &&
                  msg.options && msg.options.length > 0 && (
                  <QuickReplyChips
                    options={msg.options}
                    onSelect={(opt) => {
                      // Mark this message's chips as consumed before sending
                      setChat(prev => prev.map(m => m.id === msg.id ? { ...m, options_consumed: true } : m));
                      handleSend(opt);
                    }}
                  />
                )}
              </div>
            );
            })}

            {/* Typing indicator */}
            {sending && (
              <div style={{ display: "flex", alignItems: "flex-end", gap: "10px", marginBottom: "4px" }}>
                <div style={styles.agentBubbleAvatar}><Bot size={16} color="#fff" /></div>
                <div style={styles.typingBubble}>{[0,1,2].map(i => <div key={i} className="typing-dot" style={styles.typingDot} />)}</div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* ── Input bar ── */}
          <div style={styles.inputArea}>
            <div style={styles.inputRow} onFocusCapture={e => Object.assign(e.currentTarget.style, styles.inputRowFocused)} onBlurCapture={e => Object.assign(e.currentTarget.style, styles.inputRowBase)}>
              <input ref={inputRef} id="chat-input" type="text"
                placeholder={sending
                  ? (langMode === "hi" ? "एजेंट सोच रहा है…" : langMode === "en" ? "Agent is thinking…" : "Agent soch raha hai…")
                  : (langMode === "hi" ? "अपना सवाल यहाँ लिखें…" : langMode === "en" ? "Type a message or ask a question…" : "Type karo ya Hindi mein poochho…")
                }
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !sending && handleSend()}
                disabled={sending}
                style={styles.inputField}
              />
              <button id="send-btn" onClick={() => handleSend()} disabled={sending || !input.trim()}
                style={{ ...styles.sendBtn, background: sending || !input.trim() ? "rgba(255,255,255,0.06)" : "linear-gradient(135deg, #3b82f6, #06b6d4)", boxShadow: sending || !input.trim() ? "none" : "0 0 20px rgba(59,130,246,0.5)", cursor: sending || !input.trim() ? "not-allowed" : "pointer", opacity: sending ? 0.55 : 1 }}
                onMouseEnter={e => { if (!sending && input.trim()) e.currentTarget.style.transform = "scale(1.08)"; }}
                onMouseLeave={e => { e.currentTarget.style.transform = "scale(1)"; }}>
                {sending ? <Loader2 size={20} color="#94a3b8" style={{ animation: "spin 0.7s linear infinite" }} /> : <Send size={20} color="#fff" />}
              </button>
            </div>
            <p style={styles.inputHint}>Press <kbd style={styles.kbd}>Enter</kbd> to send
              {langMode === "auto" && " · Auto-detecting language"}
              {langMode === "hi" && " · Hindi / Hinglish mode"}
              {langMode === "en" && " · English mode"}
            </p>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes orbFloat { 0%, 100% { transform: translate(0,0) scale(1); } 33% { transform: translate(20px,-30px) scale(1.04); } 66% { transform: translate(-10px,18px) scale(0.97); } }
        @keyframes heroGlow { 0%, 100% { opacity: 0.5; transform: scale(1); } 50% { opacity: 0.8; transform: scale(1.15); } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fadeIn  { from { opacity: 0; } to { opacity: 1; } }
      `}</style>
    </div>
  );
}

/* ─────────────────────────────────────────────
   COMPONENT: QuickReplyChips
   Renders clickable pill buttons after an agent message
───────────────────────────────────────────── */
function QuickReplyChips({ options, onSelect }) {
  const [used, setUsed] = useState(false);
  if (used || !options || options.length === 0) return null;
  return (
    <div style={chipStyles.wrap}>
      {options.map((opt, i) => (
        <button key={i} onClick={() => { setUsed(true); onSelect(opt); }}
          style={chipStyles.chip}
          onMouseEnter={e => Object.assign(e.currentTarget.style, chipStyles.chipHover)}
          onMouseLeave={e => Object.assign(e.currentTarget.style, chipStyles.chipBase)}>
          {opt}
        </button>
      ))}
    </div>
  );
}
const chipStyles = {
  wrap: { display: "flex", flexWrap: "wrap", gap: "8px", marginLeft: "42px", marginTop: "6px", animation: "slideUp 0.3s ease" },
  chip: { padding: "7px 16px", borderRadius: "20px", background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.2)", color: "#93c5fd", fontSize: "13px", fontWeight: 500, cursor: "pointer", fontFamily: "'Inter', sans-serif", transition: "all 0.2s" },
  chipBase: { background: "rgba(59,130,246,0.08)", borderColor: "rgba(59,130,246,0.2)", color: "#93c5fd", transform: "none", boxShadow: "none" },
  chipHover: { background: "rgba(59,130,246,0.18)", borderColor: "rgba(59,130,246,0.5)", color: "#eff6ff", transform: "translateY(-1px)", boxShadow: "0 4px 16px rgba(59,130,246,0.2)" },
};

/* ─────────────────────────────────────────────
   COMPONENT: SaveConfirmationCard
   Shows extracted financial fields + Save/Edit/Skip buttons
───────────────────────────────────────────── */
function SaveConfirmationCard({ pendingFields, onConfirm }) {
  const [mode, setMode] = useState("confirm"); // "confirm" | "edit" | "done"
  const [editedValues, setEditedValues] = useState({ ...pendingFields });

  const fieldLabels = {
    monthly_income: "Monthly Income", annual_income: "Annual Income", net_monthly_income: "Net Monthly Income",
    cibil_score: "CIBIL Score", requested_loan_amount: "Requested Loan Amount", requested_loan_type: "Loan Type",
    requested_loan_tenure: "Loan Tenure (months)", existing_loan_amount: "Existing Loan Amount",
    total_existing_emi_monthly: "Total Monthly EMI", number_of_active_loans: "Active Loans", coapplicant_income: "Co-applicant Income",
  };

  if (mode === "done") return null;

  return (
    <div style={scStyles.card}>
      <div style={scStyles.header}>
        <div style={scStyles.headerIcon}>💾</div>
        <div>
          <p style={scStyles.headerTitle}>Save to Profile?</p>
          <p style={scStyles.headerSub}>I noted these financial details — confirm to save.</p>
        </div>
      </div>

      <div style={scStyles.fieldList}>
        {Object.entries(pendingFields).map(([field, value]) => (
          <div key={field} style={scStyles.fieldRow}>
            <span style={scStyles.fieldLabel}>{fieldLabels[field] || field.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</span>
            {mode === "edit"
              ? <input value={editedValues[field] ?? value} onChange={e => setEditedValues(prev => ({ ...prev, [field]: e.target.value }))}
                  style={scStyles.editInput} />
              : <span style={scStyles.fieldValue}>{String(value)}</span>
            }
          </div>
        ))}
      </div>

      <div style={scStyles.actions}>
        {mode === "confirm" ? (
          <>
            <button style={{ ...scStyles.btn, ...scStyles.btnSave }} onClick={() => { setMode("done"); onConfirm(true); }}>
              <CheckCircle size={15} /> Save
            </button>
            <button style={{ ...scStyles.btn, ...scStyles.btnEdit }} onClick={() => setMode("edit")}>
              <Edit3 size={15} /> Edit
            </button>
            <button style={{ ...scStyles.btn, ...scStyles.btnSkip }} onClick={() => { setMode("done"); onConfirm(false); }}>
              <XCircle size={15} /> Don't Save
            </button>
          </>
        ) : (
          <>
            <button style={{ ...scStyles.btn, ...scStyles.btnSave }} onClick={() => { setMode("done"); onConfirm(true, editedValues); }}>
              <Save size={15} /> Confirm & Save
            </button>
            <button style={{ ...scStyles.btn, ...scStyles.btnSkip }} onClick={() => setMode("confirm")}>
              Cancel
            </button>
          </>
        )}
      </div>
    </div>
  );
}
const scStyles = {
  card: { marginLeft: "42px", marginTop: "10px", background: "rgba(59,130,246,0.07)", border: "1px solid rgba(59,130,246,0.2)", borderRadius: "16px", padding: "16px 20px", animation: "slideUp 0.35s ease", maxWidth: "420px" },
  header: { display: "flex", alignItems: "center", gap: "12px", marginBottom: "14px" },
  headerIcon: { fontSize: "22px" },
  headerTitle: { margin: 0, fontWeight: 700, fontSize: "14px", color: "#e2e8f0" },
  headerSub: { margin: 0, fontSize: "12px", color: "#64748b" },
  fieldList: { display: "flex", flexDirection: "column", gap: "8px", marginBottom: "14px" },
  fieldRow: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 12px", background: "rgba(255,255,255,0.04)", borderRadius: "8px", gap: "12px" },
  fieldLabel: { fontSize: "12px", color: "#94a3b8", fontWeight: 500 },
  fieldValue: { fontSize: "13px", color: "#f0f4ff", fontWeight: 600 },
  editInput: { fontSize: "13px", color: "#f0f4ff", fontWeight: 600, background: "rgba(255,255,255,0.07)", border: "1px solid rgba(59,130,246,0.35)", borderRadius: "6px", padding: "4px 8px", outline: "none", width: "140px", fontFamily: "'Inter', sans-serif" },
  actions: { display: "flex", gap: "8px", flexWrap: "wrap" },
  btn: { display: "flex", alignItems: "center", gap: "6px", padding: "8px 16px", borderRadius: "10px", fontSize: "13px", fontWeight: 600, cursor: "pointer", fontFamily: "'Inter', sans-serif", border: "none", transition: "all 0.2s" },
  btnSave: { background: "rgba(16,185,129,0.15)", color: "#10b981", border: "1px solid rgba(16,185,129,0.3)" },
  btnEdit: { background: "rgba(245,158,11,0.12)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.3)" },
  btnSkip: { background: "rgba(239,68,68,0.1)", color: "#f87171", border: "1px solid rgba(239,68,68,0.22)" },
};

/* ─────────────────────────────────────────────
   COMPONENT: MismatchCard
   Shown when a conflict is detected — let user choose
───────────────────────────────────────────── */
function MismatchCard({ onConfirm }) {
  const [done, setDone] = useState(false);
  if (done) return null;
  return (
    <div style={mmStyles.card}>
      <div style={mmStyles.actions}>
        <button style={{ ...scStyles.btn, ...scStyles.btnSave }} onClick={() => { setDone(true); onConfirm(true); }}>
          <CheckCircle size={15} /> Yes, use new value
        </button>
        <button style={{ ...scStyles.btn, ...scStyles.btnSkip }} onClick={() => { setDone(true); onConfirm(false); }}>
          <XCircle size={15} /> Keep old value
        </button>
      </div>
    </div>
  );
}
const mmStyles = {
  card: { marginLeft: "42px", marginTop: "8px", animation: "fadeIn 0.3s ease" },
  actions: { display: "flex", gap: "8px" },
};

/* ─── Style objects ─── */
const styles = {
  root: { minHeight: "100vh", display: "flex", flexDirection: "column", background: "linear-gradient(135deg, #060b14 0%, #0a0f1e 50%, #0d1427 100%)", fontFamily: "'Inter', sans-serif", color: "#f0f4ff", position: "relative", overflow: "hidden" },
  bgGrid: { position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none", backgroundImage: "linear-gradient(rgba(59,130,246,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(59,130,246,0.035) 1px, transparent 1px)", backgroundSize: "64px 64px" },
  bgOrb: { position: "fixed", borderRadius: "50%", filter: "blur(60px)", zIndex: 0, pointerEvents: "none", animation: "orbFloat var(--dur,10s) ease-in-out infinite" },
  loadingWrap: { minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "linear-gradient(135deg, #060b14 0%, #0a0f1e 60%, #0d1427 100%)", fontFamily: "'Inter', sans-serif", position: "relative", overflow: "hidden" },
  loadingInner: { position: "relative", zIndex: 1, textAlign: "center" },
  loadingIcon: { width: "72px", height: "72px", borderRadius: "22px", margin: "0 auto 20px", background: "linear-gradient(135deg, #3b82f6, #06b6d4)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 60px rgba(59,130,246,0.55)" },
  loadingTitle: { color: "#f0f4ff", fontSize: "20px", fontWeight: 700, margin: "0 0 8px" },
  loadingSubtitle: { color: "#475569", fontSize: "14px", margin: "0 0 24px" },
  dotsRow: { display: "flex", gap: "8px", justifyContent: "center" },
  dot: { width: "8px", height: "8px", borderRadius: "50%", background: "#3b82f6" },
  nav: { position: "relative", zIndex: 10, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 28px", height: "64px", background: "rgba(6,11,20,0.88)", backdropFilter: "blur(24px)", borderBottom: "1px solid rgba(255,255,255,0.06)", boxShadow: "0 1px 32px rgba(0,0,0,0.5)", flexShrink: 0 },
  brand: { display: "flex", alignItems: "center", gap: "12px" },
  brandIcon: { width: "40px", height: "40px", borderRadius: "12px", background: "linear-gradient(135deg, #3b82f6, #06b6d4)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 20px rgba(59,130,246,0.45)" },
  brandName: { fontWeight: 800, fontSize: "19px", letterSpacing: "-0.02em", color: "#f0f4ff" },
  navCenter: { display: "flex", alignItems: "center", gap: "6px", padding: "6px 14px", borderRadius: "20px", background: "rgba(245,158,11,0.08)", border: "1px solid rgba(245,158,11,0.18)" },
  greeting: { color: "#94a3b8", fontSize: "13px", fontWeight: 500 },
  navRight: { display: "flex", alignItems: "center", gap: "14px" },
  activeBadge: { display: "flex", alignItems: "center", gap: "7px", padding: "6px 14px", borderRadius: "20px", background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.25)" },
  activeDot: { width: "7px", height: "7px", borderRadius: "50%", background: "#10b981" },
  activeTxt: { color: "#10b981", fontSize: "12px", fontWeight: 600 },
  backBtn: { display: "flex", alignItems: "center", justifyContent: "center", width: "36px", height: "36px", borderRadius: "10px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", color: "#fff", cursor: "pointer", transition: "all 0.2s" },
  backBtnBase: { background: "rgba(255,255,255,0.06)", borderColor: "rgba(255,255,255,0.1)" },
  backBtnHover: { background: "rgba(255,255,255,0.12)", borderColor: "rgba(255,255,255,0.25)", transform: "scale(1.05)" },
  logoutBtn: { display: "flex", alignItems: "center", gap: "7px", padding: "8px 18px", borderRadius: "10px", border: "1px solid rgba(239,68,68,0.22)", background: "rgba(239,68,68,0.1)", color: "#f87171", fontSize: "13px", fontWeight: 600, cursor: "pointer", fontFamily: "'Inter', sans-serif", transition: "all 0.2s" },
  logoutBtnBase: { background: "rgba(239,68,68,0.1)", borderColor: "rgba(239,68,68,0.22)" },
  logoutBtnHover: { background: "rgba(239,68,68,0.18)", borderColor: "rgba(239,68,68,0.45)" },
  chatWrap: { position: "relative", zIndex: 1, flex: 1, display: "flex", alignItems: "stretch", maxWidth: "900px", width: "100%", margin: "16px auto", padding: "0 24px 16px", boxSizing: "border-box", minHeight: 0, overflow: "hidden" },
  chatCard: { flex: 1, display: "flex", flexDirection: "column", background: "rgba(255,255,255,0.035)", backdropFilter: "blur(24px)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "24px", overflow: "hidden", boxShadow: "0 20px 80px rgba(0,0,0,0.55), 0 0 0 1px rgba(59,130,246,0.05)" },
  chatHeader: { padding: "18px 28px", borderBottom: "1px solid rgba(255,255,255,0.07)", background: "rgba(255,255,255,0.025)", display: "flex", alignItems: "center", gap: "14px", flexShrink: 0 },
  agentAvatar: { width: "44px", height: "44px", borderRadius: "14px", flexShrink: 0, background: "linear-gradient(135deg, #8b5cf6, #3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 6px 20px rgba(139,92,246,0.35)" },
  agentName: { margin: 0, fontWeight: 700, fontSize: "15px", color: "#f0f4ff" },
  agentStatus: { margin: 0, fontSize: "12px", color: "#10b981", display: "flex", alignItems: "center", gap: "5px" },
  statusDot: { display: "inline-block", width: "6px", height: "6px", borderRadius: "50%", background: "#10b981" },
  msgCount: { marginLeft: "auto", display: "flex", alignItems: "center", gap: "6px" },
  msgCountTxt: { color: "#475569", fontSize: "12px" },
  messagesArea: { flex: 1, overflowY: "auto", padding: "28px 32px", display: "flex", flexDirection: "column", gap: "12px", scrollbarWidth: "thin" },
  errorBanner: { padding: "12px 16px", borderRadius: "12px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.22)", color: "#f87171", fontSize: "13px" },
  heroWrap: { textAlign: "center", padding: "20px 20px 12px", display: "flex", flexDirection: "column", alignItems: "center", gap: "10px", position: "relative" },
  heroGlow: { position: "absolute", top: "0", left: "50%", transform: "translateX(-50%)", width: "160px", height: "160px", borderRadius: "50%", background: "radial-gradient(circle, rgba(59,130,246,0.18) 0%, transparent 70%)", filter: "blur(30px)", animation: "heroGlow 4s ease-in-out infinite", pointerEvents: "none" },
  heroIcon: { position: "relative", zIndex: 1, width: "52px", height: "52px", borderRadius: "16px", background: "linear-gradient(135deg, #3b82f6, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 8px 28px rgba(59,130,246,0.4)" },
  heroTitle: { position: "relative", zIndex: 1, margin: 0, fontSize: "20px", fontWeight: 800, color: "#f0f4ff", letterSpacing: "-0.02em" },
  heroSubtitle: { position: "relative", zIndex: 1, margin: 0, fontSize: "13px", color: "#64748b", maxWidth: "380px" },
  agentBubbleAvatar: { width: "32px", height: "32px", borderRadius: "10px", flexShrink: 0, background: "linear-gradient(135deg, #8b5cf6, #3b82f6)", display: "flex", alignItems: "center", justifyContent: "center" },
  userBubbleAvatar: { width: "32px", height: "32px", borderRadius: "10px", flexShrink: 0, background: "linear-gradient(135deg, #3b82f6, #06b6d4)", display: "flex", alignItems: "center", justifyContent: "center" },
  typingBubble: { padding: "14px 20px", borderRadius: "20px 20px 20px 4px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.09)", display: "flex", gap: "6px", alignItems: "center" },
  typingDot: { width: "7px", height: "7px", borderRadius: "50%", background: "#6366f1" },
  inputArea: { padding: "16px 24px 18px", borderTop: "1px solid rgba(255,255,255,0.07)", background: "rgba(6,11,20,0.7)", backdropFilter: "blur(12px)", flexShrink: 0 },
  inputRow: { display: "flex", gap: "10px", alignItems: "center", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "16px", padding: "7px 7px 7px 20px", transition: "border-color 0.2s, box-shadow 0.2s" },
  inputRowBase: { borderColor: "rgba(255,255,255,0.1)", boxShadow: "none" },
  inputRowFocused: { borderColor: "rgba(59,130,246,0.45)", boxShadow: "0 0 0 3px rgba(59,130,246,0.1)" },
  inputField: { flex: 1, border: "none", outline: "none", background: "transparent", color: "#f0f4ff", fontSize: "15px", fontFamily: "'Inter', sans-serif", padding: "8px 0" },
  sendBtn: { width: "44px", height: "44px", borderRadius: "12px", flexShrink: 0, border: "none", display: "flex", alignItems: "center", justifyContent: "center", transition: "transform 0.15s, box-shadow 0.2s, background 0.2s" },
  inputHint: { margin: "10px 0 0", fontSize: "11px", color: "#1e293b", textAlign: "center" },
  kbd: { background: "rgba(255,255,255,0.07)", padding: "1px 6px", borderRadius: "4px", border: "1px solid rgba(255,255,255,0.1)", color: "#475569", fontSize: "10px" },
};

/* ─── Language Toggle Styles ─── */
const langToggleStyles = {
  wrap: { display: "flex", gap: "4px", marginLeft: "auto", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "10px", padding: "3px" },
  btn:  { padding: "4px 10px", borderRadius: "7px", fontSize: "11px", fontWeight: 600, cursor: "pointer", border: "none", fontFamily: "'Inter', sans-serif", transition: "all 0.18s" },
  active:   { background: "linear-gradient(135deg, #3b82f6, #06b6d4)", color: "#fff", boxShadow: "0 2px 8px rgba(59,130,246,0.4)" },
  inactive: { background: "transparent", color: "#475569" },
};
