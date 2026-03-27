import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  ShieldCheck, Zap, Bot, ArrowRight, TrendingUp,
  CreditCard, Brain, Lock, CheckCircle, ChevronRight,
  MessageSquare, BarChart3, Users, Star
} from "lucide-react";
import ParticleBackground from "./ParticleBackground";

export default function Home() {
  const navigate = useNavigate();
  const [visibleSections, setVisibleSections] = useState(new Set());

  /* ── Intersection Observer for scroll reveal ── */
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisibleSections((prev) => new Set([...prev, entry.target.id]));
          }
        });
      },
      { threshold: 0.15 }
    );

    document.querySelectorAll("[data-animate]").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const isVisible = (id) => visibleSections.has(id);

  /* ── Animated counter hook ── */
  const AnimatedNumber = ({ end, suffix = "", duration = 2000 }) => {
    const [val, setVal] = useState(0);
    const [started, setStarted] = useState(false);

    useEffect(() => {
      if (!started) return;
      const start = performance.now();
      const step = (now) => {
        const progress = Math.min((now - start) / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 4);
        setVal(Math.round(end * ease));
        if (progress < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, [started, end, duration]);

    return (
      <span ref={(el) => { if (el) { const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setStarted(true); obs.disconnect(); } }); obs.observe(el); } }}>
        {val.toLocaleString()}{suffix}
      </span>
    );
  };

  const features = [
    { icon: Bot, title: "AI-Powered Analysis", desc: "Our intelligent agent analyzes your financial profile in real-time to find the perfect loan match.", color: "#3b82f6" },
    { icon: ShieldCheck, title: "Bank-Grade Security", desc: "256-bit AES encryption protects every conversation and data point. Your info never leaves our secure servers.", color: "#10b981" },
    { icon: Zap, title: "Instant Decisions", desc: "Get pre-approval status in under 60 seconds. No paperwork, no waiting rooms, no hassle.", color: "#f59e0b" },
    { icon: TrendingUp, title: "Best Rate Finder", desc: "We compare rates across 50+ lenders automatically to find you the most competitive rates available.", color: "#8b5cf6" },
    { icon: CreditCard, title: "Credit Score Insights", desc: "Understand your creditworthiness with detailed breakdowns and actionable tips to improve.", color: "#06b6d4" },
    { icon: Brain, title: "Smart Recommendations", desc: "Personalized loan products tailored to your income, expenses, and financial goals.", color: "#ec4899" },
  ];

  const stats = [
    { value: 50000, suffix: "+", label: "Loans Processed" },
    { value: 98, suffix: "%", label: "Approval Rate" },
    { value: 4, suffix: ".9★", label: "User Rating" },
    { value: 60, suffix: "s", label: "Avg. Response" },
  ];

  const testimonials = [
    { name: "Sarah M.", role: "Home Buyer", text: "BrainBack found me a rate 1.2% lower than my bank offered. Saved me $14,000 over the life of my loan!", rating: 5 },
    { name: "James K.", role: "Small Business Owner", text: "The AI agent understood my business needs perfectly. Got approved for a business expansion loan in under 2 minutes.", rating: 5 },
    { name: "Priya R.", role: "First-Time Buyer", text: "I was nervous about applying for my first loan. The chat agent walked me through everything step by step.", rating: 5 },
  ];

  return (
    <div style={styles.root}>
      <ParticleBackground />

      {/* Grid overlay */}
      <div style={styles.gridOverlay} />

      {/* ═══ NAVBAR ═══ */}
      <nav style={styles.nav}>
        <div style={styles.navBrand}>
          <div style={styles.navLogo}>
            <ShieldCheck size={20} color="#fff" />
          </div>
          <span style={styles.navName}>Brain</span>
          <span style={styles.navNameAccent}>Back</span>
        </div>
        <div style={styles.navLinks}>
          <a href="#features" style={styles.navLink}>Features</a>
          <a href="#stats" style={styles.navLink}>Stats</a>
          <a href="#testimonials" style={styles.navLink}>Reviews</a>
        </div>
        <div style={styles.navActions}>
          <button onClick={() => navigate("/login")} style={styles.navLoginBtn}
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

        <div style={styles.heroBadge}>
          <Zap size={12} color="#f59e0b" />
          <span>Hackathon 2026 · AI-Powered Fintech</span>
        </div>

        <h1 style={styles.heroTitle}>
          Your AI Loan Agent.<br />
          <span style={styles.heroTitleGradient}>Smarter. Faster. Secure.</span>
        </h1>

        <p style={styles.heroSubtitle}>
          BrainBack uses advanced AI to analyze your financial profile, find the best rates across 50+ lenders,
          and get you approved — all through a simple chat conversation.
        </p>

        <div style={styles.heroBtns}>
          <button onClick={() => navigate("/signup")} style={styles.heroPrimaryBtn}
            onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px) scale(1.02)"; e.currentTarget.style.boxShadow = "0 8px 40px rgba(59,130,246,0.5)"; }}
            onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0) scale(1)"; e.currentTarget.style.boxShadow = "0 4px 24px rgba(59,130,246,0.35)"; }}>
            Start Free Consultation
            <ArrowRight size={16} />
          </button>
          <button onClick={() => navigate("/login")} style={styles.heroSecondaryBtn}
            onMouseEnter={e => { e.currentTarget.style.background = "rgba(255,255,255,0.08)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.2)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.1)"; }}>
            <MessageSquare size={16} />
            Chat with Agent
          </button>
        </div>

        {/* Floating preview card */}
        <div style={styles.previewCard}>
          <div style={styles.previewHeader}>
            <div style={styles.previewDot} />
            <div style={{ ...styles.previewDot, background: "#f59e0b" }} />
            <div style={{ ...styles.previewDot, background: "#10b981" }} />
            <span style={styles.previewTitle}>BrainBack Agent</span>
          </div>
          <div style={styles.previewChat}>
            <div style={styles.previewBubbleAgent}>
              <Bot size={14} color="#8b5cf6" style={{ flexShrink: 0 }} />
              <span>Hello! I'm your AI loan agent. I can help you find the best loan options. What are you looking for today?</span>
            </div>
            <div style={styles.previewBubbleUser}>
              <span>I'd like to apply for a home loan around $350,000</span>
            </div>
            <div style={styles.previewBubbleAgent}>
              <Bot size={14} color="#8b5cf6" style={{ flexShrink: 0 }} />
              <span>Great! Based on your credit profile, I found <strong style={{ color: "#10b981" }}>3 excellent options</strong> with rates starting at <strong style={{ color: "#3b82f6" }}>6.2% APR</strong>. Let me walk you through each one...</span>
            </div>
          </div>
        </div>
      </section>

      {/* ═══ STATS BAR ═══ */}
      <section id="stats" data-animate style={{
        ...styles.statsSection,
        opacity: isVisible("stats") ? 1 : 0,
        transform: isVisible("stats") ? "translateY(0)" : "translateY(30px)",
        transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1)",
      }}>
        {stats.map((s, i) => (
          <div key={i} style={styles.statItem}>
            <div style={styles.statValue}>
              <AnimatedNumber end={s.value} suffix={s.suffix} />
            </div>
            <div style={styles.statLabel}>{s.label}</div>
          </div>
        ))}
      </section>

      {/* ═══ FEATURES ═══ */}
      <section id="features" data-animate style={{
        ...styles.featuresSection,
        opacity: isVisible("features") ? 1 : 0,
        transform: isVisible("features") ? "translateY(0)" : "translateY(30px)",
        transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.1s",
      }}>
        <div style={styles.sectionHeader}>
          <div style={styles.sectionBadge}>
            <Zap size={12} color="#3b82f6" />
            <span>Features</span>
          </div>
          <h2 style={styles.sectionTitle}>Everything You Need</h2>
          <p style={styles.sectionSubtitle}>
            Powered by cutting-edge AI to make your loan journey seamless and transparent.
          </p>
        </div>
        <div style={styles.featuresGrid}>
          {features.map((f, i) => {
            const Icon = f.icon;
            return (
              <div key={i} style={styles.featureCard}
                onMouseEnter={e => {
                  e.currentTarget.style.borderColor = `${f.color}33`;
                  e.currentTarget.style.transform = "translateY(-4px)";
                  e.currentTarget.style.boxShadow = `0 16px 48px rgba(0,0,0,0.4), 0 0 30px ${f.color}15`;
                  e.currentTarget.style.background = "rgba(255,255,255,0.06)";
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
                  e.currentTarget.style.transform = "translateY(0)";
                  e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.2)";
                  e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                }}
              >
                <div style={{ ...styles.featureIcon, background: `${f.color}12`, border: `1px solid ${f.color}25` }}>
                  <Icon size={22} color={f.color} />
                </div>
                <h3 style={styles.featureTitle}>{f.title}</h3>
                <p style={styles.featureDesc}>{f.desc}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* ═══ HOW IT WORKS ═══ */}
      <section id="how" data-animate style={{
        ...styles.howSection,
        opacity: isVisible("how") ? 1 : 0,
        transform: isVisible("how") ? "translateY(0)" : "translateY(30px)",
        transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.1s",
      }}>
        <div style={styles.sectionHeader}>
          <div style={styles.sectionBadge}>
            <BarChart3 size={12} color="#06b6d4" />
            <span>How It Works</span>
          </div>
          <h2 style={styles.sectionTitle}>Three Simple Steps</h2>
          <p style={styles.sectionSubtitle}>From first message to approved loan in minutes, not days.</p>
        </div>
        <div style={styles.stepsRow}>
          {[
            { num: "01", title: "Chat with Agent", desc: "Tell our AI about your needs — home loan, auto loan, personal loan, or business financing.", icon: MessageSquare, color: "#3b82f6" },
            { num: "02", title: "Instant Analysis", desc: "Our AI analyzes your profile, compares 50+ lenders, and finds the best rates for you.", icon: Brain, color: "#8b5cf6" },
            { num: "03", title: "Get Approved", desc: "Receive your pre-approval and detailed loan options — all within a single conversation.", icon: CheckCircle, color: "#10b981" },
          ].map((step, i) => {
            const Icon = step.icon;
            return (
              <div key={i} style={styles.stepCard}>
                <div style={{ ...styles.stepNum, color: step.color }}>{step.num}</div>
                <div style={{ ...styles.stepIconWrap, background: `${step.color}12`, borderColor: `${step.color}25` }}>
                  <Icon size={24} color={step.color} />
                </div>
                <h3 style={styles.stepTitle}>{step.title}</h3>
                <p style={styles.stepDesc}>{step.desc}</p>
                {i < 2 && <div style={styles.stepConnector}><ChevronRight size={16} color="#334155" /></div>}
              </div>
            );
          })}
        </div>
      </section>

      {/* ═══ TESTIMONIALS ═══ */}
      <section id="testimonials" data-animate style={{
        ...styles.testimonialsSection,
        opacity: isVisible("testimonials") ? 1 : 0,
        transform: isVisible("testimonials") ? "translateY(0)" : "translateY(30px)",
        transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.1s",
      }}>
        <div style={styles.sectionHeader}>
          <div style={styles.sectionBadge}>
            <Star size={12} color="#f59e0b" />
            <span>Testimonials</span>
          </div>
          <h2 style={styles.sectionTitle}>Loved by Thousands</h2>
          <p style={styles.sectionSubtitle}>See what our users have to say about their experience.</p>
        </div>
        <div style={styles.testimonialsGrid}>
          {testimonials.map((t, i) => (
            <div key={i} style={styles.testimonialCard}
              onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-4px)"; e.currentTarget.style.borderColor = "rgba(59,130,246,0.2)"; }}
              onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0)"; e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)"; }}>
              <div style={styles.testimonialStars}>
                {[...Array(t.rating)].map((_, j) => <Star key={j} size={14} fill="#f59e0b" color="#f59e0b" />)}
              </div>
              <p style={styles.testimonialText}>"{t.text}"</p>
              <div style={styles.testimonialAuthor}>
                <div style={styles.testimonialAvatar}>
                  <Users size={16} color="#3b82f6" />
                </div>
                <div>
                  <div style={styles.testimonialName}>{t.name}</div>
                  <div style={styles.testimonialRole}>{t.role}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ═══ CTA ═══ */}
      <section style={styles.ctaSection}>
        <div style={styles.ctaGlow} />
        <h2 style={styles.ctaTitle}>Ready to find your perfect loan?</h2>
        <p style={styles.ctaSubtitle}>Join 50,000+ users who've already found better rates with BrainBack AI.</p>
        <button onClick={() => navigate("/signup")} style={styles.ctaBtn}
          onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px) scale(1.03)"; e.currentTarget.style.boxShadow = "0 8px 40px rgba(59,130,246,0.5)"; }}
          onMouseLeave={e => { e.currentTarget.style.transform = "translateY(0) scale(1)"; e.currentTarget.style.boxShadow = "0 4px 24px rgba(59,130,246,0.35)"; }}>
          Get Started — It's Free
          <ArrowRight size={16} />
        </button>
      </section>

      {/* ═══ FOOTER ═══ */}
      <footer style={styles.footer}>
        <div style={styles.footerInner}>
          <div style={styles.footerBrand}>
            <div style={styles.footerLogo}>
              <ShieldCheck size={18} color="#fff" />
            </div>
            <span style={{ fontWeight: 800, fontSize: "16px", color: "#f0f4ff" }}>Brain</span>
            <span style={{ fontWeight: 800, fontSize: "16px", background: "linear-gradient(135deg, #3b82f6, #06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>Back</span>
          </div>
          <p style={styles.footerText}>
            Built with ❤️ for Hackathon 2026 · AI-Powered Loan Intelligence
          </p>
          <div style={styles.footerLinks}>
            <span style={styles.footerLink}>Privacy</span>
            <span style={styles.footerDot}>·</span>
            <span style={styles.footerLink}>Terms</span>
            <span style={styles.footerDot}>·</span>
            <span style={styles.footerLink}>Support</span>
          </div>
        </div>
        <div style={styles.footerBar}>
          <Lock size={12} color="#475569" />
          <span>End-to-end encrypted · 256-bit AES · SOC 2 Compliant</span>
        </div>
      </footer>

      <style>{`
        @keyframes heroFloat { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-10px); } }
        @keyframes shimmerLine { 0% { left: -100%; } 100% { left: 100%; } }
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
  navNameAccent: {
    fontWeight: 800, fontSize: "18px",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
  },
  navLinks: { display: "flex", gap: "32px" },
  navLink: { color: "#94a3b8", fontSize: "14px", fontWeight: 500, cursor: "pointer", transition: "color 0.2s" },
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
    textAlign: "center", padding: "80px 24px 60px",
    maxWidth: "900px", margin: "0 auto",
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
  },
  heroTitleGradient: {
    background: "linear-gradient(135deg, #3b82f6, #06b6d4, #8b5cf6)",
    WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent",
  },
  heroSubtitle: {
    position: "relative", zIndex: 1,
    fontSize: "17px", lineHeight: 1.7, color: "#64748b",
    maxWidth: "600px", margin: "0 0 36px",
  },
  heroBtns: {
    position: "relative", zIndex: 1,
    display: "flex", gap: "14px", flexWrap: "wrap", justifyContent: "center",
    marginBottom: "60px",
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

  /* Preview card */
  previewCard: {
    position: "relative", zIndex: 1,
    width: "100%", maxWidth: "560px",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: "20px", overflow: "hidden",
    boxShadow: "0 24px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(59,130,246,0.06)",
    animation: "heroFloat 6s ease-in-out infinite",
  },
  previewHeader: {
    display: "flex", alignItems: "center", gap: "8px",
    padding: "14px 18px",
    background: "rgba(255,255,255,0.03)",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
  },
  previewDot: { width: "10px", height: "10px", borderRadius: "50%", background: "#ef4444" },
  previewTitle: { marginLeft: "auto", color: "#475569", fontSize: "12px", fontWeight: 600 },
  previewChat: { padding: "18px", display: "flex", flexDirection: "column", gap: "12px" },
  previewBubbleAgent: {
    display: "flex", gap: "10px", alignItems: "flex-start",
    padding: "12px 16px", borderRadius: "14px 14px 14px 4px",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.07)",
    fontSize: "13px", lineHeight: 1.6, color: "#cbd5e1",
  },
  previewBubbleUser: {
    alignSelf: "flex-end",
    padding: "12px 16px", borderRadius: "14px 14px 4px 14px",
    background: "linear-gradient(135deg, #3b82f6, #2563eb)",
    fontSize: "13px", lineHeight: 1.6, color: "#fff",
    maxWidth: "85%",
    boxShadow: "0 4px 16px rgba(59,130,246,0.3)",
  },

  /* Stats */
  statsSection: {
    position: "relative", zIndex: 1,
    display: "flex", justifyContent: "center", gap: "0",
    maxWidth: "800px", margin: "0 auto 80px",
    padding: "32px 40px",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: "20px",
    backdropFilter: "blur(16px)",
  },
  statItem: {
    flex: 1, textAlign: "center",
    padding: "10px 20px",
    borderRight: "1px solid rgba(255,255,255,0.06)",
  },
  statValue: {
    fontSize: "32px", fontWeight: 800, color: "#f0f4ff",
    letterSpacing: "-0.03em", lineHeight: 1,
    marginBottom: "6px",
  },
  statLabel: { fontSize: "13px", color: "#64748b", fontWeight: 500 },

  /* Sections */
  sectionHeader: { textAlign: "center", marginBottom: "48px" },
  sectionBadge: {
    display: "inline-flex", alignItems: "center", gap: "6px",
    padding: "5px 14px", borderRadius: "20px",
    background: "rgba(59,130,246,0.08)",
    border: "1px solid rgba(59,130,246,0.15)",
    fontSize: "12px", fontWeight: 600, color: "#60a5fa",
    marginBottom: "16px",
  },
  sectionTitle: {
    fontSize: "clamp(26px, 3.5vw, 38px)", fontWeight: 800,
    letterSpacing: "-0.03em", margin: "0 0 12px", color: "#f0f4ff",
  },
  sectionSubtitle: {
    fontSize: "16px", color: "#64748b", lineHeight: 1.6,
    maxWidth: "500px", margin: "0 auto",
  },

  /* Features */
  featuresSection: {
    position: "relative", zIndex: 1,
    maxWidth: "1100px", margin: "0 auto", padding: "0 24px 80px",
  },
  featuresGrid: {
    display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
    gap: "20px",
  },
  featureCard: {
    padding: "28px",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: "18px",
    cursor: "default",
    transition: "all 0.3s cubic-bezier(0.16,1,0.3,1)",
    boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
  },
  featureIcon: {
    width: "48px", height: "48px", borderRadius: "14px",
    display: "flex", alignItems: "center", justifyContent: "center",
    marginBottom: "18px",
  },
  featureTitle: {
    fontSize: "16px", fontWeight: 700, color: "#f0f4ff",
    margin: "0 0 10px", letterSpacing: "-0.01em",
  },
  featureDesc: {
    fontSize: "14px", color: "#64748b", lineHeight: 1.65, margin: 0,
  },

  /* How it works */
  howSection: {
    position: "relative", zIndex: 1,
    maxWidth: "1000px", margin: "0 auto", padding: "0 24px 80px",
  },
  stepsRow: {
    display: "flex", gap: "24px", justifyContent: "center",
    flexWrap: "wrap", position: "relative",
  },
  stepCard: {
    flex: "1 1 260px", maxWidth: "320px",
    padding: "32px 24px", textAlign: "center",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: "18px", position: "relative",
  },
  stepNum: {
    fontSize: "13px", fontWeight: 800, letterSpacing: "0.1em",
    marginBottom: "16px",
  },
  stepIconWrap: {
    width: "56px", height: "56px", borderRadius: "16px",
    border: "1px solid", display: "flex", alignItems: "center", justifyContent: "center",
    margin: "0 auto 16px",
  },
  stepTitle: { fontSize: "16px", fontWeight: 700, color: "#f0f4ff", margin: "0 0 10px" },
  stepDesc: { fontSize: "14px", color: "#64748b", lineHeight: 1.6, margin: 0 },
  stepConnector: {
    position: "absolute", top: "50%", right: "-20px", transform: "translateY(-50%)",
    display: "none", // hidden on mobile, could show on desktop
  },

  /* Testimonials */
  testimonialsSection: {
    position: "relative", zIndex: 1,
    maxWidth: "1100px", margin: "0 auto", padding: "0 24px 80px",
  },
  testimonialsGrid: {
    display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
    gap: "20px",
  },
  testimonialCard: {
    padding: "28px",
    background: "rgba(255,255,255,0.03)",
    border: "1px solid rgba(255,255,255,0.06)",
    borderRadius: "18px",
    transition: "all 0.3s ease",
  },
  testimonialStars: { display: "flex", gap: "3px", marginBottom: "16px" },
  testimonialText: { fontSize: "14px", color: "#cbd5e1", lineHeight: 1.7, margin: "0 0 20px", fontStyle: "italic" },
  testimonialAuthor: { display: "flex", alignItems: "center", gap: "12px" },
  testimonialAvatar: {
    width: "40px", height: "40px", borderRadius: "12px",
    background: "rgba(59,130,246,0.1)",
    border: "1px solid rgba(59,130,246,0.2)",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  testimonialName: { fontSize: "14px", fontWeight: 700, color: "#f0f4ff" },
  testimonialRole: { fontSize: "12px", color: "#64748b" },

  /* CTA */
  ctaSection: {
    position: "relative", zIndex: 1,
    textAlign: "center", padding: "80px 24px",
    maxWidth: "700px", margin: "0 auto",
  },
  ctaGlow: {
    position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)",
    width: "400px", height: "300px", borderRadius: "50%",
    background: "radial-gradient(circle, rgba(59,130,246,0.1) 0%, transparent 70%)",
    filter: "blur(60px)", pointerEvents: "none",
  },
  ctaTitle: {
    position: "relative", fontSize: "clamp(26px, 4vw, 40px)",
    fontWeight: 800, letterSpacing: "-0.03em", margin: "0 0 14px", color: "#f0f4ff",
  },
  ctaSubtitle: {
    position: "relative", fontSize: "16px", color: "#64748b",
    margin: "0 0 32px", lineHeight: 1.6,
  },
  ctaBtn: {
    position: "relative",
    display: "inline-flex", alignItems: "center", gap: "8px",
    padding: "16px 32px", borderRadius: "14px",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    border: "none", color: "#fff", fontSize: "16px", fontWeight: 700,
    cursor: "pointer", fontFamily: "'Inter', sans-serif",
    boxShadow: "0 4px 24px rgba(59,130,246,0.35)",
    transition: "all 0.25s",
  },

  /* Footer */
  footer: {
    position: "relative", zIndex: 1,
    borderTop: "1px solid rgba(255,255,255,0.06)",
    padding: "40px 24px 0",
  },
  footerInner: {
    maxWidth: "800px", margin: "0 auto",
    textAlign: "center", paddingBottom: "32px",
  },
  footerBrand: {
    display: "inline-flex", alignItems: "center", gap: "8px",
    marginBottom: "12px",
  },
  footerLogo: {
    width: "32px", height: "32px", borderRadius: "9px",
    background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  footerText: { color: "#475569", fontSize: "13px", margin: "0 0 16px" },
  footerLinks: { display: "flex", justifyContent: "center", gap: "8px" },
  footerLink: { color: "#64748b", fontSize: "13px", cursor: "pointer" },
  footerDot: { color: "#334155" },
  footerBar: {
    display: "flex", alignItems: "center", justifyContent: "center",
    gap: "8px", padding: "16px",
    borderTop: "1px solid rgba(255,255,255,0.04)",
    color: "#334155", fontSize: "11px",
  },
};
