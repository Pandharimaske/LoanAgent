import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ShieldCheck, Zap, Bot, ArrowRight,
  MessageSquare, TrendingUp, Lock
} from "lucide-react";
import ParticleBackground from "./ParticleBackground";

export default function Home() {
  const navigate = useNavigate();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), 100);
    return () => clearTimeout(t);
  }, []);

  const features = [
    {
      icon: Bot,
      color: "#3b82f6",
      glow: "rgba(59,130,246,0.15)",
      title: "AI-Powered Chat Agent",
      desc: "Have a natural conversation with our intelligent agent. It understands your financial needs and recommends the best loan products in real-time.",
    },
    {
      icon: TrendingUp,
      color: "#10b981",
      glow: "rgba(16,185,129,0.15)",
      title: "Best Rates, Instantly",
      desc: "Our AI compares rates across 50+ lenders in seconds. Get pre-approval and personalised offers without the paperwork or waiting rooms.",
    },
    {
      icon: Lock,
      color: "#8b5cf6",
      glow: "rgba(139,92,246,0.15)",
      title: "Bank-Grade Security",
      desc: "End-to-end 256-bit AES encryption safeguards every message. Your financial data never leaves our secure, SOC 2-compliant servers.",
    },
  ];

  return (
    <div style={styles.root}>
      <ParticleBackground />
      <div style={styles.gridOverlay} />

      {/* ═══ NAVBAR ═══ */}
      <nav style={styles.nav}>
        <div style={styles.navBrand}>
          <div style={styles.navLogo}>
            <ShieldCheck size={20} color="#fff" />
          </div>
          <span style={styles.navName}>BrainBack.AI</span>
        </div>
        <div style={styles.navActions}>
          <button onClick={() => navigate("/dashboard")} style={styles.navLoginBtn}
            onMouseEnter={e => { e.currentTarget.style.color = "#f0f4ff"; e.currentTarget.style.background = "rgba(255,255,255,0.06)"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "#94a3b8"; e.currentTarget.style.background = "transparent"; }}>
            Sign In
          </button>
          <button onClick={() => navigate("/signup")} style={styles.navSignupBtn}
            onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "0 6px 28px rgba(59,130,246,0.5)"; }}
            onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.boxShadow = "0 4px 20px rgba(59,130,246,0.35)"; }}>
            Get Started <ArrowRight size={14} />
          </button>
        </div>
      </nav>

      {/* ═══ HERO ═══ */}
      <section style={styles.hero}>
        <div style={styles.heroGlowA} />
        <div style={styles.heroGlowB} />

        <div style={{
          ...styles.heroContent,
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0)" : "translateY(24px)",
        }}>
          <div style={styles.heroBadge}>
            <Zap size={12} color="#f59e0b" />
            <span>Hackathon 2026 · AI-Powered Fintech</span>
          </div>

          <h1 style={styles.heroTitle}>
            Your AI Loan Agent.<br />
            <span style={styles.heroTitleGradient}>Smarter. Faster. Secure.</span>
          </h1>
        </div>
      </section>

      {/* ═══ FEATURES ═══ */}
      <section style={{
        ...styles.featuresSection,
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(30px)",
        transition: "all 1s cubic-bezier(0.16, 1, 0.3, 1) 0.4s",
      }}>
        <div style={styles.featuresGrid}>
          {features.map((f, i) => {
            const Icon = f.icon;
            return (
              <div key={i} style={styles.featureCard}
                onMouseEnter={e => {
                  e.currentTarget.style.borderColor = `${f.color}40`;
                  e.currentTarget.style.transform = "translateY(-6px)";
                  e.currentTarget.style.boxShadow = `0 20px 60px rgba(0,0,0,0.4), 0 0 40px ${f.glow}`;
                  e.currentTarget.style.background = "rgba(255,255,255,0.06)";
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
                  e.currentTarget.style.transform = "translateY(0)";
                  e.currentTarget.style.boxShadow = "0 8px 32px rgba(0,0,0,0.3)";
                  e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                }}
              >
                <div style={{
                  ...styles.featureIconWrap,
                  background: `${f.color}10`,
                  border: `1px solid ${f.color}25`,
                  boxShadow: `0 0 24px ${f.glow}`,
                }}>
                  <Icon size={24} color={f.color} />
                </div>
                <h3 style={styles.featureTitle}>{f.title}</h3>
                <p style={styles.featureDesc}>{f.desc}</p>
                <div style={{ ...styles.featureAccentLine, background: f.color }} />
              </div>
            );
          })}
        </div>
      </section>

      <style>{`
        @keyframes heroFloat { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
        html { scroll-behavior: smooth; }
        a { text-decoration: none; }
      `}</style>
    </div>
  );
}

