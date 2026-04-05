import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Eye, EyeOff, Mail, Lock, ShieldCheck, ArrowRight, Loader2, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

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
  const [isAdmin, setIsAdmin] = useState(false);
  const [adminSecret, setAdminSecret] = useState("");

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
      const config = isAdmin ? { headers: { "X-Admin-Secret": adminSecret } } : {};
      const response = await axios.post(`${BASE_URL}/auth/login`, formData, config);

      if (response.data.success) {
        localStorage.setItem("token", response.data.jwt_token);
        localStorage.setItem("sessionId", response.data.session_id);
        localStorage.setItem("userId", response.data.user_id);
        localStorage.setItem("user_id", response.data.user_id);
        localStorage.setItem("customer_id", response.data.customer_id || "");
        
        if (response.data.role === "admin") {
          navigate("/admin-panel");
        } else {
          navigate("/dashboard");
        }
      } else {
        setError(response.data.message || "Login failed");
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.response?.data?.message || "Login failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  // Animation variants
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.6, ease: "easeOut" },
    },
  };

  const cardVariants = {
    hidden: { opacity: 0, scale: 0.95, y: 20 },
    visible: {
      opacity: 1,
      scale: 1,
      y: 0,
      transition: {
        duration: 0.7,
        ease: [0.4, 0, 0.2, 1],
      },
    },
  };

  const iconVariants = {
    animate: {
      y: [-3, 3, -3],
      transition: {
        duration: 4,
        repeat: Infinity,
        ease: "easeInOut",
      },
    },
  };

  const glowVariants = {
    animate: {
      scale: [1, 1.1, 1],
      opacity: [0.5, 0.8, 0.5],
      transition: {
        duration: 3,
        repeat: Infinity,
        ease: "easeInOut",
      },
    },
  };

  return (
    <div className="h-screen w-full flex items-center justify-center overflow-hidden font-sans relative">
      {/* ========== ANIMATED GRADIENT BACKGROUND ========== */}
      <div className="absolute inset-0 overflow-hidden">
        {/* Base dark gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#030614] via-[#0a0f1f] to-[#010005]" />
        
        {/* Animated gradient orbs */}
        <motion.div
          animate={{
            x: [0, 100, -50, 0],
            y: [0, -80, 40, 0],
            scale: [1, 1.2, 0.9, 1],
          }}
          transition={{
            duration: 25,
            repeat: Infinity,
            ease: "easeInOut",
          }}
          className="absolute top-1/4 left-1/4 w-[800px] h-[800px] rounded-full bg-[radial-gradient(circle,rgba(59,130,246,0.25)_0%,rgba(139,92,246,0.15)_40%,transparent_70%)] blur-[120px] pointer-events-none"
        />
        
        <motion.div
          animate={{
            x: [0, -120, 80, 0],
            y: [0, 100, -60, 0],
            scale: [1, 1.1, 1.2, 1],
          }}
          transition={{
            duration: 28,
            repeat: Infinity,
            ease: "easeInOut",
            delay: 2,
          }}
          className="absolute bottom-1/4 right-1/4 w-[700px] h-[700px] rounded-full bg-[radial-gradient(circle,rgba(6,182,212,0.2)_0%,rgba(59,130,246,0.1)_50%,transparent_80%)] blur-[100px] pointer-events-none"
        />
        
        <motion.div
          animate={{
            x: [0, 80, -100, 0],
            y: [0, -60, 90, 0],
          }}
          transition={{
            duration: 30,
            repeat: Infinity,
            ease: "easeInOut",
            delay: 4,
          }}
          className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-[radial-gradient(circle,rgba(168,85,247,0.15)_0%,transparent_70%)] blur-[100px] pointer-events-none"
        />
        
        {/* Subtle grid overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(56,189,248,0.03)_1px,transparent_1px),linear-gradient(0deg,rgba(56,189,248,0.03)_1px,transparent_1px)] bg-[size:60px_60px] pointer-events-none" />
        
        {/* Floating particles */}
        <div className="absolute inset-0 pointer-events-none">
          {[...Array(60)].map((_, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0 }}
              animate={{
                opacity: [0, 0.4, 0],
                y: [0, -30, 0],
              }}
              transition={{
                duration: Math.random() * 6 + 4,
                repeat: Infinity,
                delay: Math.random() * 5,
                ease: "easeInOut",
              }}
              className="absolute rounded-full bg-gradient-to-r from-blue-400 to-cyan-400"
              style={{
                width: Math.random() * 2 + 1 + "px",
                height: Math.random() * 2 + 1 + "px",
                top: Math.random() * 100 + "%",
                left: Math.random() * 100 + "%",
                filter: "blur(1px)",
              }}
            />
          ))}
        </div>
        
        {/* Spotlight glow behind card */}
        <motion.div
          variants={glowVariants}
          animate="animate"
          className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full bg-[radial-gradient(circle,rgba(59,130,246,0.3)_0%,rgba(139,92,246,0.15)_50%,transparent_80%)] blur-[80px] pointer-events-none"
        />
        
        {/* Vignette effect */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_0%,rgba(0,0,0,0.5)_100%)] pointer-events-none" />
      </div>

      {/* ========== LOGIN FORM CARD ========== */}
      <motion.div
        initial="hidden"
        animate="visible"
        variants={containerVariants}
        className="relative z-10 w-full max-w-[440px] mx-auto px-5"
      >
        {/* Animated floating icon with glow */}
        <motion.div variants={itemVariants} className="flex flex-col items-center text-center mb-8">
          <motion.div
            variants={iconVariants}
            animate="animate"
            className="relative"
          >
            <motion.div
              variants={glowVariants}
              animate="animate"
              className="absolute inset-0 rounded-2xl bg-gradient-to-r from-blue-600 to-purple-600 blur-xl opacity-60"
            />
            <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-600 via-cyan-500 to-purple-600 flex items-center justify-center shadow-2xl">
              <ShieldCheck size={28} className="text-white" />
            </div>
          </motion.div>
          <motion.h1
            variants={itemVariants}
            className="text-3xl font-bold text-white mt-4 tracking-tight"
          >
            Welcome Back
          </motion.h1>
          <motion.p
            variants={itemVariants}
            className="text-sm text-slate-400 mt-2"
          >
            Sign in to continue to BrainBack
          </motion.p>
        </motion.div>

        {/* Premium Glassmorphic Card with Gradient Border */}
        <motion.div
          variants={cardVariants}
          className="relative group"
          whileHover={{ y: -5 }}
          transition={{ duration: 0.3 }}
        >
          {/* Gradient Border Effect */}
          <div className="absolute -inset-[1px] bg-gradient-to-r from-blue-500 via-cyan-500 to-purple-500 rounded-2xl blur opacity-30 group-hover:opacity-50 transition duration-500" />
          <div className="absolute -inset-[1px] bg-gradient-to-r from-blue-500 via-cyan-500 to-purple-500 rounded-2xl opacity-20 group-hover:opacity-40 transition duration-500" />
          
          {/* Card Content */}
          <div className="relative bg-[#0a1022]/95 backdrop-blur-xl rounded-2xl p-8 shadow-2xl border border-white/10">
            {error && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="mb-6 p-3.5 bg-red-500/10 border border-red-500/25 rounded-xl"
              >
                <p className="text-red-400 text-sm text-center">{error}</p>
              </motion.div>
            )}

            <form onSubmit={handleLogin} className="flex flex-col gap-5">
              {/* Email Field */}
              <motion.div variants={itemVariants} className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Email Address
                </label>
                <div className="relative group/input">
                  <Mail size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within/input:text-cyan-400 transition-all duration-300" />
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    placeholder="you@example.com"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3.5 pl-11 text-white placeholder-slate-500 outline-none focus:border-cyan-500/60 focus:ring-4 focus:ring-cyan-500/15 focus:bg-white/10 transition-all duration-300"
                  />
                </div>
              </motion.div>

              {/* Password Field */}
              <motion.div variants={itemVariants} className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  Password
                </label>
                <div className="relative group/input">
                  <Lock size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 group-focus-within/input:text-cyan-400 transition-all duration-300" />
                  <input
                    type={showPass ? "text" : "password"}
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    placeholder="Enter your password"
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3.5 pl-11 pr-12 text-white placeholder-slate-500 outline-none focus:border-cyan-500/60 focus:ring-4 focus:ring-cyan-500/15 focus:bg-white/10 transition-all duration-300"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1.5 text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
                  >
                    {showPass ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </motion.div>

              {/* Admin Toggle */}
              <motion.div variants={itemVariants} className="flex justify-between items-center mt-1">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="adminToggle"
                    checked={isAdmin}
                    onChange={(e) => setIsAdmin(e.target.checked)}
                    className="w-4 h-4 rounded border-white/20 bg-white/5 text-cyan-500 focus:ring-cyan-500/50"
                  />
                  <label htmlFor="adminToggle" className="text-xs text-slate-400 select-none cursor-pointer">
                    Admin Access
                  </label>
                </div>
                <button
                  type="button"
                  onClick={() => navigate("/forgot-password")}
                  className="text-xs text-slate-500 hover:text-cyan-400 transition-colors"
                >
                  Forgot password?
                </button>
              </motion.div>

              {/* Admin Secret Input */}
              {isAdmin && (
                <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="space-y-1.5">
                  <label className="block text-[10px] font-semibold text-cyan-400 uppercase tracking-wider">
                    Admin Secret Code
                  </label>
                  <div className="relative group/input">
                    <ShieldCheck size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-cyan-500/70 group-focus-within/input:text-cyan-400 transition-all duration-300" />
                    <input
                      type="password"
                      value={adminSecret}
                      onChange={(e) => setAdminSecret(e.target.value)}
                      placeholder="Enter the secret code"
                      className="w-full bg-cyan-500/5 border border-cyan-500/20 rounded-xl px-4 py-3 pl-11 text-white placeholder-slate-500 outline-none focus:border-cyan-500/60 focus:ring-4 focus:ring-cyan-500/15 transition-all duration-300"
                    />
                  </div>
                </motion.div>
              )}

              {/* Submit Button */}
              <motion.button
                variants={itemVariants}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                disabled={loading}
                type="submit"
                className="relative mt-2 w-full overflow-hidden group/btn"
              >
                <div className="absolute inset-0 bg-gradient-to-r from-blue-600 via-cyan-500 to-purple-600 rounded-xl opacity-100 group-hover/btn:opacity-90 transition-opacity" />
                <div className="absolute inset-0 bg-gradient-to-r from-blue-500 via-cyan-400 to-purple-500 rounded-xl blur opacity-0 group-hover/btn:opacity-60 transition-opacity duration-300" />
                <div className="relative flex items-center justify-center gap-2 bg-gradient-to-r from-blue-600 to-purple-600 rounded-xl py-3.5 px-4">
                  {loading ? (
                    <>
                      <Loader2 size={20} className="animate-spin text-white" />
                      <span className="text-white font-bold">Signing in...</span>
                    </>
                  ) : (
                    <>
                      <span className="text-white font-bold">Sign In</span>
                      <ArrowRight size={20} className="text-white group-hover/btn:translate-x-1 transition-transform" />
                    </>
                  )}
                </div>
              </motion.button>
            </form>

            {/* Divider */}
            <motion.div variants={itemVariants} className="flex items-center gap-3 my-6">
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
              <span className="text-slate-500 text-xs uppercase font-semibold tracking-wider">
                New to BrainBack?
              </span>
              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
            </motion.div>

            {/* Sign Up Button */}
            <motion.button
              variants={itemVariants}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              onClick={() => navigate("/signup")}
              className="relative w-full group/signup overflow-hidden"
            >
              <div className="absolute inset-0 bg-white/5 rounded-xl opacity-0 group-hover/signup:opacity-100 transition-opacity duration-300" />
              <div className="absolute inset-0 border border-white/20 rounded-xl group-hover/signup:border-cyan-500/50 transition-all duration-300" />
              <div className="relative flex items-center justify-center gap-2 py-3 px-4">
                <span className="text-slate-300 font-semibold text-sm group-hover/signup:text-white transition-colors">
                  Create new account
                </span>
                <ArrowRight size={16} className="text-slate-400 group-hover/signup:text-cyan-400 group-hover/signup:translate-x-1 transition-all" />
              </div>
            </motion.button>
          </div>
        </motion.div>

        {/* Security Footer */}
        <motion.p
          variants={itemVariants}
          className="text-center mt-6 text-slate-500 text-[11px] font-medium uppercase tracking-wider"
        >
          🔒 Secured by BrainBack · End-to-end encrypted
        </motion.p>
      </motion.div>
    </div>
  );
};

export default Login;