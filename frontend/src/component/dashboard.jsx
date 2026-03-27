import React, { useState, useRef, useEffect } from "react";
import { LogOut, Send, ShieldCheck, Loader2, Bot, User, Zap, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

const BASE_URL = import.meta.env.VITE_BASE_URL || "http://localhost:8000";

const dummyChat = [
  { id: 1, role: "agent", text: "Welcome to BrainBack Secure Banking. How can I help you today?" },
];

const SUGGESTIONS = [
  "What loan options are available for me?",
  "Check my loan eligibility",
  "What are the current interest rates?",
  "Help me apply for a home loan",
];

export default function DashboardPage() {
  const navigate = useNavigate();
  const [chat, setChat] = useState(dummyChat);
  const [input, setInput] = useState("");
  const [userData, setUserData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const messageIdRef = useRef(2);

  useEffect(() => {
    const fetchUserData = async () => {
      const sessionId = localStorage.getItem("sessionId");
      const token = localStorage.getItem("token");

      if (!sessionId || !token) {
        navigate("/login");
        return;
      }

      try {
        const response = await axios.get(
          `${BASE_URL}/auth/session/${sessionId}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );

        if (response.data.is_active) {
          setUserData({
            email: response.data.email,
            user_id: response.data.user_id,
            customer_id: response.data.customer_id || "Not assigned",
            session_id: response.data.session_id,
            session_expires: response.data.expires_at,
          });
        } else {
          throw new Error("Session expired");
        }
      } catch (err) {
        console.error("Session validation failed", err);
        localStorage.removeItem("token");
        localStorage.removeItem("sessionId");
        localStorage.removeItem("userId");
        localStorage.removeItem("user_id");
        localStorage.removeItem("customer_id");
        navigate("/login");
      } finally {
        setLoading(false);
      }
    };

    fetchUserData();
  }, [navigate]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("sessionId");
    localStorage.removeItem("userId");
    localStorage.removeItem("user_id");
    localStorage.removeItem("customer_id");
    navigate("/login");
  };

  const handleSend = async (text) => {
    const msgText = (text || input).trim();
    if (!msgText || sending) return;

    setInput("");
    setError("");

    const userMessageId = messageIdRef.current++;
    setChat((prev) => [...prev, { id: userMessageId, role: "user", text: msgText }]);
    setSending(true);

    try {
      const sessionId = localStorage.getItem("sessionId");
      const response = await axios.post(`${BASE_URL}/session/message`, {
        session_id: sessionId || "demo_session",
        user_input: msgText,
        language: "en",
      });

      const agentText = response.data.agent_response || "I couldn't process that. Please try again.";
      const agentMessageId = messageIdRef.current++;
      setChat((prev) => [...prev, { id: agentMessageId, role: "agent", text: agentText }]);

      if (response.data.error) setError(response.data.error);
    } catch (err) {
      const errorText = err.response?.data?.detail || "Connection error. Please try again.";
      const errorMessageId = messageIdRef.current++;
      setChat((prev) => [
        ...prev,
        { id: errorMessageId, role: "agent", text: "⚠️ " + errorText },
      ]);
      setError(errorText);
      console.error("Message send failed", err);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  /* ─── Loading Screen ─── */
  if (loading) {
    return (
      <div style={styles.loadingWrap}>
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div style={styles.loadingInner}>
          <div style={styles.loadingIcon}>
            <ShieldCheck size={34} color="#fff" />
          </div>
          <p style={styles.loadingTitle}>Authenticating Session</p>
          <p style={styles.loadingSubtitle}>Verifying your secure connection…</p>
          <div style={styles.dotsRow}>
            {[0, 1, 2].map(i => (
              <div key={i} className="typing-dot" style={styles.dot} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const isFirstLoad = chat.length === 1;

  /* ─── Dashboard ─── */
  return (
    <div style={styles.root}>
      {/* Background layer */}
      <div style={styles.bgGrid} />
      <div style={{ ...styles.bgOrb, top: "-180px", left: "-180px", width: "550px", height: "550px", background: "radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 70%)", animationDuration: "9s" }} />
      <div style={{ ...styles.bgOrb, bottom: "-150px", right: "-100px", width: "450px", height: "450px", background: "radial-gradient(circle, rgba(139,92,246,0.09) 0%, transparent 70%)", animationDuration: "13s", animationDirection: "reverse" }} />
      <div style={{ ...styles.bgOrb, top: "40%", right: "25%", width: "300px", height: "300px", background: "radial-gradient(circle, rgba(6,182,212,0.07) 0%, transparent 70%)", animationDuration: "11s" }} />

      {/* ── Navbar ── */}
      <nav style={styles.nav}>
        {/* Brand */}
        <div style={styles.brand}>
          <div style={styles.brandIcon}>
            <ShieldCheck size={22} color="#fff" />
          </div>
          <div>
            <span style={styles.brandName}>BrainBack</span>
            <span style={styles.brandTag}> Secure</span>
          </div>
        </div>

        {/* Centre — user greeting */}
        {userData && (
          <div style={styles.navCenter}>
            <Sparkles size={13} color="#f59e0b" />
            <span style={styles.greeting}>
              {userData.email}
            </span>
          </div>
        )}

        {/* Right */}
        <div style={styles.navRight}>
          <div className="pulse-badge" style={styles.activeBadge}>
            <div style={styles.activeDot} />
            <span style={styles.activeTxt}>Session Active</span>
          </div>
          <button id="logout-btn" onClick={handleLogout} style={styles.logoutBtn}
            onMouseEnter={e => Object.assign(e.currentTarget.style, styles.logoutBtnHover)}
            onMouseLeave={e => Object.assign(e.currentTarget.style, styles.logoutBtnBase)}>
            <LogOut size={15} />
            Logout
          </button>
        </div>
      </nav>

      {/* ── Chat Container ── */}
      <div style={styles.chatWrap}>
        <div style={styles.chatCard}>

          {/* Chat header bar */}
          <div style={styles.chatHeader}>
            <div style={styles.agentAvatar}>
              <Bot size={22} color="#fff" />
            </div>
            <div>
              <p style={styles.agentName}>Loan Agent AI</p>
              <p style={styles.agentStatus}>
                <span style={styles.statusDot} />
                Online · Powered by BrainBack Intelligence
              </p>
            </div>
            <div style={styles.msgCount}>
              <Zap size={13} color="#f59e0b" />
              <span style={styles.msgCountTxt}>{chat.length} messages</span>
            </div>
          </div>

          {/* Messages area */}
          <div style={styles.messagesArea}>
            {error && (
              <div style={styles.errorBanner}>⚠ {error}</div>
            )}

            {/* Welcome hero — shown when only the first agent msg exists */}
            {isFirstLoad && (
              <div style={styles.heroWrap}>
                <div style={styles.heroGlow} />
                <div style={styles.heroIcon}>
                  <ShieldCheck size={36} color="#fff" />
                </div>
                <h2 style={styles.heroTitle}>How can I help you today?</h2>
                <p style={styles.heroSubtitle}>
                  Ask me anything about loans, eligibility, rates, or your account.
                </p>
              </div>
            )}

            {/* Suggestion chips — only on first load */}
            {isFirstLoad && (
              <div style={styles.chipsWrap}>
                {SUGGESTIONS.map((s, i) => (
                  <button key={i} onClick={() => handleSend(s)} style={styles.chip}
                    onMouseEnter={e => Object.assign(e.currentTarget.style, styles.chipHover)}
                    onMouseLeave={e => Object.assign(e.currentTarget.style, styles.chipBase)}>
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* Messages */}
            {chat.map((msg) => (
              <div key={msg.id} className="chat-bubble" style={{
                display: "flex",
                justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                alignItems: "flex-end",
                gap: "10px",
                marginBottom: "4px",
              }}>
                {msg.role === "agent" && (
                  <div style={styles.agentBubbleAvatar}>
                    <Bot size={16} color="#fff" />
                  </div>
                )}
                <div style={{
                  maxWidth: "68%",
                  padding: "13px 18px",
                  fontSize: "14px",
                  lineHeight: "1.65",
                  whiteSpace: "pre-line",
                  wordBreak: "break-word",
                  borderRadius: msg.role === "user"
                    ? "20px 20px 4px 20px"
                    : "20px 20px 20px 4px",
                  ...(msg.role === "user"
                    ? {
                        background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
                        color: "#fff",
                        boxShadow: "0 6px 24px rgba(59,130,246,0.35)",
                      }
                    : {
                        background: "rgba(255,255,255,0.06)",
                        color: "#e2e8f0",
                        border: "1px solid rgba(255,255,255,0.09)",
                        boxShadow: "0 2px 12px rgba(0,0,0,0.25)",
                      }),
                }}>
                  {msg.text}
                </div>
                {msg.role === "user" && (
                  <div style={styles.userBubbleAvatar}>
                    <User size={16} color="#fff" />
                  </div>
                )}
              </div>
            ))}

            {/* Typing indicator */}
            {sending && (
              <div className="chat-bubble" style={{ display: "flex", alignItems: "flex-end", gap: "10px", marginBottom: "4px" }}>
                <div style={styles.agentBubbleAvatar}>
                  <Bot size={16} color="#fff" />
                </div>
                <div style={styles.typingBubble}>
                  {[0, 1, 2].map(i => (
                    <div key={i} className="typing-dot" style={styles.typingDot} />
                  ))}
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* ── Input bar ── */}
          <div style={styles.inputArea}>
            <div style={styles.inputRow}
              onFocusCapture={e => Object.assign(e.currentTarget.style, styles.inputRowFocused)}
              onBlurCapture={e => Object.assign(e.currentTarget.style, styles.inputRowBase)}>
              <input
                ref={inputRef}
                id="chat-input"
                type="text"
                placeholder={sending ? "Agent is thinking…" : "Type a message or ask a question…"}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !sending && handleSend()}
                disabled={sending}
                style={styles.inputField}
              />
              <button
                id="send-btn"
                onClick={() => handleSend()}
                disabled={sending || !input.trim()}
                style={{
                  ...styles.sendBtn,
                  background: sending || !input.trim()
                    ? "rgba(255,255,255,0.06)"
                    : "linear-gradient(135deg, #3b82f6, #06b6d4)",
                  boxShadow: sending || !input.trim() ? "none" : "0 0 20px rgba(59,130,246,0.5)",
                  cursor: sending || !input.trim() ? "not-allowed" : "pointer",
                  opacity: sending ? 0.55 : 1,
                }}
                onMouseEnter={e => { if (!sending && input.trim()) e.currentTarget.style.transform = "scale(1.08)"; }}
                onMouseLeave={e => { e.currentTarget.style.transform = "scale(1)"; }}
              >
                {sending
                  ? <Loader2 size={20} color="#94a3b8" style={{ animation: "spin 0.7s linear infinite" }} />
                  : <Send size={20} color="#fff" />
                }
              </button>
            </div>
            <p style={styles.inputHint}>
              Press <kbd style={styles.kbd}>Enter</kbd> to send · Powered by BrainBack Intelligence
            </p>
          </div>

        </div>
      </div>

      <style>{`
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes orbFloat {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33%       { transform: translate(20px, -30px) scale(1.04); }
          66%       { transform: translate(-10px, 18px) scale(0.97); }
        }
        @keyframes heroGlow {
          0%, 100% { opacity: 0.5; transform: scale(1); }
          50%       { opacity: 0.8; transform: scale(1.15); }
        }
      `}</style>
    </div>
  );
}

/* ─── Style objects ─── */
const styles = {
  root: {
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    background: "linear-gradient(135deg, #060b14 0%, #0a0f1e 50%, #0d1427 100%)",
    fontFamily: "'Inter', sans-serif",
    color: "#f0f4ff",
    position: "relative",
    overflow: "hidden",
  },
  bgGrid: {
    position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none",
    backgroundImage:
      "linear-gradient(rgba(59,130,246,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(59,130,246,0.035) 1px, transparent 1px)",
    backgroundSize: "64px 64px",
  },
  bgOrb: {
    position: "fixed", borderRadius: "50%",
    filter: "blur(60px)", zIndex: 0, pointerEvents: "none",
    animation: "orbFloat var(--dur,10s) ease-in-out infinite",
  },

  /* Loading */
  loadingWrap: {
    minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
    background: "linear-gradient(135deg, #060b14 0%, #0a0f1e 60%, #0d1427 100%)",
    fontFamily: "'Inter', sans-serif", position: "relative", overflow: "hidden",
  },
  loadingInner: { position: "relative", zIndex: 1, textAlign: "center" },
  loadingIcon: {
    width: "72px", height: "72px", borderRadius: "22px", margin: "0 auto 20px",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    display: "flex", alignItems: "center", justifyContent: "center",
    boxShadow: "0 0 60px rgba(59,130,246,0.55)",
  },
  loadingTitle: { color: "#f0f4ff", fontSize: "20px", fontWeight: 700, margin: "0 0 8px" },
  loadingSubtitle: { color: "#475569", fontSize: "14px", margin: "0 0 24px" },
  dotsRow: { display: "flex", gap: "8px", justifyContent: "center" },
  dot: { width: "8px", height: "8px", borderRadius: "50%", background: "#3b82f6" },

  /* Navbar */
  nav: {
    position: "relative", zIndex: 10,
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 28px", height: "64px",
    background: "rgba(6,11,20,0.88)",
    backdropFilter: "blur(24px)",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
    boxShadow: "0 1px 32px rgba(0,0,0,0.5)",
    flexShrink: 0,
  },
  brand: { display: "flex", alignItems: "center", gap: "12px" },
  brandIcon: {
    width: "40px", height: "40px", borderRadius: "12px",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    display: "flex", alignItems: "center", justifyContent: "center",
    boxShadow: "0 4px 20px rgba(59,130,246,0.45)",
  },
  brandName: { fontWeight: 800, fontSize: "19px", letterSpacing: "-0.02em", color: "#f0f4ff" },
  brandTag: {
    fontWeight: 800, fontSize: "19px", letterSpacing: "-0.02em",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
  },
  navCenter: {
    display: "flex", alignItems: "center", gap: "6px",
    padding: "6px 14px", borderRadius: "20px",
    background: "rgba(245,158,11,0.08)",
    border: "1px solid rgba(245,158,11,0.18)",
  },
  greeting: { color: "#94a3b8", fontSize: "13px", fontWeight: 500 },
  navRight: { display: "flex", alignItems: "center", gap: "14px" },
  activeBadge: {
    display: "flex", alignItems: "center", gap: "7px",
    padding: "6px 14px", borderRadius: "20px",
    background: "rgba(16,185,129,0.1)",
    border: "1px solid rgba(16,185,129,0.25)",
  },
  activeDot: { width: "7px", height: "7px", borderRadius: "50%", background: "#10b981" },
  activeTxt: { color: "#10b981", fontSize: "12px", fontWeight: 600 },
  logoutBtn: {
    display: "flex", alignItems: "center", gap: "7px",
    padding: "8px 18px", borderRadius: "10px", border: "1px solid rgba(239,68,68,0.22)",
    background: "rgba(239,68,68,0.1)", color: "#f87171",
    fontSize: "13px", fontWeight: 600, cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    transition: "all 0.2s",
  },
  logoutBtnBase: { background: "rgba(239,68,68,0.1)", borderColor: "rgba(239,68,68,0.22)" },
  logoutBtnHover: { background: "rgba(239,68,68,0.18)", borderColor: "rgba(239,68,68,0.45)" },

  /* Chat wrap */
  chatWrap: {
    position: "relative", zIndex: 1,
    flex: 1, display: "flex", alignItems: "stretch",
    maxWidth: "900px", width: "100%",
    margin: "28px auto",
    padding: "0 24px",
    boxSizing: "border-box",
    minHeight: 0,
  },
  chatCard: {
    flex: 1, display: "flex", flexDirection: "column",
    background: "rgba(255,255,255,0.035)",
    backdropFilter: "blur(24px)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: "24px",
    overflow: "hidden",
    boxShadow: "0 20px 80px rgba(0,0,0,0.55), 0 0 0 1px rgba(59,130,246,0.05)",
  },

  /* Chat header */
  chatHeader: {
    padding: "18px 28px",
    borderBottom: "1px solid rgba(255,255,255,0.07)",
    background: "rgba(255,255,255,0.025)",
    display: "flex", alignItems: "center", gap: "14px",
    flexShrink: 0,
  },
  agentAvatar: {
    width: "44px", height: "44px", borderRadius: "14px", flexShrink: 0,
    background: "linear-gradient(135deg, #8b5cf6, #3b82f6)",
    display: "flex", alignItems: "center", justifyContent: "center",
    boxShadow: "0 6px 20px rgba(139,92,246,0.35)",
  },
  agentName: { margin: 0, fontWeight: 700, fontSize: "15px", color: "#f0f4ff" },
  agentStatus: { margin: 0, fontSize: "12px", color: "#10b981", display: "flex", alignItems: "center", gap: "5px" },
  statusDot: { display: "inline-block", width: "6px", height: "6px", borderRadius: "50%", background: "#10b981" },
  msgCount: { marginLeft: "auto", display: "flex", alignItems: "center", gap: "6px" },
  msgCountTxt: { color: "#475569", fontSize: "12px" },

  /* Messages */
  messagesArea: {
    flex: 1, overflowY: "auto", padding: "28px 32px",
    display: "flex", flexDirection: "column", gap: "12px",
    scrollbarWidth: "thin",
  },
  errorBanner: {
    padding: "12px 16px", borderRadius: "12px",
    background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.22)",
    color: "#f87171", fontSize: "13px",
  },

  /* Hero */
  heroWrap: {
    textAlign: "center", padding: "40px 20px 20px",
    display: "flex", flexDirection: "column", alignItems: "center", gap: "14px",
    position: "relative",
  },
  heroGlow: {
    position: "absolute", top: "10px", left: "50%", transform: "translateX(-50%)",
    width: "220px", height: "220px", borderRadius: "50%",
    background: "radial-gradient(circle, rgba(59,130,246,0.18) 0%, transparent 70%)",
    filter: "blur(30px)", animation: "heroGlow 4s ease-in-out infinite",
    pointerEvents: "none",
  },
  heroIcon: {
    position: "relative", zIndex: 1,
    width: "72px", height: "72px", borderRadius: "22px",
    background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
    display: "flex", alignItems: "center", justifyContent: "center",
    boxShadow: "0 12px 40px rgba(59,130,246,0.4)",
  },
  heroTitle: {
    position: "relative", zIndex: 1,
    margin: 0, fontSize: "26px", fontWeight: 800,
    color: "#f0f4ff", letterSpacing: "-0.02em",
  },
  heroSubtitle: {
    position: "relative", zIndex: 1,
    margin: 0, fontSize: "14px", color: "#64748b", maxWidth: "400px",
  },

  /* Suggestion chips */
  chipsWrap: {
    display: "flex", flexWrap: "wrap", gap: "10px",
    justifyContent: "center", paddingBottom: "8px",
  },
  chip: {
    padding: "9px 18px", borderRadius: "20px",
    background: "rgba(59,130,246,0.08)",
    border: "1px solid rgba(59,130,246,0.2)",
    color: "#93c5fd", fontSize: "13px", fontWeight: 500,
    cursor: "pointer", fontFamily: "'Inter', sans-serif",
    transition: "all 0.2s",
  },
  chipBase: {
    background: "rgba(59,130,246,0.08)", borderColor: "rgba(59,130,246,0.2)", color: "#93c5fd",
  },
  chipHover: {
    background: "rgba(59,130,246,0.16)", borderColor: "rgba(59,130,246,0.45)", color: "#eff6ff",
    transform: "translateY(-1px)", boxShadow: "0 4px 16px rgba(59,130,246,0.2)",
  },

  /* Bubble avatars */
  agentBubbleAvatar: {
    width: "32px", height: "32px", borderRadius: "10px", flexShrink: 0,
    background: "linear-gradient(135deg, #8b5cf6, #3b82f6)",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  userBubbleAvatar: {
    width: "32px", height: "32px", borderRadius: "10px", flexShrink: 0,
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    display: "flex", alignItems: "center", justifyContent: "center",
  },

  /* Typing bubble */
  typingBubble: {
    padding: "14px 20px", borderRadius: "20px 20px 20px 4px",
    background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.09)",
    display: "flex", gap: "6px", alignItems: "center",
  },
  typingDot: { width: "7px", height: "7px", borderRadius: "50%", background: "#6366f1" },

  /* Input area */
  inputArea: {
    padding: "16px 24px 18px",
    borderTop: "1px solid rgba(255,255,255,0.07)",
    background: "rgba(6,11,20,0.7)",
    backdropFilter: "blur(12px)",
    flexShrink: 0,
  },
  inputRow: {
    display: "flex", gap: "10px", alignItems: "center",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: "16px",
    padding: "7px 7px 7px 20px",
    transition: "border-color 0.2s, box-shadow 0.2s",
  },
  inputRowBase: {
    borderColor: "rgba(255,255,255,0.1)", boxShadow: "none",
  },
  inputRowFocused: {
    borderColor: "rgba(59,130,246,0.45)", boxShadow: "0 0 0 3px rgba(59,130,246,0.1)",
  },
  inputField: {
    flex: 1, border: "none", outline: "none",
    background: "transparent", color: "#f0f4ff",
    fontSize: "15px", fontFamily: "'Inter', sans-serif",
    padding: "8px 0",
  },
  sendBtn: {
    width: "44px", height: "44px", borderRadius: "12px", flexShrink: 0,
    border: "none",
    display: "flex", alignItems: "center", justifyContent: "center",
    transition: "transform 0.15s, box-shadow 0.2s, background 0.2s",
  },
  inputHint: {
    margin: "10px 0 0", fontSize: "11px", color: "#1e293b", textAlign: "center",
  },
  kbd: {
    background: "rgba(255,255,255,0.07)", padding: "1px 6px",
    borderRadius: "4px", border: "1px solid rgba(255,255,255,0.1)",
    color: "#475569", fontSize: "10px",
  },
};
