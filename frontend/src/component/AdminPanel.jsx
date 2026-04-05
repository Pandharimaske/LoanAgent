import React, { useState, useEffect } from "react";
import { LogOut, Search, Users, Database, ShieldCheck, ArrowLeft, Bot, Zap, Loader2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

const BASE_URL = import.meta.env.VITE_BASE_URL || "http://localhost:8000";

export default function AdminPanel() {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchUsers();
  }, [navigate]);

  const fetchUsers = async () => {
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        navigate("/login");
        return;
      }

      const response = await axios.get(`${BASE_URL}/admin/users`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.data.success) {
        setUsers(response.data.users);
      }
    } catch (err) {
      console.error("Failed to load users", err);
      if (err.response?.status === 401 || err.response?.status === 403) {
        // Not authorized or token expired
        handleLogout();
      } else {
        setError("Failed to load users. Please try again later.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    ["token","sessionId","userId","user_id","customer_id"].forEach(k => localStorage.removeItem(k));
    navigate("/login");
  };

  const filteredUsers = users.filter(user => 
    (user.full_name || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
    (user.customer_id || "").toLowerCase().includes(searchQuery.toLowerCase())
  );

  /* ─── Loading Screen ─── */
  if (loading) {
    return (
      <div style={styles.loadingWrap}>
        <div style={styles.loadingInner}>
          <div style={styles.loadingIcon}><ShieldCheck size={34} color="#fff" /></div>
          <p style={styles.loadingTitle}>Authenticating Admin</p>
          <p style={styles.loadingSubtitle}>Establishing secure encrypted connection…</p>
          <div style={styles.dotsRow}>{[0,1,2].map(i => <div key={i} className="typing-dot" style={styles.dot} />)}</div>
        </div>
      </div>
    );
  }

  /* ─── Stats Calculation ─── */
  const activeApplicationsUserCount = users.filter((u) => {
    if (!u.data) return false;
    try {
      const dataObj = typeof u.data === 'string' ? JSON.parse(u.data) : u.data;
      return dataObj.application_status === "In Progress" || dataObj.application_status === "Pending";
    } catch (e) {
      return false;
    }
  }).length;

  const validCibils = users.map(u => {
    if (!u.data) return 0;
    try {
      const dataObj = typeof u.data === 'string' ? JSON.parse(u.data) : u.data;
      return parseInt(dataObj?.cibil_score || 0);
    } catch (e) {
      return 0;
    }
  }).filter(s => s > 0 && !isNaN(s));
  
  const avgCibil = validCibils.length > 0 ? Math.round(validCibils.reduce((a, b) => a + b, 0) / validCibils.length) : "N/A";

  return (
    <div style={styles.root}>
      <div style={styles.bgGrid} />
      <div style={{ ...styles.bgOrb, top: "-180px", left: "-180px", width: "550px", height: "550px", background: "radial-gradient(circle, rgba(16,185,129,0.15) 0%, transparent 70%)", animationDuration: "9s" }} />
      <div style={{ ...styles.bgOrb, bottom: "-150px", right: "-100px", width: "450px", height: "450px", background: "radial-gradient(circle, rgba(59,130,246,0.12) 0%, transparent 70%)", animationDuration: "13s", animationDirection: "reverse" }} />

      {/* ── Navbar ── */}
      <nav style={styles.nav}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={styles.brand}>
            <div style={{...styles.brandIcon, background: "linear-gradient(135deg, #10b981, #059669)"}}>
              <ShieldCheck size={22} color="#fff" />
            </div>
            <div>
              <span style={styles.brandName}>BrainBack Control Center</span>
            </div>
          </div>
        </div>

        <div style={styles.navCenter}>
             <span style={styles.greeting}>Protected environment. Decrypted view active.</span>
        </div>

        <div style={styles.navRight}>
          <div className="pulse-badge" style={styles.activeBadge}>
            <ShieldCheck size={14} color="#10b981" />
            <span style={styles.activeTxt}>Admin Access</span>
          </div>
          <button id="logout-btn" onClick={handleLogout} style={styles.logoutBtn} onMouseEnter={e => Object.assign(e.currentTarget.style, styles.logoutBtnHover)} onMouseLeave={e => Object.assign(e.currentTarget.style, styles.logoutBtnBase)}>
            <LogOut size={15} /> Sign Out
          </button>
        </div>
      </nav>

      {/* ── Main Content ── */}
      <div style={styles.mainWrap}>
        
        {/* Stats Row */}
        <div style={styles.statsRow}>
            <div style={styles.statCard}>
                <div style={styles.statIconWrap}><Users size={20} color="#3b82f6" /></div>
                <div>
                   <p style={styles.statValue}>{users.length}</p>
                   <p style={styles.statLabel}>Total Customers</p>
                </div>
            </div>
            <div style={styles.statCard}>
                <div style={styles.statIconWrap}><Zap size={20} color="#f59e0b" /></div>
                <div>
                   <p style={styles.statValue}>{activeApplicationsUserCount}</p>
                   <p style={styles.statLabel}>Active Applications</p>
                </div>
            </div>
            <div style={styles.statCard}>
                <div style={styles.statIconWrap}><Database size={20} color="#10b981" /></div>
                <div>
                   <p style={styles.statValue}>{avgCibil}</p>
                   <p style={styles.statLabel}>Avg CIBIL Score</p>
                </div>
            </div>
        </div>

        <div style={styles.panelCard}>
          <div style={styles.panelHeader}>
             <h2 style={styles.panelTitle}>Customer Database</h2>
             <div style={styles.searchWrap}>
                 <Search size={16} color="#64748b" style={{marginLeft: 12}} />
                 <input 
                     type="text" 
                     placeholder="Search by name or ID..."
                     value={searchQuery}
                     onChange={(e) => setSearchQuery(e.target.value)}
                     style={styles.searchInput}
                 />
             </div>
          </div>

          <div style={styles.tableContainer}>
             {error ? (
                  <div style={styles.errorBanner}>⚠ {error}</div>
             ) : (
                <div style={{ overflowX: "auto", paddingBottom: "10px" }}>
                  <table style={styles.table}>
                      <thead>
                          <tr>
                              <th style={styles.th}>Customer ID</th>
                              <th style={styles.th}>Full Name</th>
                              <th style={styles.th}>DOB</th>
                              <th style={styles.th}>Phone</th>
                              <th style={styles.th}>Address</th>
                              <th style={styles.th}>City</th>
                              <th style={styles.th}>State</th>
                              <th style={styles.th}>Pincode</th>
                              <th style={styles.th}>Employer</th>
                              <th style={styles.th}>Job Title</th>
                              <th style={styles.th}>Years at Job</th>
                              <th style={styles.th}>Income</th>
                              <th style={styles.th}>Income Type</th>
                              <th style={styles.th}>CIBIL</th>
                              <th style={styles.th}>Active Loans</th>
                              <th style={styles.th}>Existing EMI (₹)</th>
                              <th style={styles.th}>Requested Loan</th>
                              <th style={styles.th}>Req. Amount (₹)</th>
                              <th style={styles.th}>Req. Tenure (m)</th>
                              <th style={styles.th}>Loan Purpose</th>
                              <th style={styles.th}>Co-App Name</th>
                              <th style={styles.th}>Co-App Relation</th>
                              <th style={styles.th}>Co-App Income (₹)</th>
                              <th style={styles.th}>Status</th>
                              <th style={styles.th}>Docs Submitted</th>
                              <th style={styles.th}>Created At</th>
                              <th style={styles.th}>Last Updated</th>
                          </tr>
                      </thead>
                      <tbody>
                          {filteredUsers.length > 0 ? filteredUsers.map((u) => {
                              let dataObj = {};
                              if (u.data) {
                                  try {
                                      dataObj = typeof u.data === 'string' ? JSON.parse(u.data) : u.data;
                                  } catch (e) {}
                              }
                              return (
                                  <tr key={u.customer_id || Math.random().toString()} style={styles.tr}>
                                      <td style={styles.td}><span style={styles.idBadge}>{(u.customer_id || "UNKNOWN").substring(0,10)}...</span></td>
                                      <td style={{...styles.td, fontWeight: 600, color: "#e2e8f0"}}>{u.full_name || "-"}</td>
                                      <td style={styles.td}>{dataObj.date_of_birth || "-"}</td>
                                      <td style={styles.td}>{dataObj.phone || "-"}</td>
                                      <td style={styles.td}>{dataObj.address ? dataObj.address.substring(0,15)+"..." : "-"}</td>
                                      <td style={styles.td}>{dataObj.city || "-"}</td>
                                      <td style={styles.td}>{dataObj.state || "-"}</td>
                                      <td style={styles.td}>{dataObj.pincode || "-"}</td>
                                      <td style={styles.td}>{dataObj.employer_name || "-"}</td>
                                      <td style={styles.td}>{dataObj.job_title || "-"}</td>
                                      <td style={styles.td}>{dataObj.years_at_job ?? "-"}</td>
                                      <td style={styles.td}>{dataObj.monthly_income ?? "-"}</td>
                                      <td style={styles.td}>{dataObj.income_type || "-"}</td>
                                      <td style={styles.td}>{dataObj.cibil_score || "-"}</td>
                                      <td style={styles.td}>{dataObj.number_of_active_loans ?? "-"}</td>
                                      <td style={styles.td}>{dataObj.total_existing_emi_monthly ?? "-"}</td>
                                      <td style={styles.td}>{dataObj.requested_loan_type || "-"}</td>
                                      <td style={styles.td}>{dataObj.requested_loan_amount ?? "-"}</td>
                                      <td style={styles.td}>{dataObj.requested_tenure_months ?? "-"}</td>
                                      <td style={styles.td}>{dataObj.loan_purpose || "-"}</td>
                                      <td style={styles.td}>{dataObj.coapplicant_name || "-"}</td>
                                      <td style={styles.td}>{dataObj.coapplicant_relation || "-"}</td>
                                      <td style={styles.td}>{dataObj.coapplicant_income ?? "-"}</td>
                                      <td style={styles.td}>
                                          <span style={{
                                              ...styles.statusBadge,
                                              background: dataObj.application_status === 'approved' ? 'rgba(16,185,129,0.1)' : 
                                                          dataObj.application_status === 'rejected' ? 'rgba(239,68,68,0.1)' : 'rgba(59,130,246,0.1)',
                                              color: dataObj.application_status === 'approved' ? '#10b981' : 
                                                     dataObj.application_status === 'rejected' ? '#f87171' : '#60a5fa'
                                          }}>
                                              {dataObj.application_status || "incomplete"}
                                          </span>
                                      </td>
                                      <td style={styles.td}>{dataObj.documents_submitted || "-"}</td>
                                      <td style={styles.td}>{dataObj.created_at ? new Date(dataObj.created_at).toLocaleString() : "-"}</td>
                                      <td style={styles.td}>{dataObj.last_updated ? new Date(dataObj.last_updated).toLocaleString() : (u.last_updated ? new Date(u.last_updated).toLocaleString() : "-")}</td>
                                  </tr>
                              );
                          }) : (
                             <tr><td colSpan="27" style={styles.emptyTd}>No customers found</td></tr>
                          )}
                      </tbody>
                  </table>
                </div>
             )}
          </div>
        </div>

      </div>

      <style>{`
        @keyframes spin    { to { transform: rotate(360deg); } }
        @keyframes orbFloat { 0%, 100% { transform: translate(0,0) scale(1); } 33% { transform: translate(20px,-30px) scale(1.04); } 66% { transform: translate(-10px,18px) scale(0.97); } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>
  );
}

/* ─── Style objects ─── */
const styles = {
  root: { minHeight: "100vh", display: "flex", flexDirection: "column", background: "linear-gradient(135deg, #060b14 0%, #0a0f1e 50%, #0d1427 100%)", fontFamily: "'Inter', sans-serif", color: "#f0f4ff", position: "relative", overflow: "hidden" },
  bgGrid: { position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none", backgroundImage: "linear-gradient(rgba(16,185,129,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(16,185,129,0.035) 1px, transparent 1px)", backgroundSize: "64px 64px" },
  bgOrb: { position: "fixed", borderRadius: "50%", filter: "blur(60px)", zIndex: 0, pointerEvents: "none", animation: "orbFloat var(--dur,10s) ease-in-out infinite" },
  
  loadingWrap: { minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "linear-gradient(135deg, #060b14 0%, #0a0f1e 60%, #0d1427 100%)", fontFamily: "'Inter', sans-serif", position: "relative", overflow: "hidden" },
  loadingInner: { position: "relative", zIndex: 1, textAlign: "center", animation: "slideUp 0.4s ease" },
  loadingIcon: { width: "72px", height: "72px", borderRadius: "22px", margin: "0 auto 20px", background: "linear-gradient(135deg, #10b981, #059669)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 60px rgba(16,185,129,0.55)" },
  loadingTitle: { color: "#f0f4ff", fontSize: "20px", fontWeight: 700, margin: "0 0 8px" },
  loadingSubtitle: { color: "#94a3b8", fontSize: "14px", margin: "0 0 24px" },
  dotsRow: { display: "flex", gap: "8px", justifyContent: "center" },
  dot: { width: "8px", height: "8px", borderRadius: "50%", background: "#10b981" },
  
  nav: { position: "relative", zIndex: 10, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 28px", height: "64px", background: "rgba(6,11,20,0.88)", backdropFilter: "blur(24px)", borderBottom: "1px solid rgba(255,255,255,0.06)", boxShadow: "0 1px 32px rgba(0,0,0,0.5)", flexShrink: 0 },
  brand: { display: "flex", alignItems: "center", gap: "12px" },
  brandIcon: { width: "40px", height: "40px", borderRadius: "12px", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 20px rgba(16,185,129,0.45)" },
  brandName: { fontWeight: 800, fontSize: "19px", letterSpacing: "-0.02em", color: "#f0f4ff" },
  navCenter: { display: "flex", alignItems: "center", gap: "6px", padding: "6px 14px", borderRadius: "20px", background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.18)" },
  greeting: { color: "#10b981", fontSize: "12px", fontWeight: 600, letterSpacing: "0.5px" },
  navRight: { display: "flex", alignItems: "center", gap: "14px" },
  activeBadge: { display: "flex", alignItems: "center", gap: "7px", padding: "6px 14px", borderRadius: "20px", background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.25)" },
  activeTxt: { color: "#10b981", fontSize: "12px", fontWeight: 600 },
  
  logoutBtn: { display: "flex", alignItems: "center", gap: "7px", padding: "8px 18px", borderRadius: "10px", border: "1px solid rgba(239,68,68,0.22)", background: "rgba(239,68,68,0.1)", color: "#f87171", fontSize: "13px", fontWeight: 600, cursor: "pointer", fontFamily: "'Inter', sans-serif", transition: "all 0.2s" },
  logoutBtnBase: { background: "rgba(239,68,68,0.1)", borderColor: "rgba(239,68,68,0.22)" },
  logoutBtnHover: { background: "rgba(239,68,68,0.18)", borderColor: "rgba(239,68,68,0.45)" },
  
  mainWrap: { position: "relative", zIndex: 1, flex: 1, display: "flex", flexDirection: "column", maxWidth: "1200px", width: "100%", margin: "24px auto", padding: "0 24px", boxSizing: "border-box", gap: "20px", overflow: "hidden" },
  
  statsRow: { display: "flex", gap: "20px", animation: "slideUp 0.3s ease" },
  statCard: { flex: 1, display: "flex", alignItems: "center", padding: "20px", background: "rgba(255,255,255,0.035)", backdropFilter: "blur(24px)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "20px", gap: "16px", boxShadow: "0 10px 40px rgba(0,0,0,0.3)" },
  statIconWrap: { width: "48px", height: "48px", borderRadius: "14px", background: "rgba(255,255,255,0.05)", display: "flex", alignItems: "center", justifyContent: "center" },
  statValue: { margin: "0 0 2px", fontSize: "24px", fontWeight: 800, color: "#fff" },
  statLabel: { margin: 0, fontSize: "13px", color: "#94a3b8", fontWeight: 500 },

  panelCard: { flex: 1, display: "flex", flexDirection: "column", background: "rgba(255,255,255,0.035)", backdropFilter: "blur(24px)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "24px", overflow: "hidden", boxShadow: "0 20px 80px rgba(0,0,0,0.55)", minHeight: 0, animation: "slideUp 0.4s ease" },
  panelHeader: { padding: "20px 28px", borderBottom: "1px solid rgba(255,255,255,0.07)", background: "rgba(255,255,255,0.025)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 },
  panelTitle: { margin: 0, fontSize: "16px", fontWeight: 700, color: "#f0f4ff" },
  searchWrap: { display: "flex", alignItems: "center", background: "rgba(0,0,0,0.2)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", width: "300px", overflow: "hidden" },
  searchInput: { flex: 1, background: "transparent", border: "none", color: "#fff", padding: "10px 12px", fontSize: "13px", outline: "none", fontFamily: "'Inter', sans-serif" },
  
  tableContainer: { flex: 1, padding: "0", position: "relative" },
  table: { width: "max-content", minWidth: "100%", borderCollapse: "separate", borderSpacing: 0, textAlign: "left" },
  th: { padding: "16px 20px", fontSize: "12px", fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.5px", background: "rgba(6,11,20,0.9)", position: "sticky", top: 0, backdropFilter: "blur(40px)", zIndex: 10, whiteSpace: "nowrap", borderBottom: "1px solid rgba(255,255,255,0.06)" },
  tr: { transition: "background 0.2s" },
  td: { padding: "16px 20px", fontSize: "14px", color: "#cbd5e1", whiteSpace: "nowrap", borderBottom: "1px solid rgba(255,255,255,0.04)" },
  emptyTd: { padding: "40px 20px", textAlign: "center", color: "#64748b", fontSize: "14px" },
  
  idBadge: { background: "rgba(255,255,255,0.05)", padding: "4px 8px", borderRadius: "6px", fontFamily: "monospace", fontSize: "12px", color: "#94a3b8" },
  statusBadge: { padding: "5px 10px", borderRadius: "20px", fontSize: "11px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px" },
  
  errorBanner: { padding: "16px", margin: "20px", borderRadius: "12px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.22)", color: "#f87171", fontSize: "14px", textAlign: "center" },
};
