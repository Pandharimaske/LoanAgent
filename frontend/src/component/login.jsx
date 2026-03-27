import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Eye, EyeOff, Mail, Lock, ShieldCheck, ArrowRight } from "lucide-react";

const BASE_URL = import.meta.env.VITE_BASE_URL || "http://localhost:8000";

const Login = () => {
  const navigate = useNavigate();

  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleChange = (e) => {
    setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");

    if (!formData.email || !formData.password) {
      return setError("Please fill all fields");
    }

    try {
      setLoading(true);
      const response = await axios.post(
        `${BASE_URL}/auth/login`,
        formData
      );

      if (response.data.success) {
        // Store all auth keys needed by dashboard
        localStorage.setItem("token", response.data.jwt_token);
        localStorage.setItem("sessionId", response.data.session_id);
        localStorage.setItem("userId", response.data.user_id);
        localStorage.setItem("user_id", response.data.user_id);
        localStorage.setItem("customer_id", response.data.customer_id || "");
        navigate("/dashboard");
      } else {
        setError(response.data.message || "Login failed");
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.message || "Login failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #0a0f1e 0%, #0d1427 50%, #060b14 100%)",
        position: "relative",
        overflow: "hidden",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      {/* Animated background orbs */}
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />

      {/* Grid overlay */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(rgba(59,130,246,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(59,130,246,0.03) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          zIndex: 0,
        }}
      />

      <div style={{ position: "relative", zIndex: 1, width: "100%", maxWidth: "420px", padding: "24px" }}>
        {/* Logo / brand */}
        <div style={{ textAlign: "center", marginBottom: "32px" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "56px",
              height: "56px",
              borderRadius: "16px",
              background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
              boxShadow: "0 8px 32px rgba(59,130,246,0.4)",
              marginBottom: "16px",
            }}
          >
            <ShieldCheck size={28} color="#fff" />
          </div>
          <h1
            style={{
              fontSize: "28px",
              fontWeight: 800,
              color: "#f0f4ff",
              margin: 0,
              letterSpacing: "-0.02em",
            }}
          >
            Welcome Back
          </h1>
          <p style={{ color: "#64748b", fontSize: "14px", marginTop: "6px" }}>
            Sign in to your Loan Agent account
          </p>
        </div>

        {/* Glass card */}
        <div className="auth-card" style={{ padding: "32px" }}>
          {/* Error banner */}
          {error && (
            <div
              style={{
                marginBottom: "20px",
                padding: "12px 16px",
                background: "rgba(239,68,68,0.1)",
                border: "1px solid rgba(239,68,68,0.25)",
                borderRadius: "10px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <span style={{ color: "#f87171", fontSize: "13px" }}>⚠ {error}</span>
            </div>
          )}

          <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {/* Email field */}
            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "#94a3b8", marginBottom: "8px", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                Email Address
              </label>
              <div style={{ position: "relative" }}>
                <Mail
                  size={16}
                  color="#475569"
                  style={{ position: "absolute", left: "14px", top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
                />
                <input
                  type="email"
                  name="email"
                  id="login-email"
                  placeholder="you@example.com"
                  value={formData.email}
                  onChange={handleChange}
                  className="auth-input"
                  style={{ paddingLeft: "42px" }}
                />
              </div>
            </div>

            {/* Password field */}
            <div>
              <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "#94a3b8", marginBottom: "8px", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                Password
              </label>
              <div style={{ position: "relative" }}>
                <Lock
                  size={16}
                  color="#475569"
                  style={{ position: "absolute", left: "14px", top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
                />
                <input
                  type={showPass ? "text" : "password"}
                  name="password"
                  id="login-password"
                  placeholder="Enter your password"
                  value={formData.password}
                  onChange={handleChange}
                  className="auth-input"
                  style={{ paddingLeft: "42px", paddingRight: "44px" }}
                />
                <button
                  type="button"
                  onClick={() => setShowPass((prev) => !prev)}
                  style={{
                    position: "absolute",
                    right: "14px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "#475569",
                    padding: 0,
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              id="login-submit"
              disabled={loading}
              className="btn-primary"
              style={{ marginTop: "8px", display: "flex", alignItems: "center", justifyContent: "center", gap: "8px" }}
            >
              {loading ? (
                <>
                  <span
                    style={{
                      width: "18px", height: "18px", border: "2px solid rgba(255,255,255,0.3)",
                      borderTopColor: "#fff", borderRadius: "50%",
                      animation: "spin 0.7s linear infinite", display: "inline-block",
                    }}
                  />
                  Signing in...
                </>
              ) : (
                <>
                  Sign In
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          {/* Divider */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px", margin: "24px 0 0" }}>
            <div style={{ flex: 1, height: "1px", background: "rgba(255,255,255,0.07)" }} />
            <span style={{ color: "#475569", fontSize: "12px" }}>New here?</span>
            <div style={{ flex: 1, height: "1px", background: "rgba(255,255,255,0.07)" }} />
          </div>

          <button
            onClick={() => navigate("/signup")}
            id="goto-signup"
            style={{
              display: "block",
              width: "100%",
              marginTop: "16px",
              padding: "12px",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "12px",
              color: "#94a3b8",
              fontSize: "14px",
              fontWeight: 600,
              cursor: "pointer",
              fontFamily: "'Inter', sans-serif",
              textAlign: "center",
              transition: "background 0.2s, color 0.2s",
            }}
            onMouseEnter={(e) => { e.target.style.background = "rgba(255,255,255,0.08)"; e.target.style.color = "#f0f4ff"; }}
            onMouseLeave={(e) => { e.target.style.background = "rgba(255,255,255,0.04)"; e.target.style.color = "#94a3b8"; }}
          >
            Create an account →
          </button>
        </div>

        <p style={{ textAlign: "center", marginTop: "24px", color: "#334155", fontSize: "12px" }}>
          Secured by BrainBack · End-to-end encrypted
        </p>
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
};

export default Login;