/* ─── Styles ─── */
const styles = {
  root: {
    minHeight: "100vh",
    background: "linear-gradient(135deg, #060b14 0%, #0a0f1e 50%, #0d1427 100%)",
    fontFamily: "'Inter', -apple-system, sans-serif",
    color: "#f0f4ff",
    position: "relative",
    overflow: "hidden",
  },
  gridOverlay: {
    position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none",
    backgroundImage: "linear-gradient(rgba(59,130,246,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(59,130,246,0.025) 1px, transparent 1px)",
    backgroundSize: "64px 64px",
  },

  /* Nav */
  nav: {
    position: "sticky", top: 0, zIndex: 100,
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "0 40px", height: "64px",
    background: "rgba(6,11,20,0.85)", backdropFilter: "blur(24px)",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
  },
  navBrand: { display: "flex", alignItems: "center", gap: "10px" },
  navLogo: {
    width: "36px", height: "36px", borderRadius: "10px",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    display: "flex", alignItems: "center", justifyContent: "center",
    boxShadow: "0 4px 16px rgba(59,130,246,0.4)",
  },
  navName: { fontWeight: 800, fontSize: "18px", color: "#f0f4ff" },
  navActions: { display: "flex", alignItems: "center", gap: "12px" },
  navLoginBtn: {
    background: "transparent", border: "none", color: "#94a3b8",
    fontSize: "14px", fontWeight: 600, cursor: "pointer",
    padding: "8px 16px", borderRadius: "10px", fontFamily: "'Inter', sans-serif",
    transition: "all 0.2s",
  },
  navSignupBtn: {
    display: "flex", alignItems: "center", gap: "6px",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    border: "none", color: "#fff", fontSize: "13px", fontWeight: 700,
    padding: "9px 20px", borderRadius: "10px", cursor: "pointer",
    fontFamily: "'Inter', sans-serif",
    boxShadow: "0 4px 20px rgba(59,130,246,0.35)",
    transition: "all 0.2s",
  },

  /* Hero */
  hero: {
    position: "relative", zIndex: 1,
    display: "flex", flexDirection: "column", alignItems: "center",
    textAlign: "center", padding: "70px 24px 40px",
    maxWidth: "900px", margin: "0 auto",
  },
  heroContent: {
    display: "flex", flexDirection: "column", alignItems: "center",
    transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1)",
  },
  heroGlowA: {
    position: "absolute", top: "-100px", left: "50%", transform: "translateX(-50%)",
    width: "600px", height: "400px", borderRadius: "50%",
    background: "radial-gradient(circle, rgba(59,130,246,0.12) 0%, transparent 70%)",
    filter: "blur(60px)", pointerEvents: "none",
  },
  heroGlowB: {
    position: "absolute", top: "0", left: "50%", transform: "translateX(-60%)",
    width: "400px", height: "300px", borderRadius: "50%",
    background: "radial-gradient(circle, rgba(139,92,246,0.08) 0%, transparent 70%)",
    filter: "blur(60px)", pointerEvents: "none",
  },
  heroBadge: {
    position: "relative", zIndex: 1,
    display: "inline-flex", alignItems: "center", gap: "8px",
    padding: "6px 16px", borderRadius: "20px",
    background: "rgba(245,158,11,0.08)",
    border: "1px solid rgba(245,158,11,0.2)",
    fontSize: "12px", fontWeight: 600, color: "#fbbf24",
    marginBottom: "28px",
  },
  heroTitle: {
    position: "relative", zIndex: 1,
    fontSize: "clamp(36px, 5vw, 56px)", fontWeight: 900,
    lineHeight: 1.1, letterSpacing: "-0.04em",
    margin: "0 0 20px", color: "#f0f4ff",
    textAlign: "center",
  },
  heroTitleGradient: {
    background: "linear-gradient(135deg, #3b82f6, #06b6d4, #8b5cf6)",
    WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
  },
  heroSubtitle: {
    position: "relative", zIndex: 1,
    fontSize: "17px", lineHeight: 1.7, color: "#64748b",
    maxWidth: "600px", margin: "0 0 36px", textAlign: "center",
  },
  heroBtns: {
    position: "relative", zIndex: 1,
    display: "flex", gap: "14px", flexWrap: "wrap", justifyContent: "center",
    marginBottom: "0",
  },
  heroPrimaryBtn: {
    display: "flex", alignItems: "center", gap: "8px",
    padding: "14px 28px", borderRadius: "12px",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    border: "none", color: "#fff", fontSize: "15px", fontWeight: 700,
    cursor: "pointer", fontFamily: "'Inter', sans-serif",
    boxShadow: "0 4px 24px rgba(59,130,246,0.35)",
    transition: "all 0.25s",
  },
  heroSecondaryBtn: {
    display: "flex", alignItems: "center", gap: "8px",
    padding: "14px 28px", borderRadius: "12px",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.1)", color: "#94a3b8",
    fontSize: "15px", fontWeight: 600, cursor: "pointer",
    fontFamily: "'Inter', sans-serif", transition: "all 0.25s",
  },

  /* Features */
  featuresSection: {
    position: "relative", zIndex: 1,
    maxWidth: "1100px", margin: "0 auto",
    padding: "40px 24px 80px",
  },
  featuresGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: "24px",
  },
  featureCard: {
    position: "relative",
    padding: "32px 28px 28px",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: "20px",
    cursor: "default",
    transition: "all 0.35s cubic-bezier(0.16,1,0.3,1)",
    boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
    overflow: "hidden",
  },
  featureIconWrap: {
    width: "52px", height: "52px", borderRadius: "14px",
    display: "flex", alignItems: "center", justifyContent: "center",
    marginBottom: "20px",
  },
  featureTitle: {
    fontSize: "17px", fontWeight: 700, color: "#f0f4ff",
    margin: "0 0 10px", letterSpacing: "-0.01em",
  },
  featureDesc: {
    fontSize: "14px", color: "#64748b", lineHeight: 1.7, margin: "0 0 16px",
  },
  featureAccentLine: {
    width: "40px", height: "3px", borderRadius: "2px", opacity: 0.6,
  },
};